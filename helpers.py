"""Helper utilities for MemPalace — extracted from monolithic __init__.py."""

from __future__ import annotations

import json as json_lib
import logging
import os
import re
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_DEFAULT_PALACE_PATH = "~/.mempalace/"
_DEFAULT_COLLECTION = "mempalace_drawers"
_DEFAULT_WING = "wing_general"
_DEFAULT_TTL_DAYS = 90


# ---------------------------------------------------------------------------
# Config helpers (module-level, no self needed)
# ---------------------------------------------------------------------------


def load_config() -> dict:
    """Load config from env vars with $HERMES_HOME/.mempalace/config.json overrides.

    Also supports multi-profile via memory.profiles in hermes config.yaml.
    """
    from hermes_constants import get_hermes_home

    config = {
        "palace_path": os.environ.get("MEMPALACE_PATH", _DEFAULT_PALACE_PATH),
        "collection_name": os.environ.get("MEMPALACE_COLLECTION", _DEFAULT_COLLECTION),
        "default_wing": os.environ.get("MEMPALACE_DEFAULT_WING", _DEFAULT_WING),
        "ttl_days": int(os.environ.get("MEMPALACE_TTL_DAYS", _DEFAULT_TTL_DAYS)),
        "reasoning_bank": {
            "enabled": True,
            "provider": None,
            "model": None,
            "consolidation": {
                "similarity_threshold": 0.85,
                "min_confidence": 0.15,
                "max_age_days": 90,
                "max_merges_per_cycle": 5,
            },
        },
    }

    config_path = get_hermes_home() / ".mempalace" / "config.json"
    if config_path.exists():
        try:
            file_cfg = json_lib.loads(config_path.read_text(encoding="utf-8"))
            config.update(
                {k: v for k, v in file_cfg.items() if v is not None and v != ""}
            )
        except Exception:
            pass

    try:
        import yaml

        hermes_config_path = get_hermes_home() / "config.yaml"
        if hermes_config_path.exists():
            hermes_cfg = yaml.safe_load(hermes_config_path.read_text()) or {}
            mem_cfg = hermes_cfg.get("memory", {})
            active_profile = mem_cfg.get("active_profile", "default")
            profiles = mem_cfg.get("profiles", {})

            if active_profile in profiles:
                config["palace_path"] = profiles[active_profile]
            elif profiles:
                config["palace_path"] = profiles.get("default", _DEFAULT_PALACE_PATH)

            config["active_profile"] = active_profile
            config["profiles"] = profiles
    except Exception:
        pass

    return config


def get_palace_path(config: dict) -> Path:
    return Path(os.path.expanduser(config.get("palace_path", _DEFAULT_PALACE_PATH)))


# ---------------------------------------------------------------------------
# Class helper methods (accept self as first param for binding)
# ---------------------------------------------------------------------------


def _detect_room(self, content: str) -> str:
    content_lower = content.lower()
    room_keywords = {
        "auth": ["auth", "login", "oauth", "password", "credential", "session"],
        "api": ["api", "endpoint", "request", "response", "rest", "graphql"],
        "database": ["database", "db", "query", "sql", "schema", "migration"],
        "frontend": ["ui", "component", "react", "vue", "css", "html", "button"],
        "backend": ["server", "backend", "microservice", "api", "route"],
        "deploy": ["deploy", "ci", "cd", "pipeline", "docker", "kubernetes"],
        "bug": ["bug", "error", "issue", "fix", "crash", "exception"],
        "design": ["design", "ui", "ux", "layout", "mockup", "figma"],
        "planning": ["plan", "roadmap", "milestone", "feature", "sprint"],
        "general": [],
    }
    for room, keywords in room_keywords.items():
        if room == "general":
            continue
        if any(kw in content_lower for kw in keywords):
            return room
    return "general"


def _detect_closet(self, content: str) -> str:
    content_lower = content.lower()
    if any(w in content_lower for w in ["decision", "decided", "chose", "choice"]):
        return "hall_facts"
    elif any(w in content_lower for w in ["prefer", "preference", "like", "dislike"]):
        return "hall_preferences"
    elif any(w in content_lower for w in ["discover", "found", "realized", "learned"]):
        return "hall_discoveries"
    elif any(w in content_lower for w in ["help", "advice", "recommend", "suggestion"]):
        return "hall_advice"
    else:
        return "hall_events"


