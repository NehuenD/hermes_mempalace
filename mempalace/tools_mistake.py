"""MemPalace tools — mistake tracking tools.

Extracted from monolithic __init__.py during Phase 0 refactoring.
"""

from __future__ import annotations

import json

from pathlib import Path


class MistakeMixin:
    """Mixin providing mistake tracking tools.

    Must be used alongside MempalaceMemoryProvider which provides:
    - self._collection, self._palace_path, self._kg
    - self._ensure_palace(), self._is_noise()
    - self._parse_natural_fact(), self._compress_aaak()
    - self._load_noise_patterns(), self._save_noise_patterns()
    - self._taxonomy_cache, self._default_wing, etc.
    """

    # ── Mistake tracking tools ──────────────────────────────

    def _tool_record_mistake(self, args: dict) -> str:
        """DEPRECATED: Use mempalace_learn with category="mistake" instead."""
        content = args.get("content", "")
        domain = args.get("domain", "general")
        severity = args.get("severity", "MED")
        error_type = args.get("error_type", "runtime")
        title = f"[MISTAKE] {domain}: {content[:50]}"
        return self._tool_learn({
            "content": content,
            "category": "mistake",
            "domain": domain,
            "severity": severity,
            "error_type": error_type,
            "title": title,
        })
    def _tool_distill_mistake(self, args: dict) -> str:
        """DEPRECATED: Use mempalace_update(drawer_id=..., mode="distill") instead."""
        # Thin wrapper — delegates to the unified update tool
        return self._tool_update({
            "drawer_id": args.get("drawer_id", ""),
            "mode": "distill",
            "closet": args.get("closet", ""),
        })