"""Read-oriented MemPalace tools — extracted from monolithic __init__.py."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReadToolsMixin:
    """Mixin for read-only MemPalace tools.

    Must be used alongside MempalaceMemoryProvider which provides:
    - self._palace_path
    - self._collection
    - self._collection_name
    - self._ensure_palace()
    - self._taxonomy_cache
    - self._noise_patterns
    - self._default_wing
    - self._query_embeddings
    - Self._default_ttl_days
    - self._use_aaak
    - etc.
    """

    def _tool_status(self) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            count = self._collection.count()
            return json.dumps(
                {
                    "total_drawers": count,
                    "palace_path": str(self._palace_path),
                    "collection": self._collection_name,
                    "status": "ok",
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_list_wings(self, args: dict = None) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            args = args or {}
            offset = args.get("offset", 0)
            limit = args.get("limit", 50)
            all_data = self._collection.get(include=["metadatas"])
            wings = {}
            for m in all_data.get("metadatas", []):
                w = m.get("wing", "unknown")
                wings[w] = wings.get(w, 0) + 1
            sorted_wings = sorted(wings.items(), key=lambda x: -x[1])
            total = len(sorted_wings)
            paginated = sorted_wings[offset : offset + limit]
            return json.dumps(
                {
                    "wings": dict(paginated),
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_list_rooms(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            wing = args.get("wing", "")
            offset = args.get("offset", 0)
            limit = args.get("limit", 50)
            results = self._collection.get(
                where={"wing": wing} if wing else None, include=["metadatas"]
            )
            rooms = {}
            for m in results.get("metadatas", []):
                r = m.get("room", "unknown")
                rooms[r] = rooms.get(r, 0) + 1
            sorted_rooms = sorted(rooms.items(), key=lambda x: -x[1])
            total = len(sorted_rooms)
            paginated = sorted_rooms[offset : offset + limit]
            return json.dumps(
                {
                    "wing": wing,
                    "rooms": dict(paginated),
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_get_taxonomy(self, args: dict = None) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            args = args or {}
            offset = args.get("offset", 0)
            limit = args.get("limit", 100)
            taxonomy = dict(self._taxonomy_cache)
            all_entries = []
            for wing, rooms in taxonomy.items():
                for room, count in rooms.items():
                    all_entries.append({"wing": wing, "room": room, "count": count})
            total = len(all_entries)
            paginated = all_entries[offset : offset + limit]
            return json.dumps(
                {
                    "taxonomy": taxonomy,
                    "entries": paginated,
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_search(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from searcher import search_memories

            query = args.get("query", "")
            wing = args.get("wing")
            room = args.get("room")
            offset = args.get("offset", 0)
            limit = args.get("limit", 10)
            results = search_memories(
                collection=self._collection,
                query=query,
                wing=wing,
                room=room,
                offset=offset,
                limit=limit,
                embeddings=self._query_embeddings,
            )
            return json.dumps(
                {
                    "results": results,
                    "total": len(results),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_check_duplicate(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            content = args.get("content", "")
            wing = args.get("wing")
            if not content:
                return json.dumps({"duplicate": False, "reason": "no_content"})
            where_clause = {}
            if wing:
                where_clause["wing"] = wing
            all_data = self._collection.get(
                where=where_clause if where_clause else None,
                include=["documents", "metadatas"],
            )
            docs = all_data.get("documents", []) or []
            metas = all_data.get("metadatas", []) or []
            content_lower = content.lower().strip()
            for i, doc in enumerate(docs):
                if doc and doc.lower().strip() == content_lower:
                    meta = metas[i] if i < len(metas) else {}
                    return json.dumps(
                        {
                            "duplicate": True,
                            "existing_id": all_data.get("ids", [""])[i]
                            if i < len(all_data.get("ids", []))
                            else None,
                            "existing_wing": meta.get("wing"),
                            "existing_room": meta.get("room"),
                        }
                    )
            return json.dumps({"duplicate": False})
        except Exception as e:
            return json.dumps({"error": str(e), "duplicate": False})

    def _tool_get_aaak_spec(self) -> str:
        return json.dumps(
            {
                "spec": "AAAK",
                "version": "1.0",
                "description": (
                    "AAAK (Advanced Agentic Archive for Knowledge) is a compressed "
                    "shorthand format for storing memories in MemPalace. Use pipes to "
                    "separate fields: SUBJECT|predicate|object|source_session"
                ),
            }
        )

    def _tool_recall(self, args: dict) -> str:
        """Access learnings with semantic similarity and filters."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            from datetime import datetime, timezone
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from searcher import search_memories

            query = args.get("query", "") or args.get("similarity", "")
            subject = args.get("subject", "")
            closet = args.get("closet", "")
            category = args.get("category", "")
            flag = args.get("flag", [])
            limit = args.get("limit", 1)
            offset = args.get("offset", 0)

            limit = min(max(1, limit), 10)
            n_to_fetch = (offset + limit) * 5

            try:
                results = search_memories(
                    query,
                    palace_path=str(self._palace_path / "palace"),
                    n_results=n_to_fetch,
                    closet=closet,
                    category=category,
                    subject=subject,
                )
                raw_results = (
                    results.get("results", []) if isinstance(results, dict) else results
                )
            except Exception:
                raw_results = []

            items = []

            # Phase 2: include mistakes in results when category is "mistake"
            if category == "mistake":
                try:
                    mistake_results = self._collection.get(
                        where={"wing": {"$eq": "wing_mistakes"}},
                        include=["documents", "metadatas", "ids"],
                    )
                    m_docs = mistake_results.get("documents", []) or []
                    m_metas = mistake_results.get("metadatas", []) or []
                    m_ids = mistake_results.get("ids", []) or []
                    for i, meta in enumerate(m_metas):
                        items.append(
                            {
                                "id": m_ids[i] if i < len(m_ids) else "",
                                "content": m_docs[i] if i < len(m_docs) else "",
                                "subject": meta.get("subject", ""),
                                "closet": meta.get("closet", ""),
                                "category": meta.get("category", ""),
                                "flags": json.loads(meta.get("flags", "[]"))
                                if isinstance(meta.get("flags", []), str)
                                and meta.get("flags", "").startswith("[")
                                else meta.get("flags", []),
                                "created_at": meta.get("created_at", ""),
                                "similarity_score": 1.0,
                            }
                        )
                except Exception:
                    pass
            else:
                for r in raw_results:
                    r_closet = r.get("closet", "")
                    r_category = r.get("category", "")
                    r_subject = r.get("subject", "")
                    r_flags = (
                        json.loads(r.get("flags", "[]"))
                        if isinstance(r.get("flags", []), str)
                        and r.get("flags", "").startswith("[")
                        else r.get("flags", [])
                    )

                    if closet and r_closet != closet:
                        continue
                    if category and r_category != category:
                        continue
                    if subject and r_subject != subject:
                        continue
                    if flag:
                        if isinstance(flag, list):
                            if not any(f in r_flags for f in flag):
                                continue
                        elif flag not in r_flags:
                            continue

                    items.append(
                        {
                            "id": r.get("id", ""),
                            "content": r.get("text", r.get("content", "")),
                            "subject": r_subject,
                            "closet": r_closet,
                            "category": r_category,
                            "flags": r_flags,
                            "created_at": r.get("created_at", ""),
                            "similarity_score": r.get(
                                "similarity", r.get("distance", 0)
                            ),
                        }
                    )

            total = len(items)
            paginated = items[offset : offset + limit]

            now_iso = datetime.now(timezone.utc).isoformat()
            for item in paginated:
                item_id = item.get("id", "")
                if item_id:
                    self._collection.update(
                        ids=[item_id],
                        metadatas=[{"last_accessed": now_iso}],
                    )

            return json.dumps(
                {
                    "results": paginated,
                    "count": len(paginated),
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                }
            )
        except ImportError:
            return json.dumps({"error": "mempalace searcher not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_recall_all(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            closet = args.get("closet", "")
            cap = min(int(args.get("cap", 20)), 100)
            sort = args.get("sort", "recent")
            category = args.get("category", "")

            where_clause = {}
            and_clauses = []
            if closet:
                and_clauses.append({"closet": closet})
            if category:
                and_clauses.append({"category": category})
            if and_clauses:
                where_clause["$and"] = and_clauses

            results = self._collection.get(
                where=where_clause if where_clause else None,
                include=["documents", "metadatas"],
            )
            ids = results.get("ids", []) or []
            docs = results.get("documents", []) or []
            metas = results.get("metadatas", []) or []

            items = []
            for i in range(len(ids)):
                meta = metas[i] if i < len(metas) else {}
                doc = docs[i] if i < len(docs) else ""
                items.append(
                    {
                        "id": ids[i],
                        "content": doc,
                        "metadata": meta,
                    }
                )

            # Sort
            reverse = True
            if sort == "accessed":
                items.sort(
                    key=lambda x: x["metadata"].get("last_accessed", ""),
                    reverse=reverse,
                )
            elif sort == "recent":
                items.sort(
                    key=lambda x: x["metadata"].get("created_at", ""), reverse=reverse
                )
            # relevance sort needs a query, skip

            return json.dumps(
                {
                    "items": items[:cap],
                    "total": len(items),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_drawer_history(self, args: dict) -> str:
        """Get all versions of a drawer by following parent_id chain."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            drawer_id = args.get("drawer_id", "")
            limit = args.get("limit", 20)

            if not drawer_id:
                return json.dumps({"error": "drawer_id required"})

            versions = []
            current_id = drawer_id
            version_num = 1

            while current_id and version_num <= limit:
                result = self._collection.get(
                    ids=[current_id],
                    include=["documents", "metadatas"],
                )
                docs = result.get("documents", [])
                metas = result.get("metadatas", [])

                if not docs:
                    break

                versions.append(
                    {
                        "id": current_id,
                        "content": docs[0],
                        "metadata": metas[0] if metas else {},
                        "version_num": version_num,
                    }
                )

                parent_id = metas[0].get("parent_id", "") if metas else ""
                current_id = parent_id
                version_num += 1

            if not versions:
                return json.dumps({"error": "Drawer not found"})

            versions.sort(key=lambda x: x.get("version_num", 0), reverse=True)

            return json.dumps(
                {
                    "drawer_id": drawer_id,
                    "versions": versions[:limit],
                    "count": len(versions),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
