"""Palace hygiene review tool — finds stale, duplicate, or room-specific content for user review.

Key constraint: FINAL decision is always the user. No auto-pruning.
This tool surfaces candidates; the user decides what to keep or delete.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .bootstrap import ensure_local_imports

ensure_local_imports()

logger = logging.getLogger(__name__)


class HygieneMixin:
    """Mixin for palace hygiene review tools.

    Must be used alongside MempalaceMemoryProvider which provides:
    - self._collection
    - self._collection_name
    - self._ensure_palace()
    """

    def _tool_review(self, args: dict) -> str:
        """Find content review candidates — stale, duplicate, or room-specific.

        Surfaces candidates with previews for the user to decide on.
        No content is ever auto-deleted.
        """
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})

        try:
            mode = args.get("mode", "stale")
            wing = args.get("wing", "")
            room = args.get("room", "")
            days = int(args.get("days", 30))
            limit = int(args.get("limit", 50))

            all_data = self._collection.get(
                include=["documents", "metadatas"],
            )

            docs = all_data.get("documents", []) or []
            metas = all_data.get("metadatas", []) or []
            ids = all_data.get("ids", []) or []

            candidates = []

            for i in range(len(ids)):
                meta = metas[i] if i < len(metas) else {}
                doc = docs[i] if i < len(docs) else ""

                # Apply wing/room filter
                if wing and meta.get("wing", "") != wing:
                    continue
                if room and meta.get("room", "") != room:
                    continue

                d_id = ids[i]
                created_at = meta.get("created_at", "")
                last_accessed = meta.get("last_accessed", "")
                expires_at = meta.get("expires_at", "")
                r_wing = meta.get("wing", "")
                r_room = meta.get("room", "")
                r_closet = meta.get("closet", "")
                flags = meta.get("flags", [])
                if isinstance(flags, str):
                    try:
                        flags = json.loads(flags)
                    except (json.JSONDecodeError, TypeError):
                        flags = []

                now = datetime.now(timezone.utc)

                candidate = {
                    "id": d_id,
                    "preview": (doc[:160] + "...") if doc and len(doc) > 160 else (doc or ""),
                    "wing": r_wing,
                    "room": r_room,
                    "closet": r_closet,
                    "created_at": created_at,
                    "last_accessed": last_accessed,
                    "flags": flags,
                    "reasons": [],
                }

                if mode in ("stale", "all"):
                    # Stale: not accessed in N days
                    if last_accessed:
                        try:
                            last_dt = datetime.fromisoformat(last_accessed)
                            days_since = (now - last_dt).days
                            if days_since >= days:
                                candidate["reasons"].append(
                                    f"stale (not accessed in {days_since}d)"
                                )
                        except (ValueError, TypeError):
                            pass
                    elif created_at:
                        # No last_accessed means never explicitly accessed
                        try:
                            created_dt = datetime.fromisoformat(created_at)
                            days_since = (now - created_dt).days
                            if days_since >= days:
                                candidate["reasons"].append(
                                    f"stale (never accessed, created {days_since}d ago)"
                                )
                        except (ValueError, TypeError):
                            pass
                    else:
                        # No timestamps at all — old orphan
                        candidate["reasons"].append("stale (no timestamps)")

                if mode in ("duplicates", "all"):
                    # Check for similar content based on document length match + content overlap
                    doc_lower = (doc or "").lower().strip()
                    if doc_lower and len(doc_lower) > 20:
                        for j in range(i + 1, len(ids)):
                            other_doc = docs[j] if j < len(docs) else ""
                            other_doc_lower = (other_doc or "").lower().strip()
                            if not other_doc_lower or len(other_doc_lower) <= 20:
                                continue

                            # Same-content check: exact match or significant overlap
                            if doc_lower == other_doc_lower:
                                candidate["reasons"].append("duplicate (exact match)")
                                # Also flag the other one
                                o_meta = metas[j] if j < len(metas) else {}
                                break
                            elif (len(doc_lower) > 50 and len(other_doc_lower) > 50 and
                                  (doc_lower in other_doc_lower or other_doc_lower in doc_lower)):
                                candidate["reasons"].append("duplicate (contained within)")
                                break

                if candidate["reasons"]:
                    candidates.append(candidate)

                if len(candidates) >= limit:
                    break

            # Sort by reasons count (most reasons first), then by staleness
            def _sort_key(c):
                last = c.get("last_accessed") or c.get("created_at") or ""
                # Make sort stable: stale-first, then most reasons
                return (-len(c.get("reasons", [])), last)

            candidates.sort(key=_sort_key)

            return json.dumps(
                {
                    "mode": mode,
                    "total_candidates": len(candidates),
                    "max_shown": limit,
                    "candidates": candidates,
                    "note": "Use mempalace_delete_drawer to remove, mempalace_set_drawer_flags to tag. No auto-pruning — you decide.",
                },
                indent=2,
            )

        except Exception as e:
            logger.warning("Palace review failed: %s", e)
            return json.dumps({"error": str(e)})
