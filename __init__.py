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
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

_DEFAULT_PALACE_PATH = "~/.mempalace/"
_DEFAULT_COLLECTION = "mempalace_drawers"
_DEFAULT_WING = "wing_general"
_DEFAULT_TTL_DAYS = 90

NOISE_PATTERNS = [
    "nothing to save",
    "no new memories",
    "no memories to save",
    "no significant memories",
    "nothing new to save",
    "nothing important to save",
    "no information to save",
]


def _load_config() -> dict:
    """Load config from env vars with $HERMES_HOME/.mempalace/config.json overrides.

    Also supports multi-profile via memory.profiles in hermes config.yaml.
    """
    from hermes_constants import get_hermes_home

    config = {
        "palace_path": os.environ.get("MEMPALACE_PATH", _DEFAULT_PALACE_PATH),
        "collection_name": os.environ.get("MEMPALACE_COLLECTION", _DEFAULT_COLLECTION),
        "default_wing": os.environ.get("MEMPALACE_DEFAULT_WING", _DEFAULT_WING),
        "ttl_days": int(os.environ.get("MEMPALACE_TTL_DAYS", _DEFAULT_TTL_DAYS)),
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
        "Use after decisions, discoveries, or important exchanges. "
        "Content matching noise patterns like 'Nothing to save' is automatically skipped. "
        "Supports optional TTL (default 90 days) for automatic expiry."
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
            "ttl_days": {
                "type": "integer",
                "description": "Time-to-live in days (0=never, default: 90).",
            },
            "expires_at": {
                "type": "string",
                "description": "ISO timestamp for explicit expiry override.",
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
            "max_hops": {
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

RECALL_MISTAKES_SCHEMA = {
    "name": "mempalace_recall_mistakes",
    "description": (
        "Recall past mistakes by domain to prevent repeating errors. "
        "Returns all recorded mistakes for a domain with severity."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Domain tag to recall (e.g., 'android', 'minecraft', 'skill').",
            },
        },
        "required": ["domain"],
    },
}

SEARCH_MISTAKES_SCHEMA = {
    "name": "mempalace_search_mistakes",
    "description": (
        "Search mistakes registry for relevant past errors. "
        "Use before tackling tasks to avoid repeating mistakes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default: 5).",
            },
        },
        "required": ["query"],
    },
}

RECORD_MISTAKE_SCHEMA = {
    "name": "mempalace_record_mistake",
    "description": (
        "Record a mistake or error to the mistakes registry. "
        "Use after any significant error to build institutional memory."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Description of what happened.",
            },
            "domain": {
                "type": "string",
                "description": "Domain area (e.g., 'android', 'ios', 'minecraft', 'web', 'general').",
            },
            "severity": {
                "type": "string",
                "enum": ["HIGH", "MED", "LOW"],
                "description": "Error severity.",
            },
            "error_type": {
                "type": "string",
                "enum": [
                    "runtime",
                    "build",
                    "logic",
                    "network",
                    "workflow",
                    "security",
                ],
                "description": "Type of error.",
            },
        },
        "required": ["content", "domain", "severity"],
    },
}

SESSION_WRITE_SCHEMA = {
    "name": "mempalace_session_write",
    "description": (
        "Write a session entry for project tracking across sessions. "
        "AAAK format: SESSION → date|project|summary|next. "
        "Use at session end to record what happened and what's next. "
        "This is the primary way to maintain multi-session project context."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "Session date (YYYY-MM-DD, auto-detects if not provided).",
            },
            "project": {
                "type": "string",
                "description": "Project/activity tag (e.g., 'Collatz:arithprogt3k').",
            },
            "summary": {
                "type": "string",
                "description": "What happened in this session.",
            },
            "next": {
                "type": "string",
                "description": "What needs to happen next.",
            },
        },
        "required": ["project", "summary"],
    },
}

SESSION_READ_SCHEMA = {
    "name": "mempalace_session_read",
    "description": (
        "Read recent session entries to restore multi-session project context. "
        "Use at session start to pick up where you left off. "
        "Returns entries sorted by date (newest first)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Filter by project tag (optional).",
            },
            "last_n": {
                "type": "integer",
                "description": "Number of recent sessions (default: 5).",
            },
        },
        "required": [],
    },
}

NOISE_FILTER_SCHEMA = {
    "name": "mempalace_noise_filter",
    "description": (
        "Manage noise patterns that are filtered when saving memories. "
        "Use mode 'list' to see patterns, 'add' to add, 'remove' to remove."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["list", "add", "remove"],
                "description": "Operation: list current patterns, add a new one, or remove an existing one.",
            },
            "pattern": {
                "type": "string",
                "description": "Pattern to add or remove (required for add/remove modes).",
            },
        },
        "required": ["mode"],
    },
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

