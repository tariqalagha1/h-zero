"""H-Zero — Agent State Machine.

Describes the lifecycle of an autonomous agent run:
IDLE → PLANNING → ACTING → OBSERVING → EVALUATING → (loop or terminal)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid


class AgentState(str, Enum):
    """States of an autonomous agent run."""
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    EVALUATING = "EVALUATING"
    WAITING = "WAITING"          # paused for external input
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"          # cannot proceed (CAPTCHA, login wall, etc.)


class AgentVerdict(str, Enum):
    """Final verdict of an agent run."""
    GOAL_ACHIEVED = "GOAL_ACHIEVED"
    PARTIALLY_ACHIEVED = "PARTIALLY_ACHIEVED"
    GOAL_NOT_ACHIEVED = "GOAL_NOT_ACHIEVED"
    BLOCKED_BY_CAPTCHA = "BLOCKED_BY_CAPTCHA"
    BLOCKED_BY_LOGIN = "BLOCKED_BY_LOGIN"
    BLOCKED_BY_PAYWALL = "BLOCKED_BY_PAYWALL"
    TIMED_OUT = "TIMED_OUT"
    ERROR = "ERROR"


@dataclass
class AgentRunConfig:
    """Configuration for an autonomous agent run."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mission_id: Optional[str] = None
    tenant_id: str = ""
    user_id: str = ""
    goal: str = ""
    start_url: str = ""
    max_cycles: int = 20
    max_duration_seconds: int = 600
    allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    llm_model: str = "gpt-4o"
    llm_provider: str = ""
    extract_schema: Optional[dict] = None  # JSON schema for structured extraction
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReActStep:
    """A single step in the ReAct loop."""
    cycle_index: int = 0
    state: AgentState = AgentState.PLANNING

    # Planning phase
    plan_reasoning: str = ""
    plan_next_action: str = ""
    plan_confidence: float = 0.0

    # Acting phase
    action_type: str = ""          # navigate, click, type, scroll, extract, wait
    action_target: str = ""        # CSS selector, URL, or text
    action_value: str = ""         # input text, scroll amount
    action_coordinates: Optional[dict] = None

    # Observing phase
    dom_snapshot: Optional[dict] = None
    page_title: str = ""
    page_url: str = ""
    observation_text: str = ""
    action_success: bool = True
    action_error: str = ""

    # Evaluating phase
    evaluation: str = ""
    goal_progress: float = 0.0     # 0.0 to 1.0
    should_continue: bool = True
    extracted_data: Optional[dict] = None

    # Timing
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "cycle_index": self.cycle_index,
            "state": self.state.value,
            "plan_reasoning": self.plan_reasoning[:500],
            "plan_next_action": self.plan_next_action,
            "action_type": self.action_type,
            "action_target": self.action_target,
            "action_success": self.action_success,
            "evaluation": self.evaluation[:500],
            "goal_progress": self.goal_progress,
            "should_continue": self.should_continue,
            "duration_ms": self.duration_ms,
        }


@dataclass
class AgentRun:
    """Full state of an autonomous agent run."""
    config: AgentRunConfig
    state: AgentState = AgentState.IDLE
    steps: list[ReActStep] = field(default_factory=list)
    current_cycle: int = 0
    verdict: Optional[AgentVerdict] = None
    final_result: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    dom_snapshots: list[str] = field(default_factory=list)  # snapshot IDs
    started_at: str = ""
    completed_at: str = ""

    def start(self) -> dict:
        self.state = AgentState.PLANNING
        self.started_at = datetime.now(timezone.utc).isoformat()
        return {
            "run_id": self.config.run_id,
            "status": "started",
            "goal": self.config.goal,
            "start_url": self.config.start_url,
            "max_cycles": self.config.max_cycles,
        }

    def add_step(self, step: ReActStep):
        self.steps.append(step)
        self.current_cycle = step.cycle_index

    def complete(self, verdict: AgentVerdict, result: dict = None):
        self.state = AgentState.COMPLETED
        self.verdict = verdict
        self.final_result = result or {}
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def fail(self, error: str):
        self.state = AgentState.FAILED
        self.verdict = AgentVerdict.ERROR
        self.errors.append(error)
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def block(self, reason: str, verdict: AgentVerdict = AgentVerdict.BLOCKED_BY_CAPTCHA):
        self.state = AgentState.BLOCKED
        self.verdict = verdict
        self.errors.append(reason)
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def cancel(self):
        self.state = AgentState.CANCELLED
        self.verdict = AgentVerdict.ERROR
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def is_terminal(self) -> bool:
        return self.state in (
            AgentState.COMPLETED, AgentState.FAILED,
            AgentState.CANCELLED, AgentState.BLOCKED,
        )

    def summary(self) -> dict:
        return {
            "run_id": self.config.run_id,
            "state": self.state.value,
            "verdict": self.verdict.value if self.verdict else None,
            "cycles_completed": self.current_cycle,
            "total_steps": len(self.steps),
            "goal": self.config.goal,
            "start_url": self.config.start_url,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "errors": self.errors,
        }
