"""Simple legal question answering using a keyword-based knowledge base."""
from __future__ import annotations

import json
from pathlib import Path

KB_FILE = Path(__file__).with_name("legal_kb.json")
LOG_FILE = Path(__file__).with_name("unanswered_questions.log")
DISCLAIMER = (
    "This information is for general educational purposes and is not formal legal advice. "
    "Consult a licensed attorney for advice about your specific situation."
)

with KB_FILE.open() as f:
    KNOWLEDGE_BASE: list[dict[str, object]] = json.load(f)

def answer_question(question_text: str) -> str:
    """Return an answer from the knowledge base if keywords match.

    If no match is found, log the question for future expansion and return a
    generic response with a disclaimer.
    """
    query = question_text.lower()
    for entry in KNOWLEDGE_BASE:
        keywords = entry.get("keywords", [])
        if any(kw in query for kw in keywords):
            response = entry.get("response", "")
            return f"{response}\n\n{DISCLAIMER}"

    with LOG_FILE.open("a") as log_file:
        log_file.write(question_text.strip() + "\n")
    return f"I'm sorry, I don't have information on that topic.\n\n{DISCLAIMER}"
