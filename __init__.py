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
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

_DEFAULT_PALACE_PATH = "~/.mempalace/"
_DEFAULT_COLLECTION = "mempalace_drawers"
_DEFAULT_WING = "wing_general"


def _load_config() -> dict:
    """Load config from env vars with $HERMES_HOME/.mempalace/config.json overrides."""
    from hermes_constants import get_hermes_home

    config = {
        "palace_path": os.environ.get("MEMPALACE_PATH", _DEFAULT_PALACE_PATH),
        "collection_name": os.environ.get("MEMPALACE_COLLECTION", _DEFAULT_COLLECTION),
        "default_wing": os.environ.get("MEMPALACE_DEFAULT_WING", _DEFAULT_WING),
    }

    config_path = get_hermes_home() / ".mempalace" / "config.json"
    if config_path.exists():
        try:
            file_cfg = json.loads(config_path.read_text(encoding="utf-8"))
            config.update(
                {k: v for k, v in file_cfg.items() if v is not None and v != ""}
            )
        except Exception:
            pass

    return config


def _get_palace_path(config: dict) -> Path:
    return Path(os.path.expanduser(config.get("palace_path", _DEFAULT_PALACE_PATH)))


# ---------------------------------------------------------------------------
# Tool schemas (19 tools)
# ---------------------------------------------------------------------------

STATUS_SCHEMA = {
    "name": "mempalace_status",
    "description": (
        "Get MemPalace palace overview — total drawers, wings, rooms, and AAAK spec. "
        "Use at session start to understand the current memory state."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

LIST_WINGS_SCHEMA = {
    "name": "mempalace_list_wings",
    "description": "List all wings in the palace with drawer counts.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

LIST_ROOMS_SCHEMA = {
    "name": "mempalace_list_rooms",
    "description": "List all rooms within a specific wing.",
    "parameters": {
        "type": "object",
        "properties": {
            "wing": {"type": "string", "description": "Wing name to list rooms for."},
        },
        "required": ["wing"],
    },
}

GET_TAXONOMY_SCHEMA = {
    "name": "mempalace_get_taxonomy",
    "description": "Get the full wing → room → count taxonomy tree.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

SEARCH_SCHEMA = {
    "name": "mempalace_search",
    "description": (
        "Semantic search over MemPalace's stored memory. "
        "Returns verbatim excerpts ranked by relevance. "
        "Use wing/room filters to narrow scope."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in MemPalace.",
            },
            "wing": {"type": "string", "description": "Optional wing to scope search."},
            "room": {"type": "string", "description": "Optional room to scope search."},
            "limit": {"type": "integer", "description": "Max results (default: 10)."},
        },
        "required": ["query"],
    },
}

CHECK_DUPLICATE_SCHEMA = {
    "name": "mempalace_check_duplicate",
    "description": (
        "Check if content already exists before filing. "
        "Returns duplicate check result to prevent redundant storage."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Content to check for duplicates.",
            },
            "wing": {"type": "string", "description": "Wing to check in."},
        },
        "required": ["content"],
    },
}

GET_AAAK_SPEC_SCHEMA = {
    "name": "mempalace_get_aaak_spec",
    "description": (
        "Get the AAAK dialect specification — the compressed shorthand format. "
        "AAAK is 30x lossless compression for fast context loading."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

ADD_DRAWER_SCHEMA = {
    "name": "mempalace_add_drawer",
    "description": (
        "File verbatim content into a wing/room/closet. "
        "Stores the original content for later retrieval. "
        "Use after decisions, discoveries, or important exchanges."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The verbatim content to store.",
            },
            "wing": {
                "type": "string",
                "description": "Wing name (e.g. 'wing_general').",
            },
            "room": {
                "type": "string",
                "description": "Room name (e.g. 'auth-migration').",
            },
            "closet": {
                "type": "string",
                "description": "Closet/hall name (e.g. 'hall_facts').",
            },
        },
        "required": ["content", "wing"],
    },
}

