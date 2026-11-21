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
    SEND_THIS_EN,
    SEND_THIS_KA,
    SERVER_INSTRUCTIONS,
    WORK_RULES,
    answer_rules_for_actions,
    claude_skill,
    render_prompt,
    send_this_page,
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

        fields = {"as_of", "also_searched", "decisions_through", "version_date",
                  "data_current_as_of", "none_found"}
        named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", SERVER_INSTRUCTIONS)) - fields
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

    def test_unsearched_court_practice_is_left_out(self):
        assert "If you did not look court practice up, leave it out." in ANSWER_RULES_EN
        assert "თუ პრაქტიკა არ მოგიძიებია, პასუხში არ ახსენო." in ANSWER_RULES_KA

    def test_one_rule_for_no_decision_found_everywhere(self):
        line = ("I found no published decision on this in the collections this service "
                "holds, up to <decisions_through>; this does not mean none exists.")
        assert line in SERVER_INSTRUCTIONS and line in ANSWER_RULES_EN and line in SEND_THIS_EN
        assert "ეს არ ნიშნავს, რომ ასეთი არ არსებობს" in ANSWER_RULES_KA
        assert "ეს არ ნიშნავს, რომ ასეთი არ არსებობს" in SEND_THIS_KA
        court_tool = " ".join(TOOL_DESCRIPTIONS["find_court_practice"].split())
        assert "does not mean none exists" in court_tool
        for text in (SERVER_INSTRUCTIONS, ANSWER_RULES, SEND_THIS_EN, SEND_THIS_KA):
            assert "must not mention court practice" not in text
            assert "including the remark that you did not look" not in text

    @pytest.mark.parametrize("phrase", [
        "give 112 first", "also_searched", "on or before that day", "whole article",
        "violence", "version_date", "data_current_as_of", "word for word",
        "ეს არის სამართლებრივი ინფორმაცია და არა იურიდიული კონსულტაცია.",
        "This is legal information, not legal advice.",
    ])
    def test_server_instructions_carry_the_essential_answer_rules(self, phrase: str):
        assert phrase in " ".join(SERVER_INSTRUCTIONS.split())

    def test_past_dates_are_not_promised_as_the_wording_in_force(self):
        for text in (SERVER_INSTRUCTIONS, ANSWER_RULES_EN, TOOL_DESCRIPTIONS["get_article"]):
            flat = " ".join(text.split())
            assert "stood on that day" not in flat
            assert "on or before that day" in flat


class TestSendThis:
    def test_both_languages_carry_the_same_rules(self):
        english, georgian = _numbered_rules(SEND_THIS_EN), _numbered_rules(SEND_THIS_KA)
        assert len(english) == len(georgian) == len(WORK_RULES)

    def test_georgian_message_is_in_georgian(self):
        letters = [ch for ch in SEND_THIS_KA if ch.isalpha()]
        assert sum(ord(ch) in GEORGIAN for ch in letters) / len(letters) > 0.6

    def test_message_is_built_from_the_server_rules(self):
        for english, _ in WORK_RULES:
            assert english in SERVER_INSTRUCTIONS and english in SEND_THIS_EN

    @pytest.mark.parametrize("language", ["ka", "en"])
    def test_committed_page_is_the_generated_one(self, language: str):
        page = CONNECTOR_DIR.parent / "docs" / f"send-this.{language}.md"
        assert page.read_text(encoding="utf-8") == send_this_page(language)
        assert "https://law-api.fuzzzycore.com/mcp" in page.read_text(encoding="utf-8")


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
