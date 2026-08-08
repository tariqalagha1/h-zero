"""H-Zero — DOM Action Parser.

Parses and validates DOM actions from LLM plans into executable browser commands.
Translates between natural-language descriptions and precise selectors.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedAction:
    """A parsed and validated DOM action ready for execution."""
    action_type: str  # navigate, click, type, scroll, extract, wait, done
    target: str = ""            # URL, CSS selector, text to click, or action name
    value: str = ""             # input text, scroll amount, wait seconds
    selector_type: str = ""     # css, text, index, url, none
    confidence: float = 0.5
    raw_plan: str = ""
    warnings: list[str] = field(default_factory=list)


class DOMActionParser:
    """Validates and normalizes DOM actions from LLM output.

    Translates fuzzy LLM outputs into precise, executable browser commands.
    Handles common LLM mistakes: wrong selector format, ambiguous targets,
    action type mismatches.
    """

    VALID_ACTIONS = {"navigate", "click", "type", "scroll", "extract", "wait", "done", "blocked"}

    def parse(self, action_type: str, target: str = "", value: str = "",
              plan_context: str = "") -> ParsedAction:
        """Parse and validate an action from LLM output."""
        action_type = action_type.lower().strip() if action_type else ""

        # Normalize action type
        action_type = self._normalize_action(action_type)
        if action_type not in self.VALID_ACTIONS:
            return ParsedAction(
                action_type="done",
                target="",
                selector_type="none",
                confidence=0.0,
                warnings=[f"Unknown action type: {action_type}"],
                raw_plan=plan_context,
            )

        # Parse based on action type
        parsed = ParsedAction(
            action_type=action_type,
            target=target,
            value=value,
            raw_plan=plan_context,
        )

        if action_type == "navigate":
            parsed = self._parse_navigate(parsed)
        elif action_type == "click":
            parsed = self._parse_click(parsed)
        elif action_type == "type":
            parsed = self._parse_type(parsed)
        elif action_type == "scroll":
            parsed = self._parse_scroll(parsed)
        elif action_type == "extract":
            parsed = self._parse_extract(parsed)
        elif action_type == "wait":
            parsed = self._parse_wait(parsed)
        elif action_type == "done":
            parsed.selector_type = "none"
        elif action_type == "blocked":
            parsed.selector_type = "none"

        return parsed

    def _normalize_action(self, action: str) -> str:
        """Normalize common LLM action wordings."""
        mapping = {
            "goto": "navigate",
            "go to": "navigate",
            "open": "navigate",
            "visit": "navigate",
            "press": "click",
            "tap": "click",
            "select": "click",
            "choose": "click",
            "input": "type",
            "fill": "type",
            "enter": "type",
            "write": "type",
            "type in": "type",
            "scroll down": "scroll",
            "scroll up": "scroll",
            "page down": "scroll",
            "get data": "extract",
            "scrape": "extract",
            "read": "extract",
            "pause": "wait",
            "sleep": "wait",
            "finish": "done",
            "complete": "done",
            "stop": "done",
            "return": "done",
        }
        return mapping.get(action, action)

    def _parse_navigate(self, p: ParsedAction) -> ParsedAction:
        """Parse a navigate action target."""
        target = p.target.strip()
        if not target:
            p.warnings.append("No URL provided for navigation")
            return p

        # Add https:// if missing
        if not target.startswith(("http://", "https://")):
            if "." in target:
                target = f"https://{target}"
                p.warnings.append(f"Added https:// prefix: {target}")

        p.target = target
        p.selector_type = "url"
        return p

    def _parse_click(self, p: ParsedAction) -> ParsedAction:
        """Parse a click action target into a selector."""
        target = p.target.strip()
        if not target:
            p.warnings.append("No click target specified")
            return p

        # Detect selector type
        if target.startswith(("#", ".", "[", "a[", "button", "input", "div", "span")):
            p.selector_type = "css"
        elif target.isdigit():
            p.selector_type = "index"
        elif re.match(r"^https?://", target):
            p.selector_type = "url"
        else:
            p.selector_type = "text"

        return p

    def _parse_type(self, p: ParsedAction) -> ParsedAction:
        """Parse a type action."""
        if not p.target:
            p.warnings.append("No input field specified")
        if not p.value:
            p.warnings.append("No text to type")
        p.selector_type = "css" if p.target.startswith(("#", ".")) else "text"
        return p

    def _parse_scroll(self, p: ParsedAction) -> ParsedAction:
        """Parse a scroll action."""
        direction = p.target.lower().strip() if p.target else "down"
        if direction not in ("up", "down", "top", "bottom"):
            direction = "down"
        p.target = direction
        p.value = p.value or "300"
        p.selector_type = "none"
        return p

    def _parse_extract(self, p: ParsedAction) -> ParsedAction:
        """Parse an extract action."""
        p.target = p.target or "page"
        p.selector_type = "none"

        # Try to parse extraction schema from value
        if p.value:
            try:
                schema = json.loads(p.value) if isinstance(p.value, str) else p.value
                if isinstance(schema, dict):
                    p.value = json.dumps(schema)
                    p.warnings.append("Extraction schema parsed successfully")
            except (json.JSONDecodeError, TypeError):
                p.warnings.append("Could not parse extraction schema")

        return p

    def _parse_wait(self, p: ParsedAction) -> ParsedAction:
        """Parse a wait action."""
        try:
            seconds = int(p.value) if p.value else 2
            p.value = str(max(1, min(seconds, 30)))  # Clamp 1-30
        except ValueError:
            p.value = "2"
        p.selector_type = "none"
        return p

    def build_selector(self, elements: list[dict], target: str,
                       selector_type: str = "text") -> Optional[str]:
        """Build a CSS selector from interactive element metadata."""
        if selector_type == "css":
            return target
        if selector_type == "index":
            try:
                idx = int(target)
                if 0 <= idx < len(elements):
                    el = elements[idx]
                    if el.get("id"):
                        return f"#{el['id']}"
                    return f"{el['tag']}:nth-of-type({idx + 1})"
            except (ValueError, IndexError):
                pass
            return None

        # Text matching
        if selector_type == "text" and target:
            target_lower = target.lower()
            for el in elements:
                el_text = (el.get("text", "") or "").lower()
                if target_lower in el_text:
                    if el.get("id"):
                        return f"#{el['id']}"
                    if el.get("name"):
                        return f"[name='{el['name']}']"
            # Fallback: use text content selector
            escaped = target.replace("'", "\\'")
            return f"text='{escaped}'"

        return None