DELETE_DRAWER_SCHEMA = {
    "name": "mempalace_delete_drawer",
    "description": "Remove a drawer (content entry) by its ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "drawer_id": {"type": "string", "description": "The drawer ID to remove."},
        },
        "required": ["drawer_id"],
    },
}

REMEMBER_SCHEMA = {
    "name": "mempalace_remember",
    "description": (
        "Store an important fact, preference, or decision in MemPalace memory. "
        "Use this when the user asks to 'remember' something. "
        "Automatically organizes into the palace structure (wings/rooms). "
        "Content is stored verbatim and semantically searchable."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "What to remember — a fact, preference, decision, or important detail.",
            },
            "category": {
                "type": "string",
                "description": "Category hint: 'fact', 'preference', 'decision', 'person', 'project' (default: auto-detect).",
            },
        },
        "required": ["content"],
    },
}

KG_QUERY_SCHEMA = {
    "name": "mempalace_kg_query",
    "description": (
        "Query the knowledge graph for entity relationships. "
        "Returns triples matching the query with temporal validity."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "entity": {"type": "string", "description": "Entity to query."},
            "as_of": {
                "type": "string",
                "description": "Query historical state (YYYY-MM-DD).",
            },
        },
        "required": ["entity"],
    },
}

KG_ADD_SCHEMA = {
    "name": "mempalace_kg_add",
    "description": (
        "Add a fact triple to the knowledge graph. "
        "Format: (subject, predicate, object, valid_from?). "
        "Use for structured facts with temporal validity."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Subject entity."},
            "predicate": {"type": "string", "description": "Relationship/predicate."},
            "object": {"type": "string", "description": "Object value."},
            "valid_from": {"type": "string", "description": "Start date (YYYY-MM-DD)."},
        },
        "required": ["subject", "predicate", "object"],
    },
}

KG_INVALIDATE_SCHEMA = {
    "name": "mempalace_kg_invalidate",
    "description": (
        "Invalidate a fact — mark it as ended. "
        "Use when relationships change or facts become stale."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Subject entity."},
            "predicate": {
                "type": "string",
                "description": "Relationship to invalidate.",
            },
            "object": {"type": "string", "description": "Object value."},
            "ended": {"type": "string", "description": "End date (YYYY-MM-DD)."},
        },
        "required": ["subject", "predicate", "object"],
    },
}

KG_TIMELINE_SCHEMA = {
    "name": "mempalace_kg_timeline",
    "description": "Get a chronological timeline story for an entity.",
    "parameters": {
        "type": "object",
        "properties": {
            "entity": {"type": "string", "description": "Entity to get timeline for."},
        },
        "required": ["entity"],
    },
}

KG_STATS_SCHEMA = {
    "name": "mempalace_kg_stats",
    "description": "Get knowledge graph statistics — entity count, triple count, etc.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

TRAVERSE_SCHEMA = {
    "name": "mempalace_traverse",
    "description": (
        "Walk the palace graph from a starting room across wings. "
        "Uses BFS to find connected rooms and tunnels."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "start_room": {
                "type": "string",
                "description": "Room to start traversal from.",
            },
            "max_depth": {
                "type": "integer",
                "description": "Max traversal depth (default: 3).",
            },
        },
        "required": ["start_room"],
    },
}

FIND_TUNNELS_SCHEMA = {
    "name": "mempalace_find_tunnels",
    "description": (
        "Find tunnels — rooms that bridge two different wings. "
        "Use to discover cross-domain connections."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "wing_a": {"type": "string", "description": "First wing."},
            "wing_b": {"type": "string", "description": "Second wing."},
        },
        "required": ["wing_a", "wing_b"],
    },
}

GRAPH_STATS_SCHEMA = {
    "name": "mempalace_graph_stats",
    "description": "Get palace graph connectivity statistics.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

DIARY_WRITE_SCHEMA = {
    "name": "mempalace_diary_write",
    "description": (
        "Write an AAAK diary entry for a specialist agent. "
        "Agents maintain their own diary in AAAK format."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "Agent name (e.g. 'reviewer', 'architect').",
            },
            "entry": {"type": "string", "description": "AAAK-formatted diary entry."},
        },
        "required": ["agent", "entry"],
    },
}

