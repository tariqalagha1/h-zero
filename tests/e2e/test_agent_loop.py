"""H-Zero — E2E ReAct Agent Loop Test.

Verifies that the ReAct loop orchestrates Plan → Act → Observe → Evaluate
correctly, handles terminal conditions, and produces valid run summaries.
"""

import pytest

from services.agent.state import (
    AgentRun, AgentRunConfig, AgentState, AgentVerdict, ReActStep,
)


class TestReActStateMachine:
    """Verify the ReAct state machine transitions and terminal conditions."""

    def test_initial_state(self):
        """Agent starts in IDLE state."""
        config = AgentRunConfig(goal="Test goal", start_url="http://example.com")
        run = AgentRun(config=config)
        assert run.state == AgentState.IDLE
        assert run.current_cycle == 0
        assert run.verdict is None

    def test_start_transition(self):
        """start() transitions IDLE → PLANNING."""
        config = AgentRunConfig(goal="Test goal", start_url="http://example.com")
        run = AgentRun(config=config)
        result = run.start()
        assert run.state == AgentState.PLANNING
        assert result["run_id"] == config.run_id
        assert result["status"] == "started"

    def test_add_step(self):
        """add_step increments cycle and tracks steps."""
        config = AgentRunConfig(goal="Test", start_url="http://example.com")
        run = AgentRun(config=config)
        run.start()

        step = ReActStep(cycle_index=1, state=AgentState.PLANNING)
        run.add_step(step)
        assert run.current_cycle == 1
        assert len(run.steps) == 1

    def test_complete_transition(self):
        """complete() sets terminal state with verdict."""
        config = AgentRunConfig(goal="Test", start_url="http://example.com")
        run = AgentRun(config=config)
        run.start()
        run.complete(AgentVerdict.GOAL_ACHIEVED, {"data": "test"})
        assert run.state == AgentState.COMPLETED
        assert run.verdict == AgentVerdict.GOAL_ACHIEVED
        assert run.final_result == {"data": "test"}
        assert run.is_terminal()

    def test_fail_transition(self):
        """fail() records error and marks FAILED."""
        config = AgentRunConfig(goal="Test", start_url="http://example.com")
        run = AgentRun(config=config)
        run.start()
        run.fail("Connection timeout")
        assert run.state == AgentState.FAILED
        assert "Connection timeout" in run.errors
        assert run.is_terminal()

    def test_block_transition(self):
        """block() records reason and appropriate verdict."""
        config = AgentRunConfig(goal="Test", start_url="http://example.com")
        run = AgentRun(config=config)
        run.start()
        run.block("CAPTCHA detected", AgentVerdict.BLOCKED_BY_CAPTCHA)
        assert run.state == AgentState.BLOCKED
        assert run.verdict == AgentVerdict.BLOCKED_BY_CAPTCHA
        assert run.is_terminal()

    def test_cancel_transition(self):
        """cancel() marks CANCELLED."""
        config = AgentRunConfig(goal="Test", start_url="http://example.com")
        run = AgentRun(config=config)
        run.start()
        run.cancel()
        assert run.state == AgentState.CANCELLED
        assert run.is_terminal()

    def test_is_terminal_states(self):
        """Only terminal states return True."""
        config = AgentRunConfig(goal="Test", start_url="http://example.com")
        run = AgentRun(config=config)

        terminal_states = [
            AgentState.COMPLETED, AgentState.FAILED,
            AgentState.CANCELLED, AgentState.BLOCKED,
        ]
        non_terminal = [
            AgentState.IDLE, AgentState.PLANNING, AgentState.ACTING,
            AgentState.OBSERVING, AgentState.EVALUATING, AgentState.WAITING,
        ]

        for state in terminal_states:
            run.state = state
            assert run.is_terminal(), f"{state} should be terminal"

        for state in non_terminal:
            run.state = state
            assert not run.is_terminal(), f"{state} should not be terminal"

    def test_summary_output(self):
        """summary() produces expected dict structure."""
        config = AgentRunConfig(goal="Test", start_url="http://example.com")
        run = AgentRun(config=config)
        run.start()
        run.complete(AgentVerdict.GOAL_ACHIEVED)

        summary = run.summary()
        assert summary["run_id"] == config.run_id
        assert summary["state"] == "COMPLETED"
        assert summary["verdict"] == "GOAL_ACHIEVED"
        assert summary["goal"] == "Test"
        assert "started_at" in summary
        assert "completed_at" in summary

    def test_step_to_dict(self):
        """ReActStep.to_dict() produces expected structure."""
        step = ReActStep(
            cycle_index=3,
            state=AgentState.ACTING,
            plan_reasoning="Click button to search",
            action_type="click",
            action_target="#search-btn",
            action_success=True,
            duration_ms=150,
        )
        d = step.to_dict()
        assert d["cycle_index"] == 3
        assert d["state"] == "ACTING"
        assert d["action_type"] == "click"
        assert d["action_success"] is True


class TestAgentRunConfig:
    """Verify run configuration validation."""

    def test_defaults(self):
        config = AgentRunConfig(goal="Test", start_url="http://example.com")
        assert config.max_cycles == 20
        assert config.max_duration_seconds == 600
        assert config.llm_model == "gpt-4o"
        assert config.run_id is not None

    def test_allowed_domains(self):
        config = AgentRunConfig(
            goal="Test", start_url="http://example.com",
            allowed_domains=["example.com", "test.org"],
        )
        assert len(config.allowed_domains) == 2
        assert "example.com" in config.allowed_domains

    def test_extract_schema(self):
        schema = {"title": "string", "count": "number"}
        config = AgentRunConfig(
            goal="Test", start_url="http://example.com",
            extract_schema=schema,
        )
        assert config.extract_schema == schema


class TestDOMParserActionTypes:
    """Verify DOM action parser handles all ReAct action types."""

    def setup_method(self):
        from services.agent.dom_actions import DOMActionParser
        self.parser = DOMActionParser()

    def test_valid_actions_list(self):
        """All expected actions are in VALID_ACTIONS."""
        expected = {"navigate", "click", "type", "scroll", "extract", "wait", "done", "blocked"}
        assert self.parser.VALID_ACTIONS == expected

    def test_all_actions_parse_without_error(self):
        """Every valid action type parsable without crashing."""
        for action in self.parser.VALID_ACTIONS:
            result = self.parser.parse(action, "test_target", "test_value")
            assert result.action_type in self.parser.VALID_ACTIONS
            assert result.selector_type in ("css", "text", "index", "url", "none", "")


class TestBrowserExecutorDevMode:
    """Verify browser executor works in dev mode (no fleet)."""

    def setup_method(self):
        from services.agent.browser_executor import BrowserExecutor
        self.executor = BrowserExecutor(fleet=None)

    async def test_direct_navigate(self):
        result = await self.executor._direct_navigate("http://example.com")
        assert result["url"] == "http://example.com"
        assert result["success"] is True

    async def test_execute_navigate_dev(self):
        result = await self.executor.execute("navigate", "http://example.com")
        assert result["action"] == "navigate"

    async def test_execute_wait_dev(self):
        result = await self.executor.execute("wait", "", "1")
        assert result["action"] == "wait"
        assert result["success"] is True

    async def test_get_dom_dev(self):
        result = await self.executor.get_dom()
        assert "url" in result
        assert "elements" in result
