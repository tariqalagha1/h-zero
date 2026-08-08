"""H-Zero — ReAct Agent Loop Engine.

Implements the Plan → Act → Observe → Evaluate cycle.
Integrates LLM Gateway for structured reasoning and Browser Fleet for execution.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

import structlog

from services.agent.state import (
    AgentRun, AgentRunConfig, AgentState, AgentVerdict, ReActStep,
)
from services.agent.dom_actions import DOMActionParser
from services.agent.browser_executor import BrowserExecutor

logger = structlog.get_logger("h_zero.agent.loop")

# ── ReAct Prompt Template ────────────────────────────────────────────────────

PLAN_SYSTEM_PROMPT = """You are H-Zero, an autonomous web agent. Your goal is to accomplish tasks by interacting with web pages.

You operate in a ReAct (Reasoning + Acting) loop:
1. PLAN: Analyze the current page state and decide the next action
2. ACT: Execute exactly ONE browser action
3. OBSERVE: See what changed
4. EVALUATE: Determine if the goal is reached or continue

AVAILABLE ACTIONS:
- navigate(url) — Go to a URL
- click(selector|text|index) — Click an element
- type(selector, value) — Type into an input field
- scroll(direction, amount) — Scroll the page
- extract(schema) — Extract structured data from the page
- wait(seconds) — Wait for page to load
- done(result) — Goal achieved, return result

RULES:
- Execute ONE action at a time
- Always check if the goal is reached before acting
- If blocked (CAPTCHA, login, paywall), report BLOCKED
- Extract data as early as possible after reaching the target page
- Be specific with selectors — use visible text when possible

