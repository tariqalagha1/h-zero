"""H-Zero — Scope Enforcer.

Strict access control for security testing targets.
Only allows probes against explicitly authorized:
- IP addresses and subnets
- URLs and domains
- localhost and sandbox interfaces

Blocks probes to external/unapproved targets under ALL circumstances.
"""

import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from urllib.parse import urlparse


class ScopeDecision(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    INVALID_TARGET = "INVALID_TARGET"


@dataclass
class ScopeRule:
    """A single scope rule for a target."""
    pattern: str
    rule_type: str  # domain, ip, subnet, url_prefix, exact
    description: str = ""
    allowed: bool = True


@dataclass
class ScopeResult:
    """Result of a scope check."""
    target: str
    decision: ScopeDecision
    matched_rule: Optional[str] = None
    reason: str = ""


class ScopeEnforcer:
    """Enforces strict testing boundaries.

    Only allows probes against:
    - Explicitly approved domains
    - Approved IP addresses and subnets
    - localhost (127.0.0.1, ::1)
    - Docker sandbox networks (172.16.0.0/12)
    """

    # Always-allowed local/loopback ranges
    LOCALHOST_IPS = {
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
    }

    # Docker default bridge and compose networks
    DOCKER_NETWORKS = {
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("192.168.0.0/16"),
    }

    # Always-blocked external metadata services
    BLOCKED_IPS = {
        ipaddress.ip_network("169.254.169.254/32"),  # AWS/cloud metadata
    }

    def __init__(self):
        self._rules: list[ScopeRule] = []
        self._allowed_domains: set[str] = set()
        self._allowed_ips: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()

    def add_allowed_domain(self, domain: str, description: str = ""):
        """Add a domain to the allowed scope."""
        domain = domain.lower().strip()
        self._allowed_domains.add(domain)
        self._rules.append(ScopeRule(
            pattern=domain,
            rule_type="domain",
            description=description or f"Allowed domain: {domain}",
        ))

    def add_allowed_subnet(self, subnet: str, description: str = ""):
        """Add an IP subnet to the allowed scope."""
        net = ipaddress.ip_network(subnet, strict=False)
        self._allowed_ips.add(net)
        self._rules.append(ScopeRule(
            pattern=str(net),
            rule_type="subnet",
            description=description or f"Allowed subnet: {net}",
        ))

    def add_allowed_url_prefix(self, prefix: str, description: str = ""):
        """Add a URL prefix to the allowed scope."""
        self._rules.append(ScopeRule(
            pattern=prefix,
            rule_type="url_prefix",
            description=description or f"Allowed URL prefix: {prefix}",
        ))

    def check(self, target: str) -> ScopeResult:
        """Check if a target is in scope for testing.

        Returns ScopeResult with decision and reasoning.
        """
        if not target or not target.strip():
            return ScopeResult(target=target, decision=ScopeDecision.INVALID_TARGET,
                             reason="Empty target")

        target = target.strip()

        # Parse the target
        parsed = urlparse(target if "://" in target else f"http://{target}")
        hostname = parsed.hostname or target
        port = parsed.port
        scheme = parsed.scheme or "http"

        # 1. Check if it's an IP address
        try:
            ip = ipaddress.ip_address(hostname)

            # Block cloud metadata
            for blocked_net in self.BLOCKED_IPS:
                if ip in blocked_net:
                    return ScopeResult(target=target, decision=ScopeDecision.BLOCKED,
                                     reason=f"Cloud metadata service blocked: {ip}")

            # Allow localhost
            for local_net in self.LOCALHOST_IPS:
                if ip in local_net:
                    return ScopeResult(target=target, decision=ScopeDecision.ALLOWED,
                                     matched_rule="localhost", reason="Local loopback")

            # Allow docker networks
            for docker_net in self.DOCKER_NETWORKS:
                if ip in docker_net:
                    return ScopeResult(target=target, decision=ScopeDecision.ALLOWED,
                                     matched_rule=f"docker:{docker_net}", reason="Container network")

            # Check against allowed subnets
            for net in self._allowed_ips:
                if ip in net:
                    return ScopeResult(target=target, decision=ScopeDecision.ALLOWED,
                                     matched_rule=str(net), reason=f"Allowed subnet: {net}")

            return ScopeResult(target=target, decision=ScopeDecision.OUT_OF_SCOPE,
                             reason=f"IP {ip} not in allowed subnets and not local")

        except ValueError:
            pass  # Not an IP, treat as hostname

        # 2. Check domain allowlist
        hostname_lower = hostname.lower()

        # Allow localhost hostnames
        if hostname_lower in ("localhost", "127.0.0.1", "::1"):
            return ScopeResult(target=target, decision=ScopeDecision.ALLOWED,
                             matched_rule="localhost", reason="Local hostname")

        for domain in self._allowed_domains:
            if hostname_lower == domain or hostname_lower.endswith(f".{domain}"):
                return ScopeResult(target=target, decision=ScopeDecision.ALLOWED,
                                 matched_rule=f"domain:{domain}", reason=f"Allowed domain: {domain}")

        # 3. Check URL prefix rules
        target_lower = target.lower()
        for rule in self._rules:
            if rule.rule_type == "url_prefix" and target_lower.startswith(rule.pattern.lower()):
                return ScopeResult(target=target, decision=ScopeDecision.ALLOWED,
                                 matched_rule=rule.pattern, reason=rule.description)

        return ScopeResult(target=target, decision=ScopeDecision.OUT_OF_SCOPE,
                         reason=f"Domain '{hostname}' not in allowed scope")

    def is_allowed(self, target: str) -> bool:
        """Quick check: is this target in scope?"""
        return self.check(target).decision == ScopeDecision.ALLOWED

    def get_scope_summary(self) -> dict:
        """Return a summary of the current scope configuration."""
        domains = sorted(self._allowed_domains)
        subnets = sorted(str(n) for n in self._allowed_ips)
        url_prefixes = [r.pattern for r in self._rules if r.rule_type == "url_prefix"]
        return {
            "allowed_domains": domains,
            "allowed_subnets": subnets,
            "allowed_url_prefixes": url_prefixes,
            "always_allowed": ["127.0.0.0/8", "::1", "172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16"],
            "always_blocked": ["169.254.169.254/32"],
        }


# ── Pre-built scope for local testing ──────────────────────────────────────


def create_local_scope() -> ScopeEnforcer:
    """Create a scope enforcer configured for local sandbox testing."""
    enforcer = ScopeEnforcer()
    enforcer.add_allowed_domain("localhost", "Local development")
    enforcer.add_allowed_domain("127.0.0.1", "Local loopback")
    enforcer.add_allowed_subnet("172.16.0.0/12", "Docker bridge network")
    enforcer.add_allowed_subnet("10.0.0.0/8", "Docker compose network")
    enforcer.add_allowed_url_prefix("http://localhost:", "Local HTTP services")
    enforcer.add_allowed_url_prefix("https://localhost:", "Local HTTPS services")
    return enforcer
