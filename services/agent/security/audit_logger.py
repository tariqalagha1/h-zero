"""H-Zero — Security Audit Logger.

Produces structured JSON audit logs in the required format:
{
  "iteration_step": N,
  "target": "string",
  "observation": "Key response details, headers, or parameters discovered",
  "hypothesis": "Assessed potential weakness based on observation",
  "probe_executed": "Payload or command sent to verify hypothesis",
  "outcome": "VERIFIED_VULNERABILITY | REJECTED | REQUIRES_FURTHER_PROBING",
  "next_action": "Plan for subsequent iteration step or conclusion"
}
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class AuditOutcome(str, Enum):
    VERIFIED_VULNERABILITY = "VERIFIED_VULNERABILITY"
    REJECTED = "REJECTED"
    REQUIRES_FURTHER_PROBING = "REQUIRES_FURTHER_PROBING"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class AuditEntry:
    """A single audit log entry matching the spec format."""
    iteration_step: int = 0
    target: str = ""
    observation: str = ""
    hypothesis: str = ""
    probe_executed: str = ""
    outcome: AuditOutcome = AuditOutcome.REQUIRES_FURTHER_PROBING
    next_action: str = ""
    severity: Optional[Severity] = None
    evidence: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = {
            "iteration_step": self.iteration_step,
            "target": self.target,
            "observation": self.observation,
            "hypothesis": self.hypothesis,
            "probe_executed": self.probe_executed,
            "outcome": self.outcome.value,
            "next_action": self.next_action,
            "timestamp": self.timestamp,
        }
        if self.severity:
            d["severity"] = self.severity.value
        if self.evidence:
            d["evidence"] = self.evidence
        return d


@dataclass
class AuditTrail:
    """Full audit trail for a security assessment run."""
    run_id: str = ""
    target_url: str = ""
    entries: list[AuditEntry] = field(default_factory=list)
    findings: list[AuditEntry] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    summary: dict = field(default_factory=dict)

    def add_entry(self, entry: AuditEntry):
        self.entries.append(entry)
        if entry.outcome == AuditOutcome.VERIFIED_VULNERABILITY:
            self.findings.append(entry)

    def finalize(self) -> dict:
        self.completed_at = datetime.now(timezone.utc).isoformat()
        vulns_by_severity = {}
        for f in self.findings:
            sev = f.severity.value if f.severity else "INFO"
            vulns_by_severity[sev] = vulns_by_severity.get(sev, 0) + 1

        self.summary = {
            "total_iterations": len(self.entries),
            "verified_vulnerabilities": len(self.findings),
            "by_severity": vulns_by_severity,
            "targets_probed": len(set(e.target for e in self.entries)),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
        return {
            "run_id": self.run_id,
            "target_url": self.target_url,
            "entries": [e.to_dict() for e in self.entries],
            "findings": [e.to_dict() for e in self.findings],
            "summary": self.summary,
        }

    def start(self):
        self.started_at = datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """Manages security audit trails during assessments.

    Thread-safe append-only log. Each cycle produces one AuditEntry.
    Findings are extracted automatically when outcome is VERIFIED_VULNERABILITY.
    """

    def __init__(self):
        self._active_trails: dict[str, AuditTrail] = {}

    def start_trail(self, run_id: str, target_url: str) -> AuditTrail:
        trail = AuditTrail(run_id=run_id, target_url=target_url)
        trail.start()
        self._active_trails[run_id] = trail
        return trail

    def log(self, run_id: str, entry: AuditEntry) -> None:
        trail = self._active_trails.get(run_id)
        if trail:
            trail.add_entry(entry)

    def get_findings(self, run_id: str) -> list[AuditEntry]:
        trail = self._active_trails.get(run_id)
        if trail:
            return trail.findings
        return []

    def finalize(self, run_id: str) -> Optional[dict]:
        trail = self._active_trails.pop(run_id, None)
        if trail:
            return trail.finalize()
        return None

    def get_trail(self, run_id: str) -> Optional[AuditTrail]:
        return self._active_trails.get(run_id)


# Singleton
_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _logger
    if _logger is None:
        _logger = AuditLogger()
    return _logger