Respond with JSON:
{
  "reasoning": "I see... therefore I will...",
  "next_action": "click|type|navigate|scroll|extract|wait|done",
  "target": "selector or url or text",
  "value": "text to type or scroll amount",
  "confidence": 0.0-1.0,
  "goal_progress": 0.0-1.0,
  "goal_reached": false
}"""


class ReActLoop:
    """The core autonomous agent loop.

    Each cycle:
    1. Send current DOM state + goal to LLM → get next action
    2. Execute action via Browser Fleet
    3. Observe new DOM state
    4. Evaluate: goal reached? continue?
    """

    def __init__(self, gateway=None, browser_fleet=None, embedding_pipeline=None):
        self._gateway = gateway
        self._fleet = browser_fleet
        self._embeddings = embedding_pipeline
        self._parser = DOMActionParser()
        self._executor = BrowserExecutor(fleet=browser_fleet)

    async def run(self, config: AgentRunConfig) -> AgentRun:
        """Execute a full autonomous agent run."""
        run = AgentRun(config=config)
        run.start()
        sandbox_id = None

        logger.info(f"Agent run {config.run_id} started: {config.goal}")

        try:
            # Navigate to start URL
            if config.start_url:
                step = ReActStep(cycle_index=0, state=AgentState.ACTING)
                step.started_at = datetime.now(timezone.utc).isoformat()
                step.action_type = "navigate"
                step.action_target = config.start_url

                nav_result = await self._executor.navigate(config.start_url)
                sandbox_id = nav_result.get("sandbox_id")

                step.action_success = "error" not in nav_result
                step.action_error = nav_result.get("error", "")
                step.dom_snapshot = nav_result
                step.page_title = nav_result.get("title", "")
                step.page_url = nav_result.get("url", "")
                step.completed_at = datetime.now(timezone.utc).isoformat()

                run.add_step(step)

                if not step.action_success:
                    run.fail(f"Navigation failed: {step.action_error}")
                    return run

            # Main ReAct loop
            while run.current_cycle < config.max_cycles:
                # Check timeout
                elapsed = time.time() - datetime.fromisoformat(run.started_at).timestamp()
                if elapsed > config.max_duration_seconds:
                    run.block("Max duration exceeded", AgentVerdict.TIMED_OUT)
                    break

                cycle = run.current_cycle + 1

                # ── PLAN ──
                plan_step = await self._plan(run, cycle)
                run.add_step(plan_step)

                if plan_step.action_type == "done":
                    run.complete(
                        AgentVerdict.GOAL_ACHIEVED,
                        result=plan_step.extracted_data or {"status": "done"},
                    )
                    break

                if plan_step.action_type == "blocked":
                    verdict_map = {
                        "captcha": AgentVerdict.BLOCKED_BY_CAPTCHA,
                        "login": AgentVerdict.BLOCKED_BY_LOGIN,
                        "paywall": AgentVerdict.BLOCKED_BY_PAYWALL,
                    }
                    run.block(
                        plan_step.evaluation or "Blocked",
                        verdict_map.get(plan_step.action_value, AgentVerdict.BLOCKED_BY_CAPTCHA),
                    )
                    break

                # ── ACT ──
                act_step = ReActStep(
                    cycle_index=cycle,
                    state=AgentState.ACTING,
                    action_type=plan_step.action_type,
                    action_target=plan_step.action_target,
                    action_value=plan_step.action_value,
                )
                act_step.started_at = datetime.now(timezone.utc).isoformat()

                action_result = await self._executor.execute(
                    action_type=plan_step.action_type,
                    target=plan_step.action_target,
                    value=plan_step.action_value,
                    sandbox_id=sandbox_id,
                )

                act_step.action_success = action_result.get("success", False)
                act_step.action_error = action_result.get("error", "")
                act_step.dom_snapshot = action_result
                act_step.page_url = action_result.get("url", "")
                act_step.page_title = action_result.get("title", "")
                act_step.completed_at = datetime.now(timezone.utc).isoformat()
                run.add_step(act_step)

                # ── OBSERVE ──
                obs_step = ReActStep(cycle_index=cycle, state=AgentState.OBSERVING)
                obs_step.started_at = datetime.now(timezone.utc).isoformat()

                dom_state = await self._executor.get_dom(sandbox_id)
                obs_step.dom_snapshot = dom_state
                obs_step.page_url = dom_state.get("url", "")
                obs_step.page_title = dom_state.get("title", "")
                obs_step.observation_text = dom_state.get("text", "")[:2000]
                obs_step.completed_at = datetime.now(timezone.utc).isoformat()
                run.add_step(obs_step)

                # ── EVALUATE ──
                eval_step = await self._evaluate(run, cycle, obs_step)
                run.add_step(eval_step)

                if eval_step.goal_progress >= 0.95:
                    run.complete(
                        AgentVerdict.GOAL_ACHIEVED,
                        result=eval_step.extracted_data or {"goal": "achieved"},
                    )
                    break

                if not eval_step.should_continue:
                    run.complete(
                        AgentVerdict.PARTIALLY_ACHIEVED,
                        result=eval_step.extracted_data or {"goal": "partial"},
                    )
                    break

            # If loop exhausted without terminal verdict
            if not run.is_terminal():
                run.complete(AgentVerdict.GOAL_NOT_ACHIEVED,
                           result={"reason": "Max cycles reached"})

        except Exception as e:
            logger.error(f"Agent run {config.run_id} failed: {e}")
            run.fail(str(e))

        return run

    async def _plan(self, run: AgentRun, cycle: int) -> ReActStep:
        """PLAN phase: Ask LLM to decide next action based on current state."""
        step = ReActStep(cycle_index=cycle, state=AgentState.PLANNING)
        step.started_at = datetime.now(timezone.utc).isoformat()

        # Build context from last observation
        last_obs = None
        for s in reversed(run.steps):
            if s.state == AgentState.OBSERVING and s.dom_snapshot:
                last_obs = s
                break

        # Build messages for LLM
        dom_text = ""
        elements = []
        if last_obs and last_obs.dom_snapshot:
            dom_text = last_obs.dom_snapshot.get("text", "")[:4000]
            elements = last_obs.dom_snapshot.get("elements", [])[:50]

        element_list = "\n".join(
            f"[{e.get('index', i)}] {e.get('tag', '?')} "
            f"\"{e.get('text', '')[:80]}\" "
            f"{'(hidden)' if not e.get('visible') else ''}"
            for i, e in enumerate(elements)
        )

        user_prompt = f"""Goal: {run.config.goal}

Current URL: {last_obs.page_url if last_obs else run.config.start_url}
Page Title: {last_obs.page_title if last_obs else ''}
Cycle: {cycle}/{run.config.max_cycles}
Goal Progress: {run.steps[-1].goal_progress if run.steps else 0.0}

Page Content Preview:
{dom_text[:3000]}

Interactive Elements:
{element_list[:2000]}

Previous Actions:
{self._format_action_history(run)}