DIARY_READ_SCHEMA = {
    "name": "mempalace_diary_read",
    "description": "Read recent diary entries for a specialist agent.",
    "parameters": {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "Agent name."},
            "last_n": {
                "type": "integer",
                "description": "Number of recent entries (default: 10).",
            },
        },
        "required": ["agent"],
    },
}

ALL_TOOL_SCHEMAS = [
    STATUS_SCHEMA,
    LIST_WINGS_SCHEMA,
    LIST_ROOMS_SCHEMA,
    GET_TAXONOMY_SCHEMA,
    SEARCH_SCHEMA,
    CHECK_DUPLICATE_SCHEMA,
    GET_AAAK_SPEC_SCHEMA,
    ADD_DRAWER_SCHEMA,
    DELETE_DRAWER_SCHEMA,
    KG_QUERY_SCHEMA,
    KG_ADD_SCHEMA,
    KG_INVALIDATE_SCHEMA,
    KG_TIMELINE_SCHEMA,
    KG_STATS_SCHEMA,
    TRAVERSE_SCHEMA,
    FIND_TUNNELS_SCHEMA,
    GRAPH_STATS_SCHEMA,
    DIARY_WRITE_SCHEMA,
    DIARY_READ_SCHEMA,
    REMEMBER_SCHEMA,
]


# ---------------------------------------------------------------------------
# MemoryProvider implementation
# ---------------------------------------------------------------------------