SUMMARIZE_SCHEMA = {
    "name": "mempalace_summarize",
    "description": (
        "Get a structured summary of the palace — wings, rooms, drawer counts, "
        "oldest/newest entries, and storage stats. Use at session start to understand "
        "the current memory state. Supports per-wing or per-room scope, and "
        "'full' mode that reads actual content (slower)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "wing": {
                "type": "string",
                "description": "Optional wing to summarize.",
            },
            "room": {
                "type": "string",
                "description": "Optional room to summarize (requires wing).",
            },
            "full": {
                "type": "boolean",
                "description": "Read actual content for synthesis (slower, default: false).",
            },
            "limit": {
                "type": "integer",
                "description": "Max content samples for full mode (default: 20).",
            },
        },
        "required": [],
    },
}

PROFILE_LIST_SCHEMA = {
    "name": "mempalace_profile_list",
    "description": "List all MemPalace profiles with drawer counts.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

PROFILE_SWITCH_SCHEMA = {
    "name": "mempalace_profile_switch",
    "description": "Switch to a different MemPalace profile.",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Profile name to switch to."},
        },
        "required": ["name"],
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
    SESSION_WRITE_SCHEMA,
    SESSION_READ_SCHEMA,
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
    SUMMARIZE_SCHEMA,
    PROFILE_LIST_SCHEMA,
    PROFILE_SWITCH_SCHEMA,
    RECORD_MISTAKE_SCHEMA,
    SEARCH_MISTAKES_SCHEMA,
    RECALL_MISTAKES_SCHEMA,
    NOISE_FILTER_SCHEMA,
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
        self._taxonomy_cache: Dict[str, Dict[str, int]] = {}
        self._noise_patterns: List[str] = []
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

    def _build_taxonomy_cache(self) -> None:
        if not self._collection:
            return
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
        sessions_block = self._get_recent_sessions_block()

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
            elif tool_name == "mempalace_session_write":
                return self._tool_session_write(args)
            elif tool_name == "mempalace_session_read":
                return self._tool_session_read(args)
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
            elif tool_name == "mempalace_summarize":
                return self._tool_summarize(args)
            elif tool_name == "mempalace_profile_list":
                return self._tool_profile_list()
            elif tool_name == "mempalace_profile_switch":
                return self._tool_profile_switch(args)
            elif tool_name == "mempalace_record_mistake":
                return self._tool_record_mistake(args)
            elif tool_name == "mempalace_search_mistakes":
                return self._tool_search_mistakes(args)
            elif tool_name == "mempalace_recall_mistakes":
                return self._tool_recall_mistakes(args)
            elif tool_name == "mempalace_noise_filter":
                return self._tool_noise_filter(args)
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
            return json.dumps({"taxonomy": self._taxonomy_cache})
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
            raw_results = (
                results.get("results", []) if isinstance(results, dict) else results
            )
            for r in raw_results:
                r_wing = r.get("wing", "")
                r_room = r.get("room", "")
                if wing and r_wing != wing:
                    continue
                if room and r_room != room:
                    continue
                items.append(
                    {
                        "text": r.get("text", r.get("content", "")),
                        "score": r.get("similarity", r.get("distance", 0)),
                        "wing": r_wing,
                        "room": r_room,
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
            from mempalace.dialect import Dialect

            return json.dumps(
                {
                    "aaak_spec": {
                        "format": "ENTITY → codes|topic|quote|flags",
                        "example": "NEH → android,kotlin|pref_nullcheck|CORE",
                    }
                }
            )
        except ImportError:
            return json.dumps({"error": "AAAK dialect not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _is_noise(self, content: str) -> bool:
        """Check if content matches noise patterns that shouldn't be stored."""
        if not self._noise_patterns:
            self._noise_patterns = self._load_noise_patterns()
        content_lower = content.lower().strip()
        for pattern in self._noise_patterns:
            if pattern in content_lower:
                return True
        return False

    def _tool_add_drawer(self, args: dict) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            import uuid
            from datetime import datetime, timedelta

            content = args.get("content", "")
            wing = args.get("wing", self._default_wing)
            room = args.get("room", "general")
            closet = args.get("closet", "hall_general")

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

            metadata = {"wing": wing, "room": room, "closet": closet}
            if expires_at:
                metadata["expires_at"] = expires_at

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

            return json.dumps(
                {
                    "result": "Remembered",
                    "extracted": True,
                    "memories": stored,
                    "count": len(stored),
                }
            )

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
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            drawer_id = args.get("drawer_id", "")
            self._collection.delete(ids=[drawer_id])
            self._build_taxonomy_cache()
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
            stats = self._kg.stats()
            return json.dumps({"stats": stats})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_traverse(self, args: dict) -> str:
        try:
            from mempalace.palace_graph import traverse

            start_room = args.get("start_room", "")
            max_hops = args.get("max_hops", args.get("max_depth", 3))
            results = traverse(start_room, max_hops=max_hops, col=self._collection)
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
            tunnels = find_tunnels(wing_a=wing_a, wing_b=wing_b, col=self._collection)
            return json.dumps({"wing_a": wing_a, "wing_b": wing_b, "tunnels": tunnels})
        except ImportError:
            return json.dumps({"error": "palace_graph not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_graph_stats(self) -> str:
        try:
            from mempalace.palace_graph import graph_stats

            stats = graph_stats(col=self._collection)
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

    def _tool_summarize(self, args: dict) -> str:
        """Summarize the palace - wings, rooms, counts, oldest/newest."""
        if not self._collection:
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
        try:
            name = args.get("name", "")
            if not name:
                return json.dumps({"error": "Profile name required"})

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
            if not profile_path.exists():
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

    def _tool_record_mistake(self, args: dict) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            import uuid
            from datetime import datetime, timedelta

            content = args.get("content", "")
            domain = args.get("domain", "general")
            severity = args.get("severity", "MED")
            error_type = args.get("error_type", "runtime")

            room = f"room_{domain}"
            closet = "hall_errors"

            entity_code = f"{domain.upper()[:4]}_{len(content)}"
            formatted = f"{entity_code} → {domain}|mistake|{content}|error_type:{error_type},severity:{severity}"

            metadata = {
                "wing": "wing_mistakes",
                "room": room,
                "closet": closet,
                "domain": domain,
                "severity": severity,
                "error_type": error_type,
            }

            doc_id = str(uuid.uuid4())
            self._collection.add(
                documents=[formatted],
                metadatas=[metadata],
                ids=[doc_id],
            )
            self._update_taxonomy_cache("wing_mistakes", room, 1)

            if self._kg:
                self._kg.add_triple(
                    entity_code,
                    "mistake",
                    content,
                    valid_from=datetime.now().isoformat(),
                )

            return json.dumps(
                {
                    "result": "Mistake recorded",
                    "mistake_id": doc_id,
                    "domain": domain,
                    "severity": severity,
                }
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_search_mistakes(self, args: dict) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            query = args.get("query", "")
            limit = args.get("limit", 5)

            results = self._collection.get(
                where={"wing": "wing_mistakes"},
                include=["metadatas", "documents"],
            )
            items = []
            for i, doc in enumerate(results.get("documents", []) or []):
                meta = results.get("metadatas", [])[i]
                doc_lower = doc.lower()
                query_lower = query.lower()
                if query_lower and query_lower not in doc_lower:
                    continue
                items.append(
                    {
                        "text": doc,
                        "domain": meta.get("domain"),
                        "severity": meta.get("severity"),
                        "error_type": meta.get("error_type"),
                    }
                )
                if len(items) >= limit:
                    break

            return json.dumps({"results": items, "count": len(items)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _tool_recall_mistakes(self, args: dict) -> str:
        if not self._collection:
            return json.dumps({"error": "Palace not initialized"})
        try:
            domain = args.get("domain", "")
            if not domain:
                return json.dumps({"error": "Domain required"})

            room = f"room_{domain}"
            results = self._collection.get(
                where={"wing": "wing_mistakes", "room": room},
                include=["metadatas", "documents"],
            )
            items = []
            for i, doc in enumerate(results.get("documents", []) or []):
                meta = results.get("metadatas", [])[i]
                items.append(
                    {
                        "text": doc,
                        "severity": meta.get("severity"),
                        "error_type": meta.get("error_type"),
                    }
                )

            return json.dumps(
                {"domain": domain, "mistakes": items, "count": len(items)}
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _load_noise_patterns(self) -> List[str]:
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
        if not self._palace_path:
            return default_patterns

        config_path = self._palace_path / "noise_patterns.json"
        if config_path.exists():
            try:
                import json as json_lib

                custom = json_lib.loads(config_path.read_text())
                patterns = custom.get("patterns", [])
                return patterns + [p for p in default_patterns if p not in patterns]
            except Exception:
                pass
        return default_patterns

    def _save_noise_patterns(self, patterns: List[str]) -> None:
        """Save noise patterns to config."""
        if not self._palace_path:
            return
        config_path = self._palace_path / "noise_patterns.json"
        try:
            import json as json_lib

            config_path.write_text(json_lib.dumps({"patterns": patterns}, indent=2))
        except Exception:
            pass

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