def _is_noise(self, content: str) -> bool:
    """Check if content matches noise patterns that shouldn't be stored."""
    if not self._noise_patterns:
        self._noise_patterns = _load_noise_patterns_path(self._palace_path)
    content_lower = content.lower().strip()
    for pattern in self._noise_patterns:
        if pattern in content_lower:
            return True
    return False


def _parse_natural_fact(self, fact: str) -> tuple:
    fact = fact.strip()
    fact_lower = fact.lower()
    patterns = [
        (r"^(.+) lives in (.+)$", "lives_in"),
        (r"^(.+) works as (.+)$", "works_as"),
        (r"^(.+) is a (.+)$", "is_a"),
        (r"^(.+) is an (.+)$", "is_a"),
        (r"^(.+) is the (.+)$", "is_the"),
        (r"^(.+) has (.+)$", "has"),
        (r"^(.+) loves (.+)$", "loves"),
        (r"^(.+) likes (.+)$", "likes"),
        (r"^(.+) created (.+)$", "created"),
        (r"^(.+) owns (.+)$", "owns"),
        (r"^(.+) knows (.+)$", "knows"),
        (r"^(.+) was born in (.+)$", "born_in"),
        (r"^(.+) is from (.+)$", "is_from"),
        (r"^(.+) uses (.+)$", "uses"),
        (r"^(.+) built (.+)$", "built"),
        (r"^(.+) depends on (.+)$", "depends_on"),
        (r"^(.+) is located in (.+)$", "located_in"),
    ]
    for pattern, predicate in patterns:
        match = re.match(pattern, fact_lower)
        if match:
            subject = match.group(1).strip()
            obj = match.group(2).strip()
            subject = fact[: len(subject)].strip()
            if subject[0].isupper():
                subject = subject[0].upper() + subject[1:]
            return (subject, predicate, obj)
    parts = fact.split()
    if len(parts) >= 3:
        if parts[1].lower() in ["is", "are", "was", "were"]:
            subject = parts[0]
            predicate = parts[1].lower()
            obj = " ".join(parts[2:])
            return (subject, predicate, obj)
    return ("", "", "")


def _compress_aaak(self, content: str) -> str:
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    if not lines:
        return content
    if len(lines) == 1:
        return content
    chunks = []
    current_chunk = []
    current_len = 0
    for line in lines:
        if current_len + len(line) > 80 and current_chunk:
            chunks.append("|".join(current_chunk))
            current_chunk = [line]
            current_len = len(line)
        else:
            current_chunk.append(line)
            current_len += len(line) + 1
    if current_chunk:
        chunks.append("|".join(current_chunk))
    return "\n".join(chunks)


def _load_noise_patterns_path(palace_path: Path | None) -> List[str]:
    """Load noise patterns from config or defaults."""
    default_patterns = [
        "nothing to save",
        "no new memories",
        "no memories to save",
        "no significant memories",
        "nothing new to save",
        "nothing important to save",
        "no information to save",
    ]
    if not palace_path:
        return default_patterns
    config_path = palace_path / "noise_patterns.json"
    if config_path.exists():
        try:
            custom = json_lib.loads(config_path.read_text())
            patterns = custom.get("patterns", [])
            return patterns + [p for p in default_patterns if p not in patterns]
        except Exception:
            pass
    return default_patterns


def _save_noise_patterns_path(patterns: List[str], palace_path: Path | None) -> None:
    """Save noise patterns to config."""
    if not palace_path:
        return
    config_path = palace_path / "noise_patterns.json"
    try:
        config_path.write_text(json_lib.dumps({"patterns": patterns}, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Aliases for __init__.py imports (matching the original class-method names)
# ---------------------------------------------------------------------------

_load_config = load_config
_get_palace_path = get_palace_path


def _load_noise_patterns(self) -> List[str]:
    """Wrapper called from delegating stubs with self."""
    return _load_noise_patterns_path(self._palace_path)


def _save_noise_patterns(self, patterns: List[str]) -> None:
    """Wrapper called from delegating stubs with self."""
    return _save_noise_patterns_path(patterns, self._palace_path)