class MempalaceMemoryProvider(MemoryProvider):
    """MemPalace local-first memory with palace structure and AAAK compression."""

    def __init__(self):
        self._config = None
        self._palace_path: Optional[Path] = None
        self._collection_name = _DEFAULT_COLLECTION
        self._default_wing = _DEFAULT_WING
        self._chroma_client = None
        self._collection = None
        self._kg = None
        self._prefetch_result = ""
        self._prefetch_lock = threading.Lock()
        self._prefetch_thread: Optional[threading.Thread] = None
        self._sync_thread: Optional[threading.Thread] = None
        self._turn_count = 0
        self._available = False
        self._wake_up_context: str = ""
        self._l0_identity: str = ""
        self._l1_story: str = ""

    @property
    def name(self) -> str:
        return "mempalace"

    def is_available(self) -> bool:
        if self._available:
            return True
        try:
            import mempalace
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
        except Exception as e:
            logger.warning("Failed to initialize MemPalace: %s", e)
            self._available = False

    def _load_wake_up_context(self) -> None:
        if not self._palace_path:
            return

        try:
            from mempalace.layers import Layer0, Layer1

            palace_str = str(self._palace_path)

            l0 = Layer0(identity_path=str(self._palace_path / "identity.txt"))
            self._l0_identity = l0.render()

            l1 = Layer1(palace_path=palace_str, wing=self._default_wing)
            self._l1_story = l1.generate()

            self._wake_up_context = f"{self._l0_identity}\n\n{self._l1_story}"
        except Exception as e:
            logger.debug("Failed to load wake-up context: %s", e)
            self._l0_identity = "## L0 — IDENTITY\nMemPalace memory active."
            self._l1_story = "## L1 — ESSENTIAL STORY\nNo palace data yet."
            self._wake_up_context = f"{self._l0_identity}\n\n{self._l1_story}"

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
            return True
        except Exception as e:
            logger.debug("Palace not available: %s", e)
            return False

    def system_prompt_block(self) -> str:
        if self._wake_up_context:
            return (
                "# MemPalace Memory\n"
                f"{self._wake_up_context}\n\n"
                "When user asks to 'remember' something, use mempalace_remember.\n"
                "Use mempalace_search to find stored memories.\n"
                "Use mempalace_add_drawer for explicit file storage.\n"
                "Use mempalace_kg_add for structured facts (subject-predicate-object triples)."
            )
        return (
            "# MemPalace Memory\n"
            "MemPalace is your persistent memory. It stores facts, preferences, and decisions.\n"
            "When user asks to 'remember' something, use mempalace_remember immediately.\n"
            "Use mempalace_search to find previously stored information.\n"
            "Use mempalace_kg_add for structured knowledge graph facts."
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
                from mempalace.searcher import search_memories

                results = search_memories(
                    query,
                    palace_path=str(self._palace_path),
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
        elif any(
            w in content_lower for w in ["prefer", "preference", "like", "dislike"]
        ):
            return "hall_preferences"
        elif any(
            w in content_lower for w in ["discover", "found", "realized", "learned"]
        ):
            return "hall_discoveries"
        elif any(
            w in content_lower for w in ["help", "advice", "recommend", "suggestion"]
        ):
            return "hall_advice"
        else:
            return "hall_events"

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
                return self._tool_list_wings()
            elif tool_name == "mempalace_list_rooms":
                return self._tool_list_rooms(args.get("wing", ""))
            elif tool_name == "mempalace_get_taxonomy":
                return self._tool_get_taxonomy()
            elif tool_name == "mempalace_search":
                return self._tool_search(args)
            elif tool_name == "mempalace_check_duplicate":
                return self._tool_check_duplicate(args)
            elif tool_name == "mempalace_get_aaak_spec":
                return self._tool_get_aaak_spec()
            elif tool_name == "mempalace_add_drawer":
                return self._tool_add_drawer(args)
            elif tool_name == "mempalace_remember":
                return self._tool_remember(args)
            elif tool_name == "mempalace_delete_drawer":
                return self._tool_delete_drawer(args)
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
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            logger.warning("MemPalace tool %s failed: %s", tool_name, e)
            return json.dumps({"error": str(e)})

    def _tool_status(self) -> str:
        if not self._collection:
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

    def _tool_list_wings(self) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            all_data = self._collection.get(include=["metadatas"])
            wings = {}
            for m in all_data.get("metadatas", []):
                w = m.get("wing", "unknown")
                wings[w] = wings.get(w, 0) + 1
            return json.dumps({"wings": wings})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_list_rooms(self, wing: str) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            results = self._collection.get(
                where={"wing": wing} if wing else None, include=["metadatas"]
            )
            rooms = {}
            for m in results.get("metadatas", []):
                r = m.get("room", "unknown")
                rooms[r] = rooms.get(r, 0) + 1
            return json.dumps({"wing": wing, "rooms": rooms})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_get_taxonomy(self) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            all_data = self._collection.get(include=["metadatas"])
            taxonomy = {}
            for m in all_data.get("metadatas", []):
                w = m.get("wing", "unknown")
                r = m.get("room", "unknown")
                if w not in taxonomy:
                    taxonomy[w] = {}
                taxonomy[w][r] = taxonomy[w].get(r, 0) + 1
            return json.dumps({"taxonomy": taxonomy})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_search(self, args: dict) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            from mempalace.searcher import search_memories

            query = args.get("query", "")
            wing = args.get("wing")
            room = args.get("room")
            limit = args.get("limit", 10)

            results = search_memories(
                query,
                palace_path=str(self._palace_path),
                n_results=limit,
            )
            items = []
            for r in results:
                meta = r.get("metadata", {})
                if wing and meta.get("wing") != wing:
                    continue
                if room and meta.get("room") != room:
                    continue
                items.append(
                    {
                        "text": r.get("text", r.get("content", "")),
                        "score": r.get("distance", 0),
                        "wing": meta.get("wing"),
                        "room": meta.get("room"),
                    }
                )
            return json.dumps({"results": items, "count": len(items)})
        except ImportError:
            return json.dumps({"error": "mempalace searcher not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_check_duplicate(self, args: dict) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            content = args.get("content", "")
            wing = args.get("wing", self._default_wing)
            results = self._collection.get(
                where={"wing": wing} if wing else None, include=["documents"]
            )
            for doc in results.get("documents", []):
                if content.lower() in doc.lower():
                    return json.dumps({"duplicate": True, "matched": doc[:200]})
            return json.dumps({"duplicate": False})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_get_aaak_spec(self) -> str:
        try:
            from mempalace.dialect import AAAK_SPEC

            return json.dumps({"aaak_spec": AAAK_SPEC})
        except ImportError:
            return json.dumps({"error": "AAAK dialect not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_add_drawer(self, args: dict) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            import uuid

            content = args.get("content", "")
            wing = args.get("wing", self._default_wing)
            room = args.get("room", "general")
            closet = args.get("closet", "hall_general")

            doc_id = str(uuid.uuid4())
            self._collection.add(
                documents=[content],
                metadatas=[{"wing": wing, "room": room, "closet": closet}],
                ids=[doc_id],
            )
            return json.dumps({"result": "Drawer added", "drawer_id": doc_id})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_remember(self, args: dict) -> str:
        """Intuitive remember tool - stores content with auto-detected categorization."""
        if not self._ensure_palace():
            return json.dumps(
                {"error": "Palace not initialized. Run: mempalace init <dir>"}
            )

        try:
            import uuid

            content = args.get("content", "")
            category = args.get("category", "")

            if not content:
                return json.dumps({"error": "content is required"})

            content_lower = content.lower()

            if category == "preference" or any(
                w in content_lower for w in ["prefer", "like", "dislike", "favor"]
            ):
                room = "preferences"
                closet = "hall_preferences"
            elif category == "decision" or any(
                w in content_lower for w in ["decided", "chose", "decision", "will"]
            ):
                room = "decisions"
                closet = "hall_facts"
            elif category == "person" or any(
                w in content_lower for w in ["works on", "responsible", "owns"]
            ):
                room = "people"
                closet = "hall_facts"
            elif category == "project" or any(
                w in content_lower for w in ["project", "building", "creating"]
            ):
                room = "projects"
                closet = "hall_events"
            else:
                room = "general"
                closet = "hall_events"

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
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_delete_drawer(self, args: dict) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            drawer_id = args.get("drawer_id", "")
            self._collection.delete(ids=[drawer_id])
            return json.dumps({"result": "Drawer deleted"})
        except Exception as e:
            return json.dumps({"error": str(e)})

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
            stats = self._kg.get_stats()
            return json.dumps({"stats": stats})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_traverse(self, args: dict) -> str:
        try:
            from mempalace.palace_graph import traverse

            start_room = args.get("start_room", "")
            max_depth = args.get("max_depth", 3)
            results = traverse(
                start_room, max_depth=max_depth, palace_path=str(self._palace_path)
            )
            return json.dumps({"start_room": start_room, "traversal": results})
        except ImportError:
            return json.dumps({"error": "palace_graph not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_find_tunnels(self, args: dict) -> str:
        try:
            from mempalace.palace_graph import find_tunnels

            wing_a = args.get("wing_a", "")
            wing_b = args.get("wing_b", "")
            tunnels = find_tunnels(wing_a, wing_b, palace_path=str(self._palace_path))
            return json.dumps({"wing_a": wing_a, "wing_b": wing_b, "tunnels": tunnels})
        except ImportError:
            return json.dumps({"error": "palace_graph not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_graph_stats(self) -> str:
        try:
            from mempalace.palace_graph import graph_stats

            stats = graph_stats(palace_path=str(self._palace_path))
            return json.dumps({"graph_stats": stats})
        except ImportError:
            return json.dumps({"error": "palace_graph not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_diary_write(self, args: dict) -> str:
        try:
            from mempalace.mcp_server import tool_diary_write

            agent = args.get("agent", "")
            entry = args.get("entry", "")
            result = tool_diary_write(agent, entry)
            return json.dumps({"result": result})
        except ImportError:
            return json.dumps({"error": "mcp_server not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_diary_read(self, args: dict) -> str:
        try:
            from mempalace.mcp_server import tool_diary_read

            agent = args.get("agent", "")
            last_n = args.get("last_n", 10)
            result = tool_diary_read(agent, last_n)
            return json.dumps({"agent": agent, "entries": result})
        except ImportError:
            return json.dumps({"error": "mcp_server not available"})
        except Exception as e:
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
