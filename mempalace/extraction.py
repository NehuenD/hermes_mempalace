"""
LLM-based strategy/failure extraction from session trajectories.

Extracts transferable strategies (successes) and lessons (failures)
from agent session trajectories, storing them in wing_reasoningbank.
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

STRATEGY_SCHEMA = {
    "type": "object",
    "properties": {
        "strategy": {
            "type": "string",
            "description": "Concise strategy statement (1-2 sentences)",
        },
        "domain": {
            "type": "string",
            "description": "Domain this applies to (e.g., 'debugging', 'api-design', 'testing')",
        },
        "context": {"type": "string", "description": "When this strategy applies"},
        "rationale": {"type": "string", "description": "Why this strategy works"},
        "confidence": {"type": "number", "description": "Confidence 0.0-1.0"},
        "type": {"type": "string", "enum": ["strategy", "lesson"]},
    },
}

LESSON_SCHEMA = {
    "type": "object",
    "properties": {
        "lesson": {
            "type": "string",
            "description": "Concise lesson statement (1-2 sentences)",
        },
        "domain": {"type": "string"},
        "trigger": {"type": "string", "description": "What should trigger this lesson"},
        "prevention": {"type": "string", "description": "How to prevent this issue"},
        "confidence": {"type": "number"},
        "type": {"type": "string", "enum": ["strategy", "lesson"]},
    },
}

EXTRACTION_SYSTEM_PROMPT = """You analyze AI agent trajectories to extract transferable strategies.
Given a session trajectory (conversation + tool calls), identify:

1. **Strategies** — generalizable approaches that worked well. 
   These must be abstract and NOT reference specific websites, URLs, queries, or unrepeatable context.
   Bad: "Used curl to check example.com/api/status"
   Good: "When debugging API responses, verify endpoint health with a direct HTTP call before deeper investigation"

2. **Lessons** — preventative insights from failures.
   Bad: "Don't use user.id = 5 in the test"
   Good: "Hardcoded test IDs cause cascade failures — use factories or fixtures instead"

Output as JSON array of objects matching the schema above."""


def extract_strategies_from_trajectory(trajectory_text: str, llm_call_fn=None) -> list:
    """
    Given a session trajectory text, use LLM to extract strategies and lessons.

    Args:
        trajectory_text: Full session conversation text
        llm_call_fn: Optional async function(prompt, system_prompt) -> str.
                     If None, returns mock/sample data.

    Returns:
        list of dicts matching STRATEGY_SCHEMA / LESSON_SCHEMA
    """
    if llm_call_fn is None:
        logger.info("No llm_call_fn provided, returning sample extraction")
        return _sample_extraction()

    prompt = f"Extract strategies and lessons from this session trajectory:\n\n{trajectory_text}"

    try:
        result = llm_call_fn(prompt, system_prompt=EXTRACTION_SYSTEM_PROMPT)
        parsed = json.loads(result)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict) and "strategies" in parsed:
            return parsed["strategies"]
        return [parsed]
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Extraction parsing failed: {e}")
        return []


def _sample_extraction() -> list:
    """Return sample extraction for testing."""
    return [
        {
            "strategy": "When diagnosing API failures, start with a direct HTTP probe before inspecting implementation code",
            "domain": "debugging",
            "context": "API debugging sessions",
            "rationale": "Isolates network/auth issues from logic issues first",
            "confidence": 0.85,
            "type": "strategy",
        },
        {
            "lesson": "Hardcoded environment-specific values cause mysterious failures across deployments",
            "domain": "configuration",
            "trigger": "Failure occurs in one environment but not another",
            "prevention": "Use environment variables or config files for environment-specific values",
            "confidence": 0.9,
            "type": "lesson",
        },
    ]


def validate_abstraction(item: dict) -> tuple[bool, str]:
    """
    Validate that an extracted strategy/lesson is sufficiently abstract.

    Returns:
        (is_valid: bool, reason: str)
    """
    content = item.get("strategy") or item.get("lesson", "")

    if re.search(r"https?://[^\s]+", content):
        return False, "Contains specific URL — must be abstract"

    specific_patterns = [
        r"curl\s+https?://",
        r"localhost:\d+",
        r"example\.com",
        r"specific\s+(file|path|user|id)\s+[\"\']?\w+[\"\']?",
    ]
    for pattern in specific_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return False, f"Too specific (matches: {pattern}) — generalize the approach"

    if len(content) < 20:
        return False, "Too short to be informative"

    if content.startswith(("use ", "run ", "type ", "cd ", "open ")):
        return False, "Starts with a specific action — rephrase as general principle"

    return True, ""


def store_extraction(collection, strategies: list, source_session: str):
    """
    Store extracted strategies as drawers in wing_reasoningbank.

    Args:
        collection: ChromaDB collection object
        strategies: list of extracted strategy/lesson dicts
        source_session: Session ID or description for provenance
    """
    import hashlib

    now = datetime.now()
    stored = 0
    rejected = 0

    for item in strategies:
        is_valid, reason = validate_abstraction(item)
        if not is_valid:
            logger.warning(f"Rejected non-abstract strategy: {reason}")
            rejected += 1
            continue

        item_type = item.get("type", "strategy")
        content = item.get("strategy") or item.get("lesson", "")
        domain = item.get("domain", "general")
        confidence = item.get("confidence", 0.5)

        entry_id = f"reasoningbank_{now.strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(content.encode()).hexdigest()[:8]}"

        collection.add(
            ids=[entry_id],
            documents=[json.dumps(item)],
            metadatas=[
                {
                    "wing": "wing_reasoningbank",
                    "room": "room_strategies",
                    "type": item_type,
                    "domain": domain,
                    "confidence": confidence,
                    "source_session": source_session,
                    "extracted_at": now.isoformat(),
                    "date": now.strftime("%Y-%m-%d"),
                }
            ],
        )
        stored += 1
        logger.info(f"Stored {item_type}: {entry_id}")

    return {"stored": stored, "rejected": rejected}
