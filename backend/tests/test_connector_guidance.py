"""
Tests for what the law connector tells the caller's AI: the instructions sent
on connecting, the answer rules in both languages, and the ready-made prompts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.routes.connector_mcp import TOOL_DESCRIPTIONS
from app.services.connector_guidance import (
    ACTION_NAMES,
    ANSWER_RULES,
    ANSWER_RULES_EN,
    ANSWER_RULES_KA,
    PROMPTS,
    SERVER_INSTRUCTIONS,
    answer_rules_for_actions,
    claude_skill,
    render_prompt,
)

INSTRUCTIONS_FILE = (
    Path(__file__).resolve().parents[2] / "connector" / "instructions" / "system_prompt.txt"
)
CONNECTOR_DIR = INSTRUCTIONS_FILE.parents[1]
GPT_INSTRUCTIONS_FILE = CONNECTOR_DIR / "instructions" / "custom_gpt_instructions.txt"
SKILL_FILE = CONNECTOR_DIR / "skill" / "georgian-law" / "SKILL.md"
GPT_INSTRUCTIONS_LIMIT = 8000  # the GPT editor's limit on instructions
GEORGIAN = range(0x10D0, 0x1100)


def _numbered_rules(text: str) -> list[str]:
    return [line for line in text.splitlines() if line[:1].isdigit() and ". " in line[:4]]


class TestServerInstructions:
    def test_short_enough_for_clients_that_cut_long_instructions(self):
        assert len(SERVER_INSTRUCTIONS) <= 2000

    @pytest.mark.parametrize("rule", [
        "Answer only from tool results",
        "never invent articles, paragraphs or case numbers",
        "never promise an outcome",
        "find_legal_aid",
        "Refuse help with breaking the law",
        "legal information, not legal advice",
        "as_of",
    ])
    def test_carries_each_rule(self, rule: str):
        assert rule in " ".join(SERVER_INSTRUCTIONS.split())

    def test_names_only_tools_that_exist(self):
        import re

        named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", SERVER_INSTRUCTIONS)) - {"as_of"}
        assert named and named <= set(TOOL_DESCRIPTIONS)


class TestAnswerRules:
    def test_pasted_instructions_file_is_the_same_text(self):
        assert INSTRUCTIONS_FILE.read_text(encoding="utf-8") == ANSWER_RULES

    def test_both_languages_carry_the_same_number_of_rules(self):
        english, georgian = _numbered_rules(ANSWER_RULES_EN), _numbered_rules(ANSWER_RULES_KA)
        assert len(english) == len(georgian) == 12

    def test_georgian_rules_are_in_georgian(self):
        letters = [ch for ch in ANSWER_RULES_KA if ch.isalpha()]
        assert sum(ord(ch) in GEORGIAN for ch in letters) / len(letters) > 0.6

    @pytest.mark.parametrize("tool", [
        "search_law", "get_article", "list_changes", "find_court_practice",
        "get_court_decision", "get_coverage", "find_legal_aid",
    ])
    def test_each_language_names_the_tool(self, tool: str):
        assert tool in ANSWER_RULES_EN and tool in ANSWER_RULES_KA

    def test_ends_with_the_not_legal_advice_line_in_both_languages(self):
        for rules in (ANSWER_RULES_EN, ANSWER_RULES_KA):
            assert "ეს არის სამართლებრივი ინფორმაცია და არა იურიდიული კონსულტაცია" in rules
            assert "This is legal information, not legal advice." in rules

    def test_a_georgian_answer_ends_in_georgian_only(self):
        for rules in (ANSWER_RULES_EN, ANSWER_RULES_KA):
            assert "კონსულტაცია / This is legal information" not in rules

    def test_unsearched_court_practice_is_left_out_not_announced(self):
        assert "including the remark that you did not look" in ANSWER_RULES_EN
        assert "არც ის, რომ არ მოგიძიებია" in ANSWER_RULES_KA


class TestCustomGptInstructions:
    def test_file_is_the_answer_rules_with_action_names(self):
        assert GPT_INSTRUCTIONS_FILE.read_text(encoding="utf-8") == answer_rules_for_actions()

    def test_fits_the_gpt_editor(self):
        assert len(answer_rules_for_actions()) <= GPT_INSTRUCTIONS_LIMIT

    def test_names_no_tool_the_action_does_not_have(self):
        import json

        spec = json.loads((CONNECTOR_DIR / "openapi.json").read_text(encoding="utf-8"))
        operations = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
        text = answer_rules_for_actions()
        assert set(ACTION_NAMES.values()) <= operations
        assert not [tool for tool in ACTION_NAMES if tool in text]
        assert all(operation in text for operation in ACTION_NAMES.values())


class TestClaudeSkill:
    def test_file_is_the_header_and_the_answer_rules(self):
        text = SKILL_FILE.read_text(encoding="utf-8")
        assert text == claude_skill()
        assert text.endswith(ANSWER_RULES)

    def test_header_names_the_skill_and_when_to_use_it(self):
        header = claude_skill().split("---\n")[1]
        fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
        assert fields["name"] == SKILL_FILE.parent.name == "georgian-law"
        assert "Georgia" in fields["description"] and len(fields["description"]) <= 1024


class TestPrompts:
    def test_every_prompt_names_only_tools_that_exist(self):
        import re

        for name, prompt in PROMPTS.items():
            named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", prompt.template))
            named -= {"as_of", "event_date"}
            assert named <= set(TOOL_DESCRIPTIONS), name

    def test_empty_value_is_marked_as_not_given(self):
        assert "[not given]" in render_prompt("deadline_check", situation="x", event_date="  ")

    def test_every_prompt_closes_with_the_source_rule(self):
        for name in PROMPTS:
            values = {"situation": "x", "document": "y", "event_date": "z"}
            wanted = {k: v for k, v in values.items() if "{" + k + "}" in PROMPTS[name].template}
            assert render_prompt(name, **wanted).endswith(
                "legal information, not legal advice.")
