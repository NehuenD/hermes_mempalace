"""Write-oriented tools mixin for MemPalace."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from mempalace.helpers import _is_noise, _parse_natural_fact

_DEFAULT_TTL_DAYS = 90


class WriteToolsMixin:
    """Mixin class with write-oriented tool methods for MemPalace."""

    def _tool_add_drawer(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            import uuid
            from datetime import datetime, timedelta

            content = args.get("content", "")
            wing = args.get("wing", self._default_wing)
            room = args.get("room", "general")
            closet = args.get("closet", "hall_general")
            subject = args.get("subject", "")
            flags = args.get("flags", [])

            content = content.strip() if content else ""
            if not content or len(content) < 3:
                return json.dumps(
                    {
                        "result": "skipped",
                        "reason": "content_too_short",
                        "drawer_id": None,
                    }
                )

            if self._is_noise(content):
                return json.dumps(
                    {
                        "result": "skipped",
                        "reason": "noise_filter",
                        "drawer_id": None,
                    }
                )

            expires_at = args.get("expires_at")
            if not expires_at:
                ttl_days = args.get("ttl_days", _DEFAULT_TTL_DAYS)
                if ttl_days > 0:
                    expires_at = (datetime.now() + timedelta(days=ttl_days)).isoformat()

            parent_id = args.get("parent_id")
            metadata = {
                "wing": wing,
                "room": room,
                "closet": closet,
                "subject": subject or "",
                "flags": json.dumps(flags or []),
                "created_at": datetime.now().isoformat(),
                "last_accessed": datetime.now().isoformat(),
            }
            if expires_at:
                metadata["expires_at"] = expires_at
            if parent_id:
                metadata["parent_id"] = parent_id

            doc_id = str(uuid.uuid4())
            self._collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id],
            )
            self._update_taxonomy_cache(wing, room, 1)
            return json.dumps(
                {
                    "result": "Drawer added",
                    "drawer_id": doc_id,
                    "expires_at": expires_at,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_session_write(self, args: dict) -> str:
        """Write a session entry for project tracking across sessions."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})

        try:
            import uuid
            from datetime import datetime

            date = args.get("date", "")
            project = args.get("project", "")
            summary = args.get("summary", "")
            next_task = args.get("next", "")

            if not date:
                date = datetime.now().strftime("%Y-%m-%d")

            aaak_entry = f"SESSION → {date}|{project}|{summary}"
            if next_task:
                aaak_entry += f"|next:{next_task}"

            metadata = {
                "wing": "wing_myos",
                "room": "sessions",
                "closet": "hall_events",
                "session_date": date,
                "session_type": "project_tracking",
                "session_project": project,
            }

            doc_id = str(uuid.uuid4())
            self._collection.add(
                documents=[aaak_entry],
                metadatas=[metadata],
                ids=[doc_id],
            )
            self._update_taxonomy_cache("wing_myos", "sessions", 1)

            return json.dumps(
                {
                    "result": "Session entry written",
                    "drawer_id": doc_id,
                    "date": date,
                    "project": project,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_session_read(self, args: dict) -> str:
        """Read session entries for project context restoration."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})

        try:
            project = args.get("project", "")
            last_n = args.get("last_n", 5)

            where_filter = {"$and": [{"wing": "wing_myos"}, {"room": "sessions"}]}
            if project:
                where_filter["$and"].append({"session_project": project})

            results = self._collection.get(
                where=where_filter,
                include=["metadatas", "documents"],
            )

            items = []
            docs = results.get("documents", []) or []
            metas = results.get("metadatas", []) or []

            for i, doc in enumerate(docs):
                meta = metas[i] if i < len(metas) else {}
                items.append(
                    {
                        "session": doc,
                        "date": meta.get("session_date", ""),
                        "project": meta.get("session_project", ""),
                    }
                )

            items.sort(key=lambda x: x["date"], reverse=True)
            items = items[:last_n]

            return json.dumps({"sessions": items, "count": len(items)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_remember(self, args: dict) -> str:
        """Remember tool - extracts structured memories using mempalace's general_extractor.

        Uses LLM-free pattern matching to extract decisions, preferences, milestones,
        problems, and emotional moments. Naturally deduplicates by extracting the
        ESSENCE rather than storing raw conversation.
        """
        if not self._ensure_palace():
            return json.dumps(
                {"error": "Palace not initialized. Run: mempalace init <dir>"}
            )

        try:
            import uuid
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.general_extractor import extract_memories

            content = args.get("content", "")

            if not content:
                return json.dumps({"error": "content is required"})

            if self._is_noise(content):
                return json.dumps(
                    {
                        "result": "skipped",
                        "reason": "noise_filter",
                        "drawer_id": None,
                    }
                )

            extracted = extract_memories(content)

            if not extracted:
                closet_map = {
                    "preference": "hall_preferences",
                    "decision": "hall_facts",
                    "milestone": "hall_discoveries",
                    "problem": "hall_discoveries",
                    "emotional": "hall_events",
                }

                room = "general"
                closet = "hall_events"
                category = args.get("category", "")
                content_lower = content.lower()

                if category in closet_map:
                    room = category
                    closet = closet_map[category]
                elif any(
                    w in content_lower for w in ["prefer", "like", "dislike", "favor"]
                ):
                    room = "preferences"
                    closet = "hall_preferences"
                elif any(
                    w in content_lower for w in ["decided", "chose", "decision", "will"]
                ):
                    room = "decisions"
                    closet = "hall_facts"
                elif any(
                    w in content_lower for w in ["works on", "responsible", "owns"]
                ):
                    room = "people"
                    closet = "hall_facts"

                doc_id = str(uuid.uuid4())
                self._collection.add(
                    documents=[content],
                    metadatas=[
                        {
                            "wing": self._default_wing,
                            "room": room,
                            "closet": closet,
                        }
                    ],
                    ids=[doc_id],
                )
                return json.dumps(
                    {
                        "result": "Remembered",
                        "drawer_id": doc_id,
                        "room": room,
                        "closet": closet,
                        "extracted": False,
                    }
                )

            room_map = {
                "preference": ("preferences", "hall_preferences"),
                "decision": ("decisions", "hall_facts"),
                "milestone": ("milestones", "hall_discoveries"),
                "problem": ("problems", "hall_discoveries"),
                "emotional": ("emotional", "hall_events"),
            }

            stored = []
            kg_stored = []
            for chunk in extracted:
                memory_type = chunk.get("memory_type", "general")
                room, closet = room_map.get(memory_type, ("general", "hall_events"))

                doc_id = str(uuid.uuid4())
                self._collection.add(
                    documents=[chunk["content"]],
                    metadatas=[
                        {
                            "wing": self._default_wing,
                            "room": room,
                            "closet": closet,
                            "memory_type": memory_type,
                        }
                    ],
                    ids=[doc_id],
                )
                stored.append({"type": memory_type, "drawer_id": doc_id})

                if self._kg and memory_type in ["fact", "preference", "decision"]:
                    try:
                        subject, predicate, obj = self._parse_natural_fact(
                            chunk["content"]
                        )
                        if subject and predicate and obj:
                            self._kg.add_triple(subject, predicate, obj)
                            kg_stored.append(
                                {
                                    "subject": subject,
                                    "predicate": predicate,
                                    "object": obj,
                                }
                            )
                    except Exception:
                        pass

            result = {
                "result": "Remembered",
                "extracted": True,
                "memories": stored,
                "count": len(stored),
            }
            if kg_stored:
                result["kg_triples"] = kg_stored
                result["kg_count"] = len(kg_stored)

            return json.dumps(result)

        except ImportError:
            return json.dumps(
                {
                    "error": "general_extractor not available, falling back to raw storage",
                    "fallback": True,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_delete_drawer(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            drawer_id = args.get("drawer_id", "")
            self._collection.delete(ids=[drawer_id])
            self._build_taxonomy_cache()
            return json.dumps({"result": "Drawer deleted"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_learn(self, args: dict) -> str:
        """File new knowledge with auto-detection."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            auto_detect = args.get("auto_detect", False)
            content = args.get("content", "")
            title = args.get("title", "")
            description = args.get("description", "")
            subject = args.get("subject", "")
            predicate = args.get("predicate", "")
            category = args.get("category", "fact")
            closet = args.get("closet", "personal")
            source_session = args.get("source_session", "")

            domain = args.get("domain", "general")
            severity = args.get("severity", "MED")
            error_type = args.get("error_type", "runtime")
            is_mistake = category == "mistake"

            if is_mistake:
                wing = "wing_mistakes"
                room = f"room_{domain}"
                closet = "hall_errors"
                entity_code = f"{domain.upper()[:4]}_{len(content)}"
                formatted_content = f"{entity_code} → {domain}|mistake|{content}|error_type:{error_type},severity:{severity}"
                content_to_store = formatted_content
            else:
                wing = "wing_myos"
                room = "learnings"
                closet = args.get("closet", "personal")
                content_to_store = content

            if is_mistake and self._kg:
                self._kg.add_triple(
                    entity_code,
                    "mistake",
                    content,
                    valid_from=datetime.now().isoformat(),
                )

            if auto_detect and content:
                import sys

                _plugin_dir = Path(__file__).parent / "mempalace"
                if str(_plugin_dir) not in sys.path:
                    sys.path.insert(0, str(_plugin_dir))
                from searcher import search_memories

                SIMILARITY_THRESHOLD = 0.85

                try:
                    recall_results = search_memories(
                        content,
                        palace_path=str(self._palace_path / "palace"),
                        n_results=10,
                        closet=closet or "",
                        category=category or "",
                        subject=subject or "",
                    )
                    raw_results = (
                        recall_results.get("results", [])
                        if isinstance(recall_results, dict)
                        else recall_results
                    )
                except Exception:
                    raw_results = []

                candidates = []
                for r in raw_results:
                    sim = r.get("similarity", r.get("distance", 0))
                    if sim > SIMILARITY_THRESHOLD:
                        candidates.append(
                            {
                                "id": r.get("id", ""),
                                "content": r.get("text", r.get("content", "")),
                                "subject": r.get("subject", ""),
                                "closet": r.get("closet", ""),
                                "category": r.get("category", ""),
                                "flags": r.get("flags", []),
                                "similarity_score": sim,
                            }
                        )

                if candidates:
                    return json.dumps(
                        {
                            "match_found": True,
                            "candidates": candidates,
                            "action": "update|correct|extend|skip",
                            "message": f"Similar learnings found (best sim={candidates[0]['similarity_score']:.2f}). Review candidates before updating.",
                        }
                    )

            metadata = {
                "wing": wing,
                "room": room,
                "closet": closet,
                "category": category,
                "subject": subject,
                "predicate": predicate,
                "title": title,
                "source_session": source_session,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if is_mistake:
                metadata["domain"] = domain
                metadata["severity"] = severity
                metadata["error_type"] = error_type

            drawer_id = str(uuid.uuid4())
            self._collection.add(
                ids=[drawer_id],
                documents=[content_to_store],
                metadatas=[metadata],
            )

            result = {
                "drawer_id": drawer_id,
                "title": title,
                "subject": subject,
                "closet": closet,
                "category": category,
                "stored": True,
            }
            if is_mistake:
                result["domain"] = domain
                result["severity"] = severity
                result["error_type"] = error_type
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_update(self, args: dict) -> str:
        """Modify existing learning entry."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            from datetime import datetime, timezone

            drawer_id = args.get("drawer_id", "")
            mode = args.get("mode", "replace")
            content = args.get("content", "")
            extend_with = args.get("extend_with", "")
            title = args.get("title", "")
            description = args.get("description", "")

            if not drawer_id:
                return json.dumps({"error": "drawer_id required"})

            existing = self._collection.get(
                ids=[drawer_id],
                include=["documents", "metadatas"],
            )
            docs = existing.get("documents", [])
            metas = existing.get("metadatas", [])

            if not docs:
                return json.dumps({"error": "Drawer not found"})

            old_content = docs[0]
            old_meta = metas[0] if metas else {}

            predicate = old_meta.get("predicate", "value")
            subject = old_meta.get("subject", "?")

            new_content = content
            if mode == "extend":
                new_content = old_content + "\n---\n" + extend_with

            if mode == "distill":
                domain = old_meta.get("domain", "general")
                error_type = old_meta.get("error_type", "general")
                analysis = self._run_distillation_analysis(
                    old_content, domain, error_type
                )
                if "error" in analysis:
                    return json.dumps(analysis)

                root_cause = analysis["root_cause"]
                lesson = analysis["lesson"]
                counterfactual = analysis["counterfactual"]
                related_concepts = analysis["related_concepts"]
                improvement_score = analysis["improvement_score"]

                domain_code = domain.upper()[:4]
                new_content = (
                    f"LESSON → {domain_code}_{drawer_id[:8]}|mistake-distill|"
                    f"root:{root_cause}|lesson:{lesson}|counterfactual:{counterfactual}|"
                    f"concepts:{','.join(related_concepts)}|score:{improvement_score}/5"
                )

                new_meta = dict(old_meta)
                new_meta["parent_id"] = drawer_id
                new_meta["root_cause"] = root_cause
                new_meta["lesson"] = lesson
                new_meta["counterfactual"] = counterfactual
                new_meta["related_concepts"] = related_concepts
                new_meta["improvement_score"] = improvement_score
                new_meta["distilled"] = True
                new_meta["created_at"] = datetime.now(timezone.utc).isoformat()
                new_meta["last_accessed"] = ""

                new_drawer_id = str(uuid.uuid4())
                self._collection.add(
                    ids=[new_drawer_id],
                    documents=[new_content],
                    metadatas=[new_meta],
                )

                extra_closet = args.get("closet", "")
                extra_drawer_id = None
                if old_meta.get("wing") == "wing_mistakes" and extra_closet in (
                    "personal",
                    "projects",
                    "world",
                ):
                    extra_drawer_id = str(uuid.uuid4())
                    extra_doc = (
                        f"LESSON → {domain_code}|lesson|{lesson}|"
                        f"root_cause:{root_cause}|from_mistake:{drawer_id[:8]}"
                    )
                    extra_meta = {
                        "wing": "wing_general",
                        "room": "learnings",
                        "closet": extra_closet,
                        "parent_id": drawer_id,
                        "lesson_id": new_drawer_id,
                        "domain": domain,
                        "subject": domain,
                        "improvement_score": improvement_score,
                        "distilled_from": "distill_mistake",
                    }
                    self._collection.add(
                        documents=[extra_doc],
                        metadatas=[extra_meta],
                        ids=[extra_drawer_id],
                    )
                    self._update_taxonomy_cache("wing_general", "learnings", 1)

                if self._kg:
                    self._kg.add_triple(
                        f"MISTAKE_{drawer_id[:8]}",
                        "distilled_to_lesson",
                        lesson,
                        valid_from=datetime.now(timezone.utc).isoformat(),
                    )
                    self._kg.add_triple(
                        new_drawer_id[:8],
                        "root_cause",
                        root_cause,
                        valid_from=datetime.now(timezone.utc).isoformat(),
                    )

                return json.dumps(
                    {
                        "new_drawer_id": new_drawer_id,
                        "parent_id": drawer_id,
                        "root_cause": root_cause,
                        "lesson": lesson,
                        "counterfactual": counterfactual,
                        "related_concepts": related_concepts,
                        "improvement_score": improvement_score,
                        "extra_drawer_id": extra_drawer_id,
                        "mode": "distill",
                    }
                )

            if mode in ("replace", "correct"):
                flags = old_meta.get("flags", [])
                if "correction" not in flags:
                    flags.append("correction")

                self._tool_kg_add(
                    {
                        "subject": subject,
                        "predicate": f"had_{predicate}",
                        "object": old_content[:200],
                    }
                )

                new_meta = dict(old_meta)
                new_meta["parent_id"] = drawer_id
                new_meta["flags"] = flags
                new_meta["corrected_to"] = ""
                new_meta["last_accessed"] = ""
                new_meta["created_at"] = datetime.now(timezone.utc).isoformat()
            else:
                new_meta = dict(old_meta)

            if title:
                new_meta["title"] = title
            if description:
                new_meta["description"] = description

            new_drawer_id = str(uuid.uuid4())
            self._collection.add(
                ids=[new_drawer_id],
                documents=[new_content],
                metadatas=[new_meta],
            )

            if mode in ("replace", "correct") and new_meta.get("parent_id"):
                self._collection.update(
                    ids=[drawer_id],
                    metadatas=[{"corrected_to": new_drawer_id}],
                )

            return json.dumps(
                {
                    "new_drawer_id": new_drawer_id,
                    "parent_id": drawer_id,
                    "mode": mode,
                    "kg_triple_added": mode in ("replace", "correct"),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _run_distillation_analysis(
        self, content: str, domain: str, error_type: str
    ) -> dict:
        """Run LLM analysis on any content to extract structured lessons."""
        import re as _re

        analysis_prompt = (
            "You are a rigorous post-mortem analyst. Given recorded content, "
            "produce a deep structural analysis. Return ONLY valid JSON with these exact keys:\n"
            "{\n"
            '  "root_cause": "...",\n'
            '  "lesson": "...",\n'
            '  "counterfactual": "...",\n'
            '  "related_concepts": ["...", "..."],\n'
            '  "improvement_score": N\n'
            "}\n\n"
            "Rules:\n"
            "- root_cause: the fundamental reason this failed or underperformed (not just what happened)\n"
            "- lesson: the actionable takeaway — what you should do differently\n"
            "- counterfactual: what would have happened if the lesson had been applied\n"
            "- related_concepts: 2-4 relevant topic tags (e.g. 'filter-syntax', 'chromadb', 'error-handling')\n"
            "- improvement_score: 1-5, how actionable/transferable is this lesson\n"
            "- Return ONLY the JSON. No markdown fences. No explanation.\n\n"
            f"CONTENT: {content}\n"
            f"DOMAIN: {domain}\n"
            f"ERROR TYPE: {error_type}\n"
        )

        from hermes_tools import terminal

        result = terminal(
            command=(
                f'python3 -c "\n'
                f"import json, sys\n"
                f"from anthropic import Anthropic\n"
                f"client = Anthropic()\n"
                f"msg = client.messages.create(\n"
                f"    model='claude-opus-4-7-20251120',\n"
                f"    max_tokens=1024,\n"
                f"    messages=[{{'role': 'user', 'content': {repr(analysis_prompt)}}}]"
                f")\n"
                f"print(msg.content[0].text)\n"
                f'"'
            ),
            timeout=30,
        )

        raw = result.get("output", "").strip()

        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0].strip()
        first_brace = json_str.find("{")
        if first_brace > 0:
            json_str = json_str[first_brace:]

        try:
            analysis = json.loads(json_str)
        except Exception:
            return {"error": f"Failed to parse LLM analysis response: {raw[:500]}"}

        return {
            "root_cause": analysis.get("root_cause", "unknown"),
            "lesson": analysis.get("lesson", "unknown"),
            "counterfactual": analysis.get("counterfactual", "unknown"),
            "related_concepts": analysis.get("related_concepts", []),
            "improvement_score": int(analysis.get("improvement_score", 3)),
        }
