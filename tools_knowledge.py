"""MemPalace tools — knowledge graph tools.

Extracted from monolithic __init__.py during Phase 0 refactoring.
"""

from __future__ import annotations

import json

from pathlib import Path


class KnowledgeMixin:
    """Mixin providing knowledge graph tools.

    Must be used alongside MempalaceMemoryProvider which provides:
    - self._collection, self._palace_path, self._kg
    - self._ensure_palace(), self._is_noise()
    - self._parse_natural_fact(), self._compress_aaak()
    - self._load_noise_patterns(), self._save_noise_patterns()
    - self._taxonomy_cache, self._default_wing, etc.
    """

    # ── Knowledge Graph tools ──────────────────────────────

    def _tool_kg_query(self, args: dict) -> str:
        if not self._kg:
            return json.dumps({"error": "Knowledge graph not available"})
        try:
            entity = args.get("entity", "")
            as_of = args.get("as_of")
            results = self._kg.query_entity(entity, as_of=as_of)
            return json.dumps({"entity": entity, "results": results})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_kg_add(self, args: dict) -> str:
        if not self._kg:
            return json.dumps({"error": "Knowledge graph not available"})
        try:
            subject = args.get("subject", "")
            predicate = args.get("predicate", "")
            obj = args.get("object", "")
            valid_from = args.get("valid_from")
            self._kg.add_triple(subject, predicate, obj, valid_from=valid_from)
            return json.dumps({"result": "Triple added"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_kg_invalidate(self, args: dict) -> str:
        if not self._kg:
            return json.dumps({"error": "Knowledge graph not available"})
        try:
            subject = args.get("subject", "")
            predicate = args.get("predicate", "")
            obj = args.get("object", "")
            ended = args.get("ended")
            self._kg.invalidate(subject, predicate, obj, ended=ended)
            return json.dumps({"result": "Triple invalidated"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_kg_timeline(self, args: dict) -> str:
        if not self._kg:
            return json.dumps({"error": "Knowledge graph not available"})
        try:
            entity = args.get("entity", "")
            timeline = self._kg.timeline(entity)
            return json.dumps({"entity": entity, "timeline": timeline})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_kg_stats(self) -> str:
        if not self._kg:
            return json.dumps({"error": "Knowledge graph not available"})
        try:
            stats = self._kg.stats()
            return json.dumps({"stats": stats})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_kg_explore(self, args: dict) -> str:
        if not self._kg:
            return json.dumps({"error": "Knowledge graph not available"})
        try:
            entity = args.get("entity", "")
            direction = args.get("direction", "both")
            depth = args.get("depth", 2)
            limit = args.get("limit", 20)

            if not entity:
                return json.dumps({"error": "entity is required"})

            visited = set()
            current_level = [entity]
            results_by_depth = []

            for d in range(1, depth + 1):
                next_level = []
                level_results = []

                for current_entity in current_level:
                    if current_entity in visited:
                        continue
                    visited.add(current_entity)

                    triples = self._kg.query_entity(current_entity)
                    if not triples:
                        triples = []

                    for t in triples[:limit]:
                        t_subject = t.get("subject", "")
                        t_predicate = t.get("predicate", "")
                        t_object = t.get("object", "")

                        if direction in ["out", "both"]:
                            if t_subject == current_entity:
                                level_results.append(
                                    {
                                        "from": current_entity,
                                        "predicate": t_predicate,
                                        "to": t_object,
                                        "direction": "out",
                                    }
                                )
                                next_level.append(t_object)

                        if direction in ["in", "both"]:
                            if t_object == current_entity:
                                level_results.append(
                                    {
                                        "from": t_subject,
                                        "predicate": t_predicate,
                                        "to": current_entity,
                                        "direction": "in",
                                    }
                                )
                                next_level.append(t_subject)

                results_by_depth.append(
                    {
                        "depth": d,
                        "entities": level_results,
                        "count": len(level_results),
                    }
                )

                current_level = list(set(next_level))[:limit]
                if not current_level:
                    break

            return json.dumps(
                {
                    "entity": entity,
                    "direction": direction,
                    "depth": depth,
                    "results": results_by_depth,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_remember_fact(self, args: dict) -> str:
        if not self._kg:
            return json.dumps({"error": "Knowledge graph not available"})
        try:
            fact = args.get("fact", "").strip()
            if not fact:
                return json.dumps({"error": "fact is required"})

            valid_from = args.get("valid_from", "")
            if not valid_from:
                from datetime import datetime

                valid_from = datetime.now().strftime("%Y-%m-%d")

            subject, predicate, obj = self._parse_natural_fact(fact)
            if not subject or not predicate or not obj:
                return json.dumps(
                    {
                        "error": "Could not parse fact. Try patterns like 'X is a Y', 'X lives in Y', 'X works as Y'.",
                        "parsed": {
                            "subject": subject,
                            "predicate": predicate,
                            "object": obj,
                        },
                    }
                )

            self._kg.add_triple(subject, predicate, obj, valid_from=valid_from)
            return json.dumps(
                {
                    "result": "Fact added",
                    "parsed": {
                        "subject": subject,
                        "predicate": predicate,
                        "object": obj,
                    },
                    "valid_from": valid_from,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})