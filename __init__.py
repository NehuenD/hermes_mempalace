"""MemPalace memory plugin — MemoryProvider interface.

Local-first AI memory system with palace structure (Wings/Rooms/Closets/Drawers),
AAAK compression dialect (30x lossless), and 96.6% recall on LongMemEval benchmark.

Config via environment variables or $HERMES_HOME/.mempalace/config.json:
    MEMPALACE_PATH        — Palace directory (default: ~/.mempalace/)
    MEMPALACE_COLLECTION  — ChromaDB collection name (default: mempalace_drawers)
    MEMPALACE_DEFAULT_WING — Default wing (default: wing_general)

Or via $HERMES_HOME/.mempalace/config.json.

Tools (19 total):
    READ:       status, list_wings, list_rooms, get_taxonomy, search,
                check_duplicate, get_aaak_spec
    WRITE:      add_drawer, delete_drawer
    KNOWLEDGE G: kg_query, kg_add, kg_invalidate, kg_timeline, kg_stats
    NAVIGATION: traverse, find_tunnels, graph_stats
    DIARY:      diary_write, diary_read
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

_DEFAULT_PALACE_PATH = "~/.mempalace/"
_DEFAULT_COLLECTION = "mempalace_drawers"
_DEFAULT_WING = "wing_general"
_DEFAULT_TTL_DAYS = 90
from mempalace.tools_write import WriteToolsMixin
from mempalace.tools_read import ReadToolsMixin
from mempalace.tools_diary import DiaryMixin
from mempalace.tools_knowledge import KnowledgeMixin
from mempalace.tools_meta import MetaToolsMixin
from mempalace.tools_mistake import MistakeMixin
from mempalace.tools_nav import NavigationMixin
from mempalace.helpers import (
    _load_config,
    _get_palace_path,
    _is_noise,
    _detect_room,
    _detect_closet,
    _parse_natural_fact,
    _compress_aaak,
    _load_noise_patterns,
    _save_noise_patterns,
)
from mempalace.schemas import ALL_TOOL_SCHEMAS
from mempalace.config import MempalaceConfig
from mempalace.layers import Layer0, Layer1

class MempalaceMemoryProvider(ReadToolsMixin, WriteToolsMixin, KnowledgeMixin, NavigationMixin, DiaryMixin, MistakeMixin, MetaToolsMixin, MemoryProvider):
    """MemPalace local-first memory with palace structure and AAAK compression."""
    def __init__(self):
        self._config = None
        self._palace_path: Optional[Path] = None
        self._collection_name = _DEFAULT_COLLECTION
        self._default_wing = _DEFAULT_WING
        self._chroma_client = None
        self._collection = None
        self._kg = None
        self._taxonomy_cache: Dict[str, Dict[str, int]] = {}
        self._noise_patterns: List[str] = []
        self._watch_cache: Dict[str, dict] = {}
        self._prefetch_result = ""
        self._prefetch_lock = threading.Lock()
        self._prefetch_thread: Optional[threading.Thread] = None
        self._sync_thread: Optional[threading.Thread] = None
        self._turn_count = 0
        self._available = False
        self._wake_up_context: str = ""
        self._l0_identity: str = ""
        self._l1_story: str = ""

    def name(self) -> str:
        return "mempalace"
    def is_available(self) -> bool:
        if self._available:
            return True
        try:
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.config import MempalaceConfig

            return True
        except ImportError:
            logger.debug("MemPalace not installed: pip install mempalace")
            return False
    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "palace_path",
                "description": "Palace directory path",
                "default": _DEFAULT_PALACE_PATH,
            },
            {
                "key": "collection_name",
                "description": "ChromaDB collection name",
                "default": _DEFAULT_COLLECTION,
            },
            {
                "key": "default_wing",
                "description": "Default wing name",
                "default": _DEFAULT_WING,
            },
        ]
    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        config_path = Path(hermes_home) / ".mempalace" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except Exception:
                pass
        existing.update(values)
        config_path.write_text(json.dumps(existing, indent=2))
    def initialize(self, session_id: str, **kwargs) -> None:
        self._config = _load_config()
        self._palace_path = _get_palace_path(self._config)
        self._collection_name = self._config.get("collection_name", _DEFAULT_COLLECTION)
        self._default_wing = self._config.get("default_wing", _DEFAULT_WING)
        self._turn_count = 0

        try:
            import chromadb
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.knowledge_graph import KnowledgeGraph

            self._chroma_client = chromadb.PersistentClient(
                path=str(self._palace_path / "palace")
            )
            self._collection = self._chroma_client.get_or_create_collection(
                self._collection_name
            )
            self._kg = KnowledgeGraph()
            self._available = True
            logger.info("MemPalace initialized at %s", self._palace_path)

            self._load_wake_up_context()
            cache_path = self._palace_path / "taxonomy_cache.json"
            if cache_path.exists():
                try:
                    with open(cache_path) as f:
                        self._taxonomy_cache = json.load(f)
                    logger.debug("Taxonomy cache loaded from disk")
                except Exception:
                    self._build_taxonomy_cache()
            else:
                self._build_taxonomy_cache()
            self._sweep_expired_drawers()
            self._seed_kg_if_empty()
        except Exception as e:
            logger.warning("Failed to initialize MemPalace: %s", e)
            self._available = False
    def _load_wake_up_context(self) -> None:
        if not self._palace_path:
            return

        try:
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.layers import Layer0, Layer1

            palace_str = str(self._palace_path / "palace")

            l0 = Layer0(identity_path=str(self._palace_path / "identity.txt"))
            self._l0_identity = l0.render()

            # Check sync between identity.txt and SOUL.md
            hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
            soul_path = Path(hermes_home) / "SOUL.md"
            identity_path = self._palace_path / "identity.txt"
            if soul_path.exists() and identity_path.exists():
                soul_mtime = soul_path.stat().st_mtime
                id_mtime = identity_path.stat().st_mtime
                if abs(soul_mtime - id_mtime) > 86400:
                    logger.info("identity.txt and SOUL.md timestamps differ > 1 day")

            l1 = Layer1(palace_path=palace_str, wing=self._default_wing)
            self._l1_story = l1.generate()

            self._wake_up_context = f"{self._l0_identity}\n\n{self._l1_story}"
        except Exception as e:
            logger.warning("Failed to load wake-up context: %s", e)
            self._l0_identity = "## L0 — IDENTITY\nMemPalace memory active."
            self._l1_story = "## L1 — ESSENTIAL STORY\nNo palace data yet."
            self._wake_up_context = f"{self._l0_identity}\n\n{self._l1_story}"
    def _get_recent_sessions_block(self) -> str:
        """Get recent session entries for wake-up context."""
        if not self._ensure_palace():
            return ""

        try:
            results = self._collection.get(
                where={"$and": [{"wing": "wing_myos"}, {"room": "sessions"}]},
                include=["documents"],
            )

            docs = results.get("documents", []) or []
            if not docs:
                return ""

            sessions = docs[:5]
            if not sessions:
                return ""

            block = "## Recent Sessions\n"
            for s in sessions:
                block += f"- {s}\n"
            return block + "\n"
        except Exception as e:
            logger.debug("Failed to get recent sessions: %s", e)
            return ""
    def _get_learnings_block(self) -> str:
        """Get recent learnings for wake-up context.

        Note: hall_events entries are excluded because they are short-lived
        session bookkeeping with 1-week TTL, not actual learnings.
        """
        if not self._ensure_palace():
            return ""
        try:
            results = self._collection.get(
                where={"$and": [{"closet": {"$eq": "learnings"}}]},
                include=["documents", "metadatas"],
            )

            docs = results.get("documents", []) or []
            metas = results.get("metadatas", []) or []
            ids = results.get("ids", []) or []

            items = []
            for i, meta in enumerate(metas):
                # Filter out hall_events entries in Python (ChromaDB $ne is unreliable for exclusions)
                if meta.get("room") == "hall_events":
                    continue
                items.append(
                    {
                        "id": ids[i] if i < len(ids) else "",
                        "content": docs[i] if i < len(docs) else "",
                        "subject": meta.get("subject", ""),
                        "category": meta.get("category", ""),
                        "flags": meta.get("flags", []),
                        "created_at": meta.get("created_at", ""),
                    }
                )

            items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            capped = items[:30]

            now_iso = datetime.now(timezone.utc).isoformat()
            for item in capped:
                item_id = item.get("id", "")
                if item_id:
                    self._collection.update(
                        ids=[item_id],
                        metadatas=[{"last_accessed": now_iso}],
                    )

            if not capped:
                return ""

            block = "## What I Know (MemPalace Learnings)\n"
            for item in capped:
                content = item.get("content", "")
                subject = item.get("subject", "")
                category = item.get("category", "general")
                flags = item.get("flags", [])

                if not subject and content:
                    parts = content.strip().split()
                    subject = parts[0].upper() if parts else "UNKNOWN"
                elif not subject:
                    subject = "UNKNOWN"

                predicate = (
                    content.strip().replace("\n", " ")[:60] if content else category
                )

                flag_str = ",".join(flags[:3]) if isinstance(flags, list) else ""

                block += (
                    f"- {subject} → {predicate}|{category}"
                    + (f"|{flag_str}" if flag_str else "")
                    + "\n"
                )

            return block + "\n"
        except Exception as e:
            logger.debug("Failed to get learnings block: %s", e)
            return ""
    def _ensure_palace(self) -> bool:
        if self._collection is not None:
            return True
        if not self._palace_path:
            return False
        try:
            import chromadb

            self._chroma_client = chromadb.PersistentClient(
                path=str(self._palace_path / "palace")
            )
            self._collection = self._chroma_client.get_or_create_collection(
                self._collection_name
            )

            try:
                existing = self._collection.get(
                    where={"$and": [{"wing": "wing_myos"}, {"room": "diary"}]},
                    include=["metadatas"],
                )
                if not existing.get("ids"):
                    import time

                    self._collection.add(
                        documents=["[diary room bootstrap]"],
                        metadatas=[
                            {
                                "wing": "wing_myos",
                                "room": "diary",
                                "closet": "system",
                            }
                        ],
                        ids=[f"bootstrap_diary_{int(time.time())}"],
                    )
            except Exception:
                pass

            # Bootstrap learnings room in wing_myos if not exists
            try:
                existing_learnings = self._collection.get(
                    where={"$and": [{"wing": "wing_myos"}, {"room": "learnings"}]},
                    include=["metadatas"],
                )
                if not existing_learnings.get("ids"):
                    import time

                    self._collection.add(
                        documents=["[learnings room bootstrap]"],
                        metadatas=[
                            {
                                "wing": "wing_myos",
                                "room": "learnings",
                                "closet": "system",
                            }
                        ],
                        ids=[f"bootstrap_learnings_{int(time.time())}"],
                    )
            except Exception:
                pass

            return True
        except Exception as e:
            logger.debug("Palace not available: %s", e)
            return False
    def _build_taxonomy_cache(self) -> None:
        if not self._collection:
            return
        cache_path = self._palace_path / "taxonomy_cache.json"
        try:
            all_data = self._collection.get(include=["metadatas"])
            taxonomy: Dict[str, Dict[str, int]] = {}
            for m in all_data.get("metadatas", []) or []:
                w = m.get("wing", "unknown")
                r = m.get("room", "unknown")
                if w not in taxonomy:
                    taxonomy[w] = {}
                taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
            self._taxonomy_cache = taxonomy
            try:
                with open(cache_path, "w") as f:
                    json.dump(taxonomy, f)
            except Exception:
                pass
            logger.debug("Taxonomy cache built: %d wings", len(taxonomy))
        except Exception as e:
            logger.debug("Failed to build taxonomy cache: %s", e)
    def _update_taxonomy_cache(self, wing: str, room: str, delta: int) -> None:
        if wing not in self._taxonomy_cache:
            self._taxonomy_cache[wing] = {}
        if room not in self._taxonomy_cache[wing]:
            self._taxonomy_cache[wing][room] = 0
        self._taxonomy_cache[wing][room] += delta
        if self._taxonomy_cache[wing][room] <= 0:
            del self._taxonomy_cache[wing][room]
        if not self._taxonomy_cache[wing]:
            del self._taxonomy_cache[wing]
        try:
            cache_path = self._palace_path / "taxonomy_cache.json"
            with open(cache_path, "w") as f:
                json.dump(self._taxonomy_cache, f)
        except Exception:
            pass
    def _sweep_expired_drawers(self) -> None:
        if not self._collection:
            return
        try:
            now = datetime.now().isoformat()
            all_data = self._collection.get(where={"expires_at": {"$lt": now}})
            expired_ids = all_data.get("ids", [])
            if expired_ids:
                self._collection.delete(ids=expired_ids)
                logger.info("Swept %d expired drawers", len(expired_ids))
        except Exception as e:
            logger.debug("Failed to sweep expired drawers: %s", e)
    def _seed_kg_if_empty(self) -> None:
        if not self._kg or not self._palace_path:
            return
        try:
            hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
            soul_path = Path(hermes_home) / "SOUL.md"
            registry_path = Path.home() / ".mempalace" / "entity_registry.json"

            # Check if KG already has content
            kg_stats = self._kg.stats()
            if kg_stats and kg_stats.get("triples", 0) > 0:
                logger.debug("KG already has data, skipping seed")
                return

            now = datetime.now().isoformat()
            count = 0

            # Seed from SOUL.md
            if soul_path.exists():
                facts = [
                    ("NEH", "core_value", "genuine_helpful", now),
                    ("NEH", "core_value", "have_opinions", now),
                    ("NEH", "core_value", "resourceful", now),
                    ("NEH", "core_value", "earn_trust", now),
                    ("NEH", "core_value", "remember_guest", now),
                ]
                for kw in ["private", "ask_before", "careful"]:
                    facts.append(("NEH", "boundary", kw, now))
                for kw in ["concise", "thorough"]:
                    facts.append(("NEH", "vibe", kw, now))

                for subject, predicate, obj, valid_from in facts:
                    try:
                        self._kg.add_triple(
                            subject, predicate, obj, valid_from=valid_from
                        )
                        count += 1
                    except Exception:
                        pass

            # Seed from identity.txt
            identity_path = self._palace_path / "identity.txt"
            if identity_path.exists():
                try:
                    content = identity_path.read_text()
                    lines = content.strip().split("\n")
                    in_section = None
                    for line in lines:
                        line = line.strip()
                        if line.startswith("## "):
                            in_section = line.strip("# ").lower()
                        elif line.startswith("- ") and in_section:
                            fact = line[2:].strip()
                            if fact and len(fact) > 3:
                                self._kg.add_triple(
                                    "MyOS",
                                    in_section.replace(" ", "_"),
                                    fact[:100],
                                    valid_from=now,
                                )
                                count += 1
                except Exception:
                    pass

            # Seed from entity_registry.json
            if registry_path.exists():
                try:
                    import json as json_lib

                    content = json_lib.loads(registry_path.read_text())
                    for name, data in content.get("people", {}).items():
                        entity_code = name[:3].upper()
                        rel = data.get("relationship", "")
                        if rel:
                            self._kg.add_triple(
                                "NEH",
                                "relationship",
                                f"{entity_code}:{rel}",
                                valid_from=now,
                            )
                            count += 1
                except Exception:
                    pass

            if count > 0:
                logger.info("KG seeded with %d triples", count)
        except Exception as e:
            logger.debug("Failed to seed KG: %s", e)
    def system_prompt_block(self) -> str:
        try:
            sessions_block = self._get_recent_sessions_block()
        except Exception:
            sessions_block = ""
        try:
            learnings_block = self._get_learnings_block()
        except Exception:
            learnings_block = ""

        aaak_guide = """## AAAK Compression Dialect