What is your next action? Respond with JSON only."""

        try:
            if self._gateway:
                from services.gateway.llm_gateway import LLMRequest, TaskType

                request = LLMRequest(
                    messages=[
                        {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    task_type=TaskType.GENERAL,
                    model=run.config.llm_model,
                    response_format={"type": "json_object"},
                )
                response = await self._gateway.generate(request)

                if response.content and not response.error:
                    plan_data = json.loads(response.content)
                    step.plan_reasoning = plan_data.get("reasoning", "")
                    step.plan_next_action = plan_data.get("next_action", "")
                    step.action_type = plan_data.get("next_action", "")
                    step.action_target = plan_data.get("target", "")
                    step.action_value = plan_data.get("value", "")
                    step.plan_confidence = plan_data.get("confidence", 0.5)
                    step.goal_progress = plan_data.get("goal_progress", 0.0)
                else:
                    step.action_type = "done"
                    step.evaluation = f"LLM error: {response.error}"
            else:
                # Dev fallback: simple heuristic planning
                step = self._heuristic_plan(run, cycle, last_obs, elements)

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            step.action_type = "done"
            step.evaluation = f"Planning error: {e}"

        step.completed_at = datetime.now(timezone.utc).isoformat()
        return step

    def _heuristic_plan(self, run: AgentRun, cycle: int, last_obs, elements) -> ReActStep:
        """Fallback heuristic planner when LLM is unavailable."""
        step = ReActStep(cycle_index=cycle, state=AgentState.PLANNING)

        # Simple heuristic: if first cycle, extract; else click first visible element
        if cycle == 1:
            step.action_type = "extract"
            step.action_target = "page"
            step.plan_reasoning = "First cycle — extracting page data"
        elif cycle >= run.config.max_cycles - 1:
            step.action_type = "done"
            step.plan_reasoning = "Approaching max cycles — finishing"
        else:
            visible = [e for e in elements if e.get("visible")]
            if visible:
                step.action_type = "click"
                step.action_target = visible[0].get("text", f"[{visible[0].get('index', 0)}]")
                step.plan_reasoning = f"Clicking first visible element: {step.action_target}"
            else:
                step.action_type = "scroll"
                step.action_target = "down"
                step.plan_reasoning = "No visible elements — scrolling down"

        step.plan_confidence = 0.3
        step.goal_progress = min(cycle / run.config.max_cycles, 0.9)
        return step

    async def _evaluate(self, run: AgentRun, cycle: int, obs_step) -> ReActStep:
        """EVALUATE phase: Have LLM assess if goal is reached."""
        step = ReActStep(
            cycle_index=cycle,
            state=AgentState.EVALUATING,
            goal_progress=run.steps[-1].goal_progress if run.steps else 0.0,
        )
        step.started_at = datetime.now(timezone.utc).isoformat()

        eval_prompt = f"""Goal: {run.config.goal}

Current URL: {obs_step.page_url}
Page Title: {obs_step.page_title}

Page Content:
{obs_step.observation_text[:3000]}

Action History:
{self._format_action_history(run)}

Evaluate: Is the goal achieved? Respond with JSON:
{{
  "goal_achieved": true/false,
  "progress": 0.0-1.0,
  "continue": true/false,
  "extracted_data": {{}},
  "evaluation": "brief assessment"
}}"""

        try:
            if self._gateway:
                from services.gateway.llm_gateway import LLMRequest, TaskType
                request = LLMRequest(
                    messages=[
                        {"role": "system", "content": "You evaluate web agent progress. Respond with JSON only."},
                        {"role": "user", "content": eval_prompt},
                    ],
                    task_type=TaskType.GENERAL,
                    response_format={"type": "json_object"},
                )
                response = await self._gateway.generate(request)

                if response.content and not response.error:
                    eval_data = json.loads(response.content)
                    step.goal_progress = eval_data.get("progress", 0.5)
                    step.should_continue = eval_data.get("continue", True)
                    step.extracted_data = eval_data.get("extracted_data")
                    step.evaluation = eval_data.get("evaluation", "")
                else:
                    step.should_continue = False
                    step.evaluation = "Evaluation error"
            else:
                step.should_continue = cycle < run.config.max_cycles
                step.evaluation = "Heuristic: continuing until max cycles"
                step.goal_progress = min(cycle / run.config.max_cycles, 0.9)
        except Exception as e:
            step.should_continue = False
            step.evaluation = f"Eval error: {e}"

        step.completed_at = datetime.now(timezone.utc).isoformat()
        return step

    def _format_action_history(self, run: AgentRun) -> str:
        """Format the action history for LLM context."""
        lines = []
        for s in run.steps[-10:]:  # Last 10 steps
            if s.state == AgentState.ACTING:
                status = "✓" if s.action_success else "✗"
                lines.append(
                    f"[{s.cycle_index}] {status} {s.action_type}({s.action_target}) "
                    f"→ {s.page_url[:60]}"
                )
            elif s.state == AgentState.EVALUATING:
                lines.append(f"[{s.cycle_index}] EVAL: progress={s.goal_progress:.1%} continue={s.should_continue}")
        return "\n".join(lines) if lines else "No actions yet"


# Singleton
_loop: Optional[ReActLoop] = None


def get_react_loop() -> ReActLoop:
    global _loop
    if _loop is None:
        _loop = ReActLoop()
    return _loop
