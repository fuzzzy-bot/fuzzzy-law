"""
Write every file generated from the connector's code, so they never drift:

  connector/instructions/system_prompt.txt          the answer rules (English and Georgian)
  connector/instructions/custom_gpt_instructions.txt the rules with a GPT Action's tool names
  connector/skill/georgian-law/SKILL.md              the Claude skill
  connector/openapi.json                             the OpenAPI document for a GPT Action
  docs/send-this.ka.md, docs/send-this.en.md         the "send this to your assistant" message

Run from backend/:  python scripts/write_client_files.py
The tests fail when a committed file differs from what this script writes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.config.settings import settings  # noqa: E402
from app.services.connector_guidance import (  # noqa: E402
    ANSWER_RULES,
    answer_rules_for_actions,
    claude_skill,
    send_this_page,
)

PUBLIC_BASE_URL = "https://law-api.fuzzzycore.com"


def openapi_document() -> dict:
    settings.connector_public_base_url = PUBLIC_BASE_URL
    from app.routes.connector_router import connector_openapi

    return connector_openapi()


def main() -> None:
    files = {
        REPO / "connector" / "instructions" / "system_prompt.txt": ANSWER_RULES,
        REPO / "connector" / "instructions" / "custom_gpt_instructions.txt": (
            answer_rules_for_actions()
        ),
        REPO / "connector" / "skill" / "georgian-law" / "SKILL.md": claude_skill(),
        REPO / "connector" / "openapi.json": (
            json.dumps(openapi_document(), ensure_ascii=False, indent=2) + "\n"
        ),
        REPO / "docs" / "send-this.ka.md": send_this_page("ka"),
        REPO / "docs" / "send-this.en.md": send_this_page("en"),
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != text:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(REPO)}")


if __name__ == "__main__":
    main()