AAAK (Autonomous Autonomous Autonomous Knowledge) is a 30x lossless shorthand format.
Use structured shorthand to store memories compactly:

Format: ENTITY → entity|topic_codes|"key_quote"|flags
Example: AUTH_DB → Postgres|db,migration|reason:reliable|decision
Example: KAI → pref:detailed.reviews|team|preference
Example: ORION → project,jovovich|architecture,goals|project

FLAGS: DECISION, CORE, SENSITIVE, TECHNICAL, PIVOT

When storing via mempalace_add_drawer or mempalace_remember, prefer AAAK shorthand
when content exceeds 100 words. Store raw text for short items, AAAK for long summaries."""

        if self._wake_up_context:
            return (
                "# MemPalace Memory\n"
                f"{self._wake_up_context}\n\n"
                "When user asks to 'remember' something, use mempalace_remember.\n"
                "Use mempalace_search to find stored memories.\n"
                "Use mempalace_add_drawer with AAAK shorthand for long content.\n"
                "Use mempalace_kg_add for structured facts (subject-predicate-object triples).\n"
                "Use mempalace_diary_write in AAAK format for agent observations.\n"
                "Use mempalace_session_write at session end to track multi-session projects.\n"
                "Use mempalace_session_read at session start to restore project context.\n\n"
                + learnings_block
                + sessions_block
                + aaak_guide
            )
        return (
            "# MemPalace Memory\n"
            "MemPalace is your persistent memory with palace structure (Wings/Rooms).\n"
            "When user asks to 'remember', use mempalace_remember.\n"
            "Use mempalace_search to find information.\n"
            "Use mempalace_kg_add for structured facts.\n"
            "Use mempalace_diary_write in AAAK shorthand for observations.\n"
            "Use mempalace_session_write at session end to track multi-session projects.\n"
            "Use mempalace_session_read at session start to restore project context.\n\n"
            + learnings_block
            + sessions_block
            + aaak_guide
        )
    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            self._prefetch_thread.join(timeout=3.0)
        with self._prefetch_lock:
            result = self._prefetch_result
            self._prefetch_result = ""
        if not result:
            return ""
        return f"## MemPalace Memory\n{result}"
    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        def _run():
            if not self._ensure_palace():
                return
            try:
                import sys

                _plugin_dir = Path(__file__).parent / "mempalace"
                if str(_plugin_dir) not in sys.path:
                    sys.path.insert(0, str(_plugin_dir))
                from searcher import search_memories

                results = search_memories(
                    query,
                    palace_path=str(self._palace_path / "palace"),
                    n_results=5,
                )
                if results:
                    lines = [r.get("text", r.get("content", "")) for r in results if r]
                    with self._prefetch_lock:
                        self._prefetch_result = "\n".join(f"- {l}" for l in lines[:5])
            except Exception as e:
                logger.debug("MemPalace prefetch failed: %s", e)

        self._prefetch_thread = threading.Thread(
            target=_run, daemon=True, name="mempalace-prefetch"
        )
        self._prefetch_thread.start()
    def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str = ""
    ) -> None:
        self._turn_count += 1

        if not self._ensure_palace():
            return

        if not user_content and not assistant_content:
            return

        def _mine():
            try:
                combined = f"USER: {user_content}\nASSISTANT: {assistant_content}"
                room = self._detect_room(combined)
                closet = self._detect_closet(combined)

                import uuid

                doc_id = str(uuid.uuid4())
                self._collection.add(
                    documents=[combined[:10000]],
                    metadatas=[
                        {
                            "wing": self._default_wing,
                            "room": room,
                            "closet": closet,
                            "session_id": session_id,
                            "turn": self._turn_count,
                        }
                    ],
                    ids=[doc_id],
                )
            except Exception as e:
                logger.debug("Auto-mine failed: %s", e)

        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=2.0)

        self._sync_thread = threading.Thread(
            target=_mine, daemon=True, name="mempalace-sync"
        )
        self._sync_thread.start()

    # ---- Helper delegating stubs ----

    def _detect_room(self, content: str) -> str:
        return _detect_room(self, content)

    def _detect_closet(self, content: str) -> str:
        return _detect_closet(self, content)

    def _parse_natural_fact(self, fact: str) -> tuple:
        return _parse_natural_fact(self, fact)

    def _compress_aaak(self, content: str) -> str:
        return _compress_aaak(self, content)

    def _is_noise(self, content: str) -> bool:
        return _is_noise(self, content)

    def _load_noise_patterns(self) -> List[str]:
        return _load_noise_patterns(self)

    def _save_noise_patterns(self, patterns: List[str]) -> None:
        return _save_noise_patterns(self, patterns)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return ALL_TOOL_SCHEMAS
    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        if not self._ensure_palace():
            return json.dumps(
                {"error": "MemPalace palace not initialized. Run: mempalace init <dir>"}
            )

        try:
            if tool_name == "mempalace_status":
                return self._tool_status()
            elif tool_name == "mempalace_list_wings":
                return self._tool_list_wings(args)
            elif tool_name == "mempalace_list_rooms":
                return self._tool_list_rooms(args)
            elif tool_name == "mempalace_get_taxonomy":
                return self._tool_get_taxonomy(args)
            elif tool_name == "mempalace_search":
                return self._tool_search(args)
            elif tool_name == "mempalace_check_duplicate":
                return self._tool_check_duplicate(args)
            elif tool_name == "mempalace_get_aaak_spec":
                return self._tool_get_aaak_spec()
            elif tool_name == "mempalace_add_drawer":
                return self._tool_add_drawer(args)
            elif tool_name == "mempalace_session_write":
                return self._tool_session_write(args)
            elif tool_name == "mempalace_session_read":
                return self._tool_session_read(args)
            elif tool_name == "mempalace_remember":
                return self._tool_remember(args)
            elif tool_name == "mempalace_delete_drawer":
                return self._tool_delete_drawer(args)
            elif tool_name == "mempalace_get_versions":
                return self._tool_get_versions(args)
            elif tool_name == "mempalace_kg_query":
                return self._tool_kg_query(args)
            elif tool_name == "mempalace_kg_add":
                return self._tool_kg_add(args)
            elif tool_name == "mempalace_kg_invalidate":
                return self._tool_kg_invalidate(args)
            elif tool_name == "mempalace_kg_timeline":
                return self._tool_kg_timeline(args)
            elif tool_name == "mempalace_kg_stats":
                return self._tool_kg_stats()
            elif tool_name == "mempalace_kg_explore":
                return self._tool_kg_explore(args)
            elif tool_name == "mempalace_remember_fact":
                return self._tool_remember_fact(args)
            elif tool_name == "mempalace_preview_aaak":
                return self._tool_preview_aaak(args)
            elif tool_name == "mempalace_set_drawer_flags":
                return self._tool_set_drawer_flags(args)
            elif tool_name == "mempalace_watch":
                return self._tool_watch(args)
            elif tool_name == "mempalace_traverse":
                return self._tool_traverse(args)
            elif tool_name == "mempalace_find_tunnels":
                return self._tool_find_tunnels(args)
            elif tool_name == "mempalace_graph_stats":
                return self._tool_graph_stats()
            elif tool_name == "mempalace_diary_write":
                return self._tool_diary_write(args)
            elif tool_name == "mempalace_diary_read":
                return self._tool_diary_read(args)
            elif tool_name == "mempalace_summarize":
                return self._tool_summarize(args)
            elif tool_name == "mempalace_profile_list":
                return self._tool_profile_list()
            elif tool_name == "mempalace_profile_switch":
                return self._tool_profile_switch(args)
            elif tool_name == "mempalace_sweep":
                return self._tool_sweep(args)
            elif tool_name == "mempalace_record_mistake":
                return self._tool_record_mistake(args)
            elif tool_name == "mempalace_distill_mistake":
                return self._tool_distill_mistake(args)
            elif tool_name == "mempalace_noise_filter":
                return self._tool_noise_filter(args)
            elif tool_name == "mempalace_expiring":
                return self._tool_expiring(args)
            elif tool_name == "mempalace_backup":
                return self._tool_backup(args)
            elif tool_name == "mempalace_restore":
                return self._tool_restore(args)
            elif tool_name == "mempalace_session_diff":
                return self._tool_session_diff(args)
            elif tool_name == "mempalace_recall":
                return self._tool_recall(args)
            elif tool_name == "mempalace_recall_all":
                return self._tool_recall_all(args)
            elif tool_name == "mempalace_learn":
                return self._tool_learn(args)
            elif tool_name == "mempalace_update":
                return self._tool_update(args)
            elif tool_name == "mempalace_drawer_history":
                return self._tool_drawer_history(args)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            logger.warning("MemPalace tool %s failed: %s", tool_name, e)
            return json.dumps({"error": str(e)})
    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        self._turn_count = turn_number
        remaining_tokens = kwargs.get("remaining_tokens")
        if remaining_tokens and remaining_tokens < 2000:
            logger.debug("Low token context: triggering prefetch")
            self.queue_prefetch(message, session_id="")
    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if not messages or not self._ensure_palace():
            return

        def _extract():
            try:
                from datetime import datetime

                topics = set()
                key_points = []

                for msg in messages[-10:]:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if not content or role not in ("user", "assistant"):
                        continue

                    room = self._default_wing
                    closet = "hall_general"

                    if "decision" in content.lower() or "decided" in content.lower():
                        closet = "hall_facts"
                    elif "preference" in content.lower() or "prefer" in content.lower():
                        closet = "hall_preferences"
                    elif "problem" in content.lower() or "issue" in content.lower():
                        closet = "hall_discoveries"

                    if len(content) > 100:
                        content = content[:500] + "..."

                    try:
                        import uuid

                        doc_id = str(uuid.uuid4())
                        self._collection.add(
                            documents=[content[:5000]],
                            metadatas=[
                                {"wing": room, "room": "session", "closet": closet}
                            ],
                            ids=[doc_id],
                        )
                    except Exception as e:
                        logger.debug("Failed to extract session memory: %s", e)

                for msg in messages[-10:]:
                    content = msg.get("content", "")
                    if not content:
                        continue
                    content_lower = content.lower()
                    if "cod" in content_lower or "implement" in content_lower:
                        topics.add("code")
                    if (
                        "fix" in content_lower
                        or "bug" in content_lower
                        or "error" in content_lower
                    ):
                        topics.add("fix")
                    if "design" in content_lower or "architecture" in content_lower:
                        topics.add("design")
                    if "test" in content_lower:
                        topics.add("testing")

                if topics:
                    try:
                        import uuid
                        from datetime import datetime

                        now = datetime.now()
                        date_str = now.strftime("%Y-%m-%d")
                        topics_str = ",".join(sorted(topics))

                        diary_entry = (
                            f"DATE:{date_str}|ACTIVITIES:{topics_str}|"
                            f"TURNS:{self._turn_count}|"
                            f"NOTES:auto-extracted from session"
                        )

                        doc_id = str(uuid.uuid4())
                        self._collection.add(
                            documents=[diary_entry],
                            metadatas=[
                                {
                                    "wing": "wing_myos",
                                    "room": "diary",
                                    "closet": "hall_events",
                                    "created_at": now.isoformat(),
                                }
                            ],
                            ids=[doc_id],
                        )
                        logger.debug("Added auto diary entry for session")
                    except Exception as e:
                        logger.debug("Failed to create diary entry: %s", e)

            except Exception as e:
                logger.debug("Session end extraction failed: %s", e)

        thread = threading.Thread(
            target=_extract, daemon=True, name="mempalace-session-end"
        )
        thread.start()

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        if not messages or not self._ensure_palace():
            return ""

        relevant = []
        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue
            if len(content) > 500:
                content = content[:497] + "..."
            role = msg.get("role", "unknown")
            relevant.append(f"[{role}]: {content}")

        if not relevant:
            return ""

        compressed = "\n".join(relevant[-5:])
        return f"\n## MemPalace Context (pre-compression)\n{compressed}\n"
    def on_memory_write(self, action: str, target: str, content: str) -> None:
        if not self._ensure_palace():
            return

        def _mirror():
            try:
                import uuid

                wing = "wing_general"
                room = "memory" if target == "memory" else "user"
                closet = "hall_facts"

                doc_id = str(uuid.uuid4())
                self._collection.add(
                    documents=[content[:5000]],
                    metadatas=[{"wing": wing, "room": room, "closet": closet}],
                    ids=[doc_id],
                )
                logger.debug("Mirrored memory write to MemPalace: %s", action)
            except Exception as e:
                logger.debug("Failed to mirror memory write: %s", e)

        thread = threading.Thread(
            target=_mirror, daemon=True, name="mempalace-memory-write"
        )
        thread.start()

    def on_delegation(
        self, task: str, result: str, *, child_session_id: str = "", **kwargs
    ) -> None:
        if not self._ensure_palace():
            return

        def _record():
            try:
                import uuid

                content = f"DELEGATION TASK: {task[:500]}\n\nRESULT: {result[:2000]}"
                doc_id = str(uuid.uuid4())
                self._collection.add(
                    documents=[content],
                    metadatas=[
                        {
                            "wing": self._default_wing,
                            "room": "delegation",
                            "closet": "hall_events",
                        }
                    ],
                    ids=[doc_id],
                )
                logger.debug("Recorded delegation to MemPalace")
            except Exception as e:
                logger.debug("Failed to record delegation: %s", e)

        thread = threading.Thread(
            target=_record, daemon=True, name="mempalace-delegation"
        )
        thread.start()

    def shutdown(self) -> None:
        for t in (self._prefetch_thread, self._sync_thread):
            if t and t.is_alive():
                t.join(timeout=5.0)
        if self._chroma_client:
            self._chroma_client = None
            self._collection = None


def register(ctx) -> None:
    """Register MemPalace as a memory provider plugin."""
    ctx.register_memory_provider(MempalaceMemoryProvider())