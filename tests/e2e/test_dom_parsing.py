"""H-Zero — E2E DOM Parsing Test.

Verifies that DOM action parser correctly translates LLM plans into
executable browser commands with valid selectors.
"""

import pytest

from services.agent.dom_actions import DOMActionParser, ParsedAction


class TestDOMParsing:
    """Verify DOM action parser handles all LLM output scenarios."""

    def setup_method(self):
        self.parser = DOMActionParser()

    def test_parse_navigate_url(self):
        """Parse a navigate action with URL."""
        result = self.parser.parse("navigate", "https://example.com")
        assert result.action_type == "navigate"
        assert result.selector_type == "url"
        assert result.target == "https://example.com"

    def test_parse_navigate_auto_prefix(self):
        """Auto-add https:// to bare domains."""
        result = self.parser.parse("navigate", "example.com")
        assert result.target == "https://example.com"
        assert "Added https://" in result.warnings[0]

    def test_parse_click_css(self):
        """Parse click with CSS selector."""
        result = self.parser.parse("click", "#search-btn")
        assert result.action_type == "click"
        assert result.selector_type == "css"

    def test_parse_click_text(self):
        """Parse click with text content."""
        result = self.parser.parse("click", "Submit Finding")
        assert result.action_type == "click"
        assert result.selector_type == "text"

    def test_parse_click_index(self):
        """Parse click by element index."""
        result = self.parser.parse("click", "5")
        assert result.action_type == "click"
        assert result.selector_type == "index"

    def test_parse_type_action(self):
        """Parse type action."""
        result = self.parser.parse("type", "#search-input", "aspirin")
        assert result.action_type == "type"
        assert result.target == "#search-input"
        assert result.value == "aspirin"

    def test_parse_scroll_action(self):
        """Parse scroll action."""
        result = self.parser.parse("scroll", "down", "500")
        assert result.action_type == "scroll"
        assert result.target == "down"

    def test_parse_extract_action(self):
        """Parse extract action."""
        result = self.parser.parse("extract", "page")
        assert result.action_type == "extract"

    def test_parse_wait_action(self):
        """Parse wait action."""
        result = self.parser.parse("wait", "", "3")
        assert result.action_type == "wait"
        assert result.value == "3"

    def test_parse_done_action(self):
        """Parse done action."""
        result = self.parser.parse("done")
        assert result.action_type == "done"

    def test_parse_blocked_action(self):
        """Parse blocked action."""
        result = self.parser.parse("blocked", "", "captcha")
        assert result.action_type == "blocked"

    def test_normalize_llm_aliases(self):
        """Normalize common LLM wordings."""
        aliases = {
            "goto": "navigate",
            "press": "click",
            "tap": "click",
            "input": "type",
            "fill": "type",
            "enter": "type",
            "scrape": "extract",
            "pause": "wait",
            "finish": "done",
        }
        for alias, expected in aliases.items():
            result = self.parser.parse(alias, "test")
            assert result.action_type == expected, f"Alias '{alias}' → expected '{expected}', got '{result.action_type}'"

    def test_unknown_action_falls_back_to_done(self):
        """Unknown actions should fall back to done."""
        result = self.parser.parse("fly_to_moon", "target")
        assert result.action_type == "done"
        assert len(result.warnings) > 0

    def test_build_selector_from_text(self):
        """Build CSS selector from element list using text match."""
        elements = [
            {"tag": "button", "text": "Search", "id": "", "name": ""},
            {"tag": "button", "text": "Submit Finding", "id": "submit-btn", "name": ""},
            {"tag": "a", "text": "Home", "id": "nav-home", "name": ""},
        ]

        # Text match
        selector = self.parser.build_selector(elements, "Search", "text")
        assert selector is not None

        # ID match
        selector = self.parser.build_selector(elements, "Submit Finding", "text")
        assert selector == "#submit-btn"

        # Index match
        selector = self.parser.build_selector(elements, "0", "index")
        assert selector is not None
        assert "nth-of-type" in selector


class TestActionValidation:
    """Verify edge cases in action parsing."""

    def setup_method(self):
        self.parser = DOMActionParser()

    def test_empty_navigate(self):
        result = self.parser.parse("navigate", "")
        assert len(result.warnings) > 0

    def test_empty_click(self):
        result = self.parser.parse("click", "")
        assert len(result.warnings) > 0

    def test_empty_type(self):
        result = self.parser.parse("type", "#input", "")
        assert len(result.warnings) > 0
        assert "No text to type" in result.warnings[0]

    def test_wait_clamping(self):
        """Wait seconds clamped to 1-30."""
        result = self.parser.parse("wait", "", "999")
        assert result.value == "30"

        result = self.parser.parse("wait", "", "0")
        assert result.value == "1"

    def test_scroll_invalid_direction(self):
        result = self.parser.parse("scroll", "left", "300")
        assert result.target == "down"  # Falls back to default

    def test_extract_with_schema(self):
        """Extract with JSON schema in value."""
        schema = '{"title": "string", "count": "number"}'
        result = self.parser.parse("extract", "page", schema)
        assert result.action_type == "extract"
