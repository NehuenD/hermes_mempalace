"""MemPalace tools — meta/utility tools.

Extracted from monolithic __init__.py during Phase 0 refactoring.
"""

from __future__ import annotations

import json

from pathlib import Path


class MetaToolsMixin:
    """Mixin providing meta/utility tools.

    Must be used alongside MempalaceMemoryProvider which provides:
    - self._collection, self._palace_path, self._kg
    - self._ensure_palace(), self._is_noise()
    - self._parse_natural_fact(), self._compress_aaak()
    - self._load_noise_patterns(), self._save_noise_patterns()
    - self._taxonomy_cache, self._default_wing, etc.
    """

    # ── Meta/Utility tools ─────────────────────────────────

    def _tool_get_versions(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            drawer_id = args.get("drawer_id", "")
            limit = args.get("limit", 20)

            if not drawer_id:
                return json.dumps({"error": "drawer_id is required"})

            results = self._collection.get(ids=[drawer_id])
            docs = results.get("documents", []) or []
            metas = results.get("metadatas", []) or []
            ids = results.get("ids", []) or []

            if not ids:
                return json.dumps({"error": "Drawer not found"})

            versions = []
            current_id = drawer_id

            while current_id and len(versions) < limit:
                results = self._collection.get(ids=[current_id])
                d = results.get("documents", []) or []
                m = results.get("metadatas", []) or []
                i = results.get("ids", []) or []

                if not i:
                    break

                doc = d[0] if d else ""
                meta = m[0] if m else {}
                versions.append(
                    {
                        "drawer_id": i[0],
                        "document": doc[:100] + "..." if len(doc) > 100 else doc,
                        "parent_id": meta.get("parent_id", ""),
                        "created_at": meta.get("created_at", ""),
                    }
                )

                current_id = meta.get("parent_id", "")

            versions.reverse()
            return json.dumps(
                {
                    "drawer_id": drawer_id,
                    "versions": versions,
                    "count": len(versions),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_preview_aaak(self, args: dict) -> str:
        content = args.get("content", "")
        if not content:
            return json.dumps({"error": "content is required"})

        try:
            aaak_preview = self._compress_aaak(content)
            original_len = len(content)
            compressed_len = len(aaak_preview)
            ratio = original_len / compressed_len if compressed_len > 0 else 0

            return json.dumps(
                {
                    "original": content,
                    "aaak": aaak_preview,
                    "original_length": original_len,
                    "compressed_length": compressed_len,
                    "compression_ratio": round(ratio, 2),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_set_drawer_flags(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            drawer_id = args.get("drawer_id", "")
            flags = args.get("flags", [])
            mode = args.get("mode", "set")

            if not drawer_id:
                return json.dumps({"error": "drawer_id is required"})

            results = self._collection.get(ids=[drawer_id])
            existing = results.get("metadatas", [])
            if not existing:
                return json.dumps({"error": "Drawer not found"})

            existing_meta = existing[0]
            existing_flags = existing_meta.get("flags", "")
            current_flags = existing_flags.split(",") if existing_flags else []

            if mode == "set":
                new_flags = flags
            elif mode == "add":
                new_flags = list(set(current_flags + flags))
            elif mode == "remove":
                new_flags = [f for f in current_flags if f not in flags]
            else:
                new_flags = flags

            new_meta = dict(existing_meta)
            new_meta["flags"] = ",".join(new_flags)

            self._collection.update(
                ids=[drawer_id],
                metadatas=[new_meta],
            )

            return json.dumps(
                {
                    "result": "Flags updated",
                    "drawer_id": drawer_id,
                    "flags": new_flags,
                    "mode": mode,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_watch(self, args: dict) -> str:
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            import hashlib
            import uuid

            query = args.get("query", "")
            wing = args.get("wing")
            room = args.get("room")
            watch_id = args.get("watch_id")
            limit = args.get("limit", 10)

            where_filter = None
            if wing and room:
                where_filter = {"$and": [{"wing": wing}, {"room": room}]}
            elif wing:
                where_filter = {"wing": wing}
            elif room:
                where_filter = {"room": room}

            if not watch_id:
                watch_id = str(uuid.uuid4())

            try:
                import sys

                _plugin_dir = Path(__file__).parent / "mempalace"
                if str(_plugin_dir) not in sys.path:
                    sys.path.insert(0, str(_plugin_dir))
                from searcher import search_memories

                n_to_fetch = limit * 5
                results = search_memories(
                    query,
                    palace_path=str(self._palace_path / "palace"),
                    n_results=n_to_fetch,
                )
                raw_results = (
                    results.get("results", []) if isinstance(results, dict) else results
                )
            except Exception:
                raw_results = []

            items = []
            for r in raw_results:
                r_wing = r.get("wing", "")
                r_room = r.get("room", "")
                if wing and r_wing != wing:
                    continue
                if room and r_room != room:
                    continue
                content = r.get("text", r.get("content", ""))
                content_hash = hashlib.md5(content.encode()).hexdigest()[:12]
                items.append(
                    {
                        "drawer_id": r.get("id", ""),
                        "content": content[:200],
                        "content_hash": content_hash,
                        "wing": r_wing,
                        "room": r_room,
                    }
                )

            total = len(items)
            current_ids = set(i["drawer_id"] for i in items[:limit])

            stored = self._watch_cache.get(watch_id, {})
            previous_ids = stored.get("drawer_ids", set())
            added = current_ids - previous_ids
            removed = previous_ids - current_ids

            self._watch_cache[watch_id] = {
                "query": query,
                "wing": wing,
                "room": room,
                "drawer_ids": current_ids,
                "timestamp": str(uuid.uuid4()),
            }

            return json.dumps(
                {
                    "watch_id": watch_id,
                    "results": items[:limit],
                    "count": len(items[:limit]),
                    "total": total,
                    "changes": {
                        "added": len(added),
                        "removed": len(removed),
                        "added_ids": list(added)[:5],
                        "removed_ids": list(removed)[:5],
                    },
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_summarize(self, args: dict) -> str:
        """Summarize the palace - wings, rooms, counts, oldest/newest."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})

        try:
            wing = args.get("wing")
            room = args.get("room")
            full_mode = args.get("full", False)
            limit = args.get("limit", 20)

            # Fast path: use cache for counts when no filtering needed
            if not full_mode and not wing and not room:
                taxonomy = dict(self._taxonomy_cache)
                wing_counts = {w: sum(taxonomy[w].values()) for w in taxonomy}
                total = sum(wing_counts.values())
                wings_list = [
                    {"name": w, "drawers": c}
                    for w, c in sorted(wing_counts.items(), key=lambda x: -x[1])
                ]
                return json.dumps(
                    {
                        "total_drawers": total,
                        "wings": wings_list,
                        "taxonomy": taxonomy,
                        "palace_path": str(self._palace_path),
                        "from_cache": True,
                    }
                )

            # Full scan path: for filtered queries or full_mode
            where_filter = {}
            if wing:
                where_filter["wing"] = wing
            if room:
                where_filter["room"] = room

            all_data = self._collection.get(
                where=where_filter if where_filter else None,
                include=["metadatas", "documents"] if full_mode else ["metadatas"],
            )

            metadatas = all_data.get("metadatas", []) or []
            documents = all_data.get("documents", []) if full_mode else []

            taxonomy = {}
            wing_counts = {}
            oldest_ts = None
            newest_ts = None

            for m in metadatas:
                w = m.get("wing", "unknown")
                r = m.get("room", "unknown")
                ts = m.get("created_at", "")

                wing_counts[w] = wing_counts.get(w, 0) + 1
                if w not in taxonomy:
                    taxonomy[w] = {}
                taxonomy[w][r] = taxonomy[w].get(r, 0) + 1

                if ts:
                    if oldest_ts is None or ts < oldest_ts:
                        oldest_ts = ts
                    if newest_ts is None or ts > newest_ts:
                        newest_ts = ts

            total = len(metadatas)
            wings_list = [
                {"name": w, "drawers": c}
                for w, c in sorted(wing_counts.items(), key=lambda x: -x[1])
            ]

            result = {
                "total_drawers": total,
                "wings": wings_list,
                "taxonomy": taxonomy,
                "oldest_drawer": oldest_ts,
                "newest_drawer": newest_ts,
                "palace_path": str(self._palace_path),
                "from_cache": False,
            }

            if full_mode and documents:
                samples = []
                for doc in documents[:limit]:
                    samples.append(doc[:200] if doc else "")
                result["samples"] = samples

            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_profile_list(self) -> str:
        """List all MemPalace profiles."""
        try:
            profiles = {}
            default_path = Path(os.path.expanduser(_DEFAULT_PALACE_PATH))
            hermes_home = Path.home() / ".hermes"

            if hermes_home.exists():
                config_path = hermes_home / "config.yaml"
                if config_path.exists():
                    import yaml

                    config_data = yaml.safe_load(config_path.read_text()) or {}
                    mem_cfg = config_data.get("memory", {})
                    profile_cfg = mem_cfg.get("profiles", {})
                    active = mem_cfg.get("active_profile", "default")

                    for name, path in profile_cfg.items():
                        p = Path(os.path.expanduser(path))
                        if p.exists():
                            chroma_path = p / "palace" / "chroma.sqlite3"
                            if chroma_path.exists():
                                import sqlite3

                                try:
                                    count = (
                                        sqlite3.connect(str(chroma_path))
                                        .execute("SELECT COUNT(*) FROM embeddings")
                                        .fetchone()[0]
                                    )
                                    profiles[name] = {
                                        "path": str(p),
                                        "drawers": count,
                                        "active": name == active,
                                    }
                                except Exception:
                                    profiles[name] = {
                                        "path": str(p),
                                        "drawers": 0,
                                        "active": name == active,
                                    }

            if not profiles:
                default_path = Path(os.path.expanduser(_DEFAULT_PALACE_PATH))
                if default_path.exists():
                    chroma_path = default_path / "palace" / "chroma.sqlite3"
                    if chroma_path.exists():
                        import sqlite3

                        try:
                            count = (
                                sqlite3.connect(str(chroma_path))
                                .execute("SELECT COUNT(*) FROM embeddings")
                                .fetchone()[0]
                            )
                            profiles["default"] = {
                                "path": str(default_path),
                                "drawers": count,
                                "active": True,
                            }
                        except Exception:
                            pass

            if not profiles:
                profiles["default"] = {
                    "path": str(default_path),
                    "drawers": 0,
                    "active": True,
                }

            return json.dumps({"profiles": profiles})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_profile_switch(self, args: dict) -> str:
        """Switch to a different profile."""
        name = args.get("name", "")
        if not name:
            return json.dumps({"error": "Profile name required"})

        try:
            hermes_home = Path.home() / ".hermes"
            config_path = hermes_home / "config.yaml"

            if not config_path.exists():
                return json.dumps({"error": "Config not found"})

            import yaml

            config_data = yaml.safe_load(config_path.read_text()) or {}
            mem_cfg = config_data.get("memory", {})
            profiles = mem_cfg.get("profiles", {})

            if name not in profiles:
                profiles[name] = f"~/.mempalace_{name}/"

            profile_path = Path(os.path.expanduser(profiles[name]))
            if profile_path.exists():
                test_col_path = profile_path / "palace" / "chroma.sqlite"
                if not test_col_path.exists():
                    return json.dumps(
                        {"error": f"Invalid profile: {name} is not a valid MemPalace"}
                    )

            elif not profile_path.exists():
                profile_path.mkdir(parents=True, exist_ok=True)
                (profile_path / "palace").mkdir(parents=True, exist_ok=True)

            mem_cfg["active_profile"] = name

            if "memory" not in config_data:
                config_data["memory"] = mem_cfg
            else:
                config_data["memory"] = mem_cfg

            config_path.write_text(yaml.dump(config_data))

            self._config = _load_config()
            self._palace_path = _get_palace_path(self._config)

            self._chroma_client = None
            self._collection = None
            self._ensure_palace()

            return json.dumps(
                {
                    "result": "Switched",
                    "profile": name,
                    "palace_path": str(self._palace_path),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_sweep(self, args: dict) -> str:
        """Manually trigger expired drawer sweep."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            self._sweep_expired_drawers()
            return json.dumps({"result": "sweep_completed"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_noise_filter(self, args: dict) -> str:
        """Manage noise filter patterns."""
        mode = args.get("mode", "list")
        pattern = args.get("pattern", "").lower().strip()

        patterns = self._load_noise_patterns()

        if mode == "list":
            return json.dumps({"patterns": patterns, "count": len(patterns)})

        if mode == "add":
            if not pattern:
                return json.dumps({"error": "Pattern required for add mode"})
            if pattern in patterns:
                return json.dumps({"error": "Pattern already exists"})
            patterns.append(pattern)
            self._save_noise_patterns(patterns)
            self._noise_patterns = patterns
            return json.dumps({"result": "Pattern added", "pattern": pattern})

        if mode == "remove":
            if not pattern:
                return json.dumps({"error": "Pattern required for remove mode"})
            if pattern not in patterns:
                return json.dumps({"error": "Pattern not found"})
            patterns.remove(pattern)
            self._save_noise_patterns(patterns)
            self._noise_patterns = patterns
            return json.dumps({"result": "Pattern removed", "pattern": pattern})

        return json.dumps({"error": "Invalid mode"})
    def _tool_expiring(self, args: dict) -> str:
        """Preview drawers about to TTL-expire."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            from datetime import datetime, timedelta, timezone

            days_ahead = args.get("days_ahead", 7)
            wing = args.get("wing")
            room = args.get("room")
            rescue = args.get("rescue", False)
            ttl_days = args.get("ttl_days", 90)

            cutoff = (
                datetime.now(timezone.utc) + timedelta(days=days_ahead)
            ).isoformat()

            where_filter = {}
            if wing:
                where_filter["wing"] = wing
            if room:
                where_filter["room"] = room

            results = self._collection.get(
                where=where_filter if where_filter else None,
                include=["documents", "metadatas"],
            )

            expiring = []
            docs = results.get("documents", []) or []
            metas = results.get("metadatas", []) or []
            ids = results.get("ids", []) or []

            for i, meta in enumerate(metas):
                expires_at = meta.get("expires_at", "")
                if not expires_at:
                    continue
                if expires_at > cutoff:
                    continue
                r_wing = meta.get("wing", "")
                r_room = meta.get("room", "")
                if wing and r_wing != wing:
                    continue
                if room and r_room != room:
                    continue
                expiring.append(
                    {
                        "drawer_id": ids[i] if i < len(ids) else "",
                        "document": docs[i] if i < len(docs) else "",
                        "expires_at": expires_at,
                        "wing": r_wing,
                        "room": r_room,
                        "closet": meta.get("closet", ""),
                    }
                )

            if rescue and expiring:
                new_expiry = (
                    datetime.now(timezone.utc) + timedelta(days=ttl_days)
                ).isoformat()
                ids_to_update = [
                    meta.get("id", "")
                    for meta in metas
                    if meta.get("expires_at", "") in [e["expires_at"] for e in expiring]
                ]
                for doc_id in ids_to_update:
                    if doc_id:
                        self._collection.update(
                            ids=[doc_id],
                            metadatas=[{"expires_at": new_expiry}],
                        )
                return json.dumps(
                    {
                        "rescued": len(ids_to_update),
                        "new_expires_at": new_expiry,
                        "expiring": expiring,
                    }
                )

            return json.dumps(
                {"expiring": expiring, "count": len(expiring), "cutoff": cutoff}
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_backup(self, args: dict) -> str:
        """Export palace drawers and KG to JSON."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            import uuid
            from datetime import datetime
            from pathlib import Path

            backup_path = args.get("path")
            include_kg = args.get("include_kg", True)

            if not backup_path:
                stamp = datetime.now().strftime("%Y%m%d")
                backup_path = self._palace_path / "backups" / f"backup_{stamp}.json"
            else:
                backup_path = Path(backup_path).expanduser()

            backup_path.parent.mkdir(parents=True, exist_ok=True)

            all_data = self._collection.get(include=["documents", "metadatas", "ids"])
            drawers = []
            docs = all_data.get("documents", []) or []
            metas = all_data.get("metadatas", []) or []
            ids = all_data.get("ids", []) or []

            for i, doc in enumerate(docs):
                meta = metas[i] if i < len(metas) else {}
                drawers.append(
                    {
                        "id": ids[i] if i < len(ids) else str(uuid.uuid4()),
                        "document": doc,
                        "metadata": meta,
                    }
                )

            backup = {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "drawers": drawers,
                "kg_triples": [],
            }

            if include_kg and self._kg:
                try:
                    all_triples = self._kg.get_all_triples()
                    backup["kg_triples"] = all_triples
                except Exception as e:
                    logger.debug("Failed to backup KG: %s", e)

            with open(backup_path, "w") as f:
                json.dump(backup, f, indent=2)

            return json.dumps(
                {
                    "result": "Backup created",
                    "path": str(backup_path),
                    "drawers": len(drawers),
                    "kg_triples": len(backup.get("kg_triples", [])),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_restore(self, args: dict) -> str:
        """Restore palace from JSON backup."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            from pathlib import Path

            backup_path = Path(args.get("path", "")).expanduser()
            clear_first = args.get("clear_first", False)
            include_kg = args.get("include_kg", True)

            if not backup_path or not backup_path.exists():
                return json.dumps({"error": f"Backup file not found: {backup_path}"})

            with open(backup_path) as f:
                backup = json.load(f)

            drawers = backup.get("drawers", [])
            kg_triples = backup.get("kg_triples", [])

            if clear_first:
                try:
                    all_ids = [d["id"] for d in drawers]
                    if all_ids:
                        self._collection.delete(ids=all_ids)
                except Exception as e:
                    logger.debug("Failed to clear collection: %s", e)

            added = 0
            for d in drawers:
                try:
                    self._collection.add(
                        documents=[d.get("document", "")],
                        metadatas=[d.get("metadata", {})],
                        ids=[d.get("id", str(uuid.uuid4()))],
                    )
                    added += 1
                except Exception:
                    pass

            kg_restored = 0
            if include_kg and kg_triples and self._kg:
                try:
                    for triple in kg_triples:
                        self._kg.add_triple(
                            triple.get("subject", ""),
                            triple.get("predicate", ""),
                            triple.get("object", ""),
                            valid_from=triple.get("valid_from"),
                        )
                        kg_restored += 1
                except Exception as e:
                    logger.debug("Failed to restore KG: %s", e)

            return json.dumps(
                {
                    "result": "Restored",
                    "drawers_restored": added,
                    "kg_triples_restored": kg_restored,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_session_diff(self, args: dict) -> str:
        """Show what changed between sessions."""
        if not self._ensure_palace():
            return json.dumps({"error": "Palace not initialized"})
        try:
            project = args.get("project", "")
            before_date = args.get("before_date", "")
            after_date = args.get("after_date", "")

            forget_filter = args.get("forget_filter", True)
            new_filter = args.get("new_filter", True)

            forget_conditions = [{"wing": "wing_myos"}, {"room": "sessions"}]
            if forget_filter and project:
                forget_conditions.append({"session_project": project})
            if forget_filter and before_date:
                forget_conditions.append({"session_date": {"$lte": before_date}})
            if forget_filter and after_date:
                forget_conditions.append({"session_date": {"$gte": after_date}})
            forget_where = (
                {"$and": forget_conditions}
                if len(forget_conditions) > 1
                else forget_conditions[0]
            )

            new_conditions = [{"wing": "wing_myos"}, {"room": "sessions"}]
            if new_filter and project:
                new_conditions.append({"session_project": project})
            if new_filter and before_date:
                new_conditions.append({"session_date": {"$lte": before_date}})
            if new_filter and after_date:
                new_conditions.append({"session_date": {"$gte": after_date}})
            new_where = (
                {"$and": new_conditions}
                if len(new_conditions) > 1
                else new_conditions[0]
            )

            forget_results = self._collection.get(
                where=forget_where, include=["metadatas"]
            )
            new_results = self._collection.get(where=new_where, include=["metadatas"])

            if not before_date and not after_date:
                all_metas = forget_results.get("metadatas", []) + new_results.get(
                    "metadatas", []
                )
                dated = [
                    (m.get("session_date", ""), m)
                    for m in all_metas
                    if m.get("session_date")
                ]
                dated.sort(key=lambda x: x[0])
                half = len(dated) // 2
                older_dates = {d for d, m in dated[:half]} if half > 0 else set()
                newer_dates = {d for d, m in dated[half:]} if half > 0 else set()
                forget_metas = [
                    m for m in all_metas if m.get("session_date") in older_dates
                ]
                new_metas = [
                    m for m in all_metas if m.get("session_date") in newer_dates
                ]
                forget_results = {"metadatas": forget_metas}
                new_results = {"metadatas": new_metas}

            forget_projects = {
                m.get("session_project")
                for m in forget_results.get("metadatas", [])
                if m.get("session_project")
            }
            new_projects = {
                m.get("session_project")
                for m in new_results.get("metadatas", [])
                if m.get("session_project")
            }

            added_projects = new_projects - forget_projects
            removed_projects = forget_projects - new_projects

            added = [
                m
                for m in new_results.get("metadatas", [])
                if m.get("session_project") in added_projects
            ]
            removed = [
                m
                for m in forget_results.get("metadatas", [])
                if m.get("session_project") in removed_projects
            ]

            return json.dumps(
                {
                    "project": project,
                    "added": added,
                    "removed": removed,
                    "count": len(added) + len(removed),
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})