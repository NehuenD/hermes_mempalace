"""All MemPalace tool schemas — extracted from monolithic __init__.py."""

from __future__ import annotations

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
    "parameters": {
        "type": "object",
        "properties": {
            "offset": {
                "type": "integer",
                "description": "Number of wings to skip (for pagination).",
            },
            "limit": {
                "type": "integer",
                "description": "Max wings to return (default: 50).",
            },
        },
        "required": [],
    },
}

LIST_ROOMS_SCHEMA = {
    "name": "mempalace_list_rooms",
    "description": "List all rooms within a specific wing.",
    "parameters": {
        "type": "object",
        "properties": {
            "wing": {"type": "string", "description": "Wing name to list rooms for."},
            "offset": {
                "type": "integer",
                "description": "Number of rooms to skip (for pagination).",
            },
            "limit": {
                "type": "integer",
                "description": "Max rooms to return (default: 50).",
            },
        },
        "required": ["wing"],
    },
}

GET_TAXONOMY_SCHEMA = {
    "name": "mempalace_get_taxonomy",
    "description": "Get the full wing → room → count taxonomy tree.",
    "parameters": {
        "type": "object",
        "properties": {
            "offset": {
                "type": "integer",
                "description": "Number of entries to skip (for pagination).",
            },
            "limit": {
                "type": "integer",
                "description": "Max entries to return (default: 100).",
            },
        },
        "required": [],
    },
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
            "offset": {
                "type": "integer",
                "description": "Number of results to skip (for pagination).",
            },
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
            "parent_id": {
                "type": "string",
                "description": "ID of the parent drawer this replaces (for versioning).",
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

GET_VERSIONS_SCHEMA = {
    "name": "mempalace_get_versions",
    "description": (
        "Get the version chain for a drawer via parent_id links. "
        "Shows all versions from current to original."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "drawer_id": {
                "type": "string",
                "description": "The drawer ID to get versions for.",
            },
            "limit": {
                "type": "integer",
                "description": "Max versions to return (default: 20).",
            },
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

KG_EXPLORE_SCHEMA = {
    "name": "mempalace_kg_explore",
    "description": (
        "Explore the knowledge graph directionally from an entity. "
        "Traverse outgoing (subject->predicate->object) or incoming (object<-subject) relations. "
        "Returns entities and their relationships at each depth level."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "entity": {
                "type": "string",
                "description": "Starting entity to explore from.",
            },
            "direction": {
                "type": "string",
                "enum": ["out", "in", "both"],
                "description": "Traversal direction: out (subject->), in (<-object), both (default: both).",
            },
            "depth": {
                "type": "integer",
                "description": "Max depth to traverse (default: 2).",
            },
            "limit": {
                "type": "integer",
                "description": "Max results per depth (default: 20).",
            },
        },
        "required": ["entity"],
    },
}

REMEMBER_FACT_SCHEMA = {
    "name": "mempalace_remember_fact",
    "description": (
        "Add a fact to the knowledge graph using natural language. "
        "Parses sentences like 'Nehuen lives in Argentina' into (subject, predicate, object). "
        "Supports patterns: 'X is a Y', 'X has Y', 'X lives in Y', 'X works as Y', etc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": "A fact in natural language, e.g., 'Nehuen lives in Argentina' or 'Python is a programming language'.",
            },
            "valid_from": {
                "type": "string",
                "description": "Start date for temporal validity (YYYY-MM-DD, default: today).",
            },
        },
        "required": ["fact"],
    },
}

PREVIEW_AAAK_SCHEMA = {
    "name": "mempalace_preview_aaak",
    "description": (
        "Preview how content would be compressed using AAAK format without saving. "
        "Use before mempalace_add_drawer to see the compressed output and decide whether to save."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Content to preview AAAK compression on.",
            },
        },
        "required": ["content"],
    },
}

SET_DRAWER_FLAGS_SCHEMA = {
    "name": "mempalace_set_drawer_flags",
    "description": (
        "Set flags/tags on a drawer for organization and filtering. "
        "Flags are user-defined labels like 'important', 'review', 'archived', etc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "drawer_id": {
                "type": "string",
                "description": "The drawer ID to tag.",
            },
            "flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of flag strings to set on the drawer.",
            },
            "mode": {
                "type": "string",
                "enum": ["set", "add", "remove"],
                "description": "Mode: set (replace all), add (append), or remove (delete).",
            },
        },
        "required": ["drawer_id", "flags"],
    },
}

WATCH_SCHEMA = {
    "name": "mempalace_watch",
    "description": (
        "Watch a query and get notified when matching drawers change. "
        "Returns a list of current matches. Use periodically to check for changes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query to watch (similar to search query).",
            },
            "wing": {"type": "string", "description": "Optional wing to scope."},
            "room": {"type": "string", "description": "Optional room to scope."},
            "watch_id": {
                "type": "string",
                "description": "Optional watch ID from previous call to check for changes.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default: 10).",
            },
        },
        "required": ["query"],
    },
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

RECORD_MISTAKE_SCHEMA = {
    "name": "mempalace_record_mistake",
    "description": (
        'DEPRECATED: Use mempalace_learn with category="mistake" instead. '
        "This tool is kept for backward compatibility."
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

EXPIRING_SCHEMA = {
    "name": "mempalace_expiring",
    "description": (
        "Preview drawers that are about to expire based on TTL. "
        "Shows what will disappear before the next TTL sweep so you can rescue or extend them."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "Show drawers expiring within this many days (default: 7).",
            },
            "wing": {
                "type": "string",
                "description": "Filter by wing (optional).",
            },
            "room": {
                "type": "string",
                "description": "Filter by room (optional).",
            },
            "rescue": {
                "type": "boolean",
                "description": "If true, extend TTL for listed drawers by ttl_days (default: 90).",
            },
            "ttl_days": {
                "type": "integer",
                "description": "Days to extend TTL when rescue=true (default: 90).",
            },
        },
        "required": [],
    },
}

BACKUP_SCHEMA = {
    "name": "mempalace_backup",
    "description": (
        "Export all palace drawers to a JSON backup file. "
        "Backs up documents, metadata (wing, room, closet, expires_at, session_date, session_project), and KG triples. "
        "Use before schema migrations or before a TTL sweep."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Backup file path (default: ~/.mempalace/backups/backup_YYYYMMDD.json).",
            },
            "include_kg": {
                "type": "boolean",
                "description": "Include KG triples in backup (default: true).",
            },
        },
        "required": [],
    },
}

RESTORE_SCHEMA = {
    "name": "mempalace_restore",
    "description": (
        "Restore palace from a JSON backup file. "
        "Restores drawers and optionally KG triples. Use after data loss or before loading a backup."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to backup file to restore from.",
            },
            "clear_first": {
                "type": "boolean",
                "description": "Clear existing palace before restoring (default: false).",
            },
            "include_kg": {
                "type": "boolean",
                "description": "Restore KG triples from backup (default: true).",
            },
        },
        "required": ["path"],
    },
}

SESSION_DIFF_SCHEMA = {
    "name": "mempalace_session_diff",
    "description": (
        "Show what changed between two sessions by comparing their summaries. "
        "Returns added, removed, and modified entries based on session_project and date range."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Project to diff (optional, defaults to most recent active project).",
            },
            "before_date": {
                "type": "string",
                "description": "Compare sessions before this date (YYYY-MM-DD, default: 7 days ago).",
            },
            "after_date": {
                "type": "string",
                "description": "Compare sessions after this date (YYYY-MM-DD, default: today).",
            },
        },
        "required": [],
    },
}

RECALL_SCHEMA = {
    "name": "mempalace_recall",
    "description": (
        "Access learnings with semantic similarity and filters. "
        "The primary tool for retrieving stored knowledge. "
        "Returns relevant learnings ranked by similarity."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Semantic query — matches against all learnings.",
            },
            "subject": {
                "type": "string",
                "description": "Filter by subject entity (e.g. 'Nehuen', 'T3Code').",
            },
            "closet": {
                "type": "string",
                "description": "Filter by closet: 'personal', 'projects', 'world'.",
            },
            "category": {
                "type": "string",
                "description": "Filter by category: 'fact', 'preference', 'decision', 'person', 'project', 'mistake'.",
            },
            "flag": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by flags (e.g. ['CORE', 'EXPERIMENTAL']).",
            },
            "similarity": {
                "type": "string",
                "description": "Override query with explicit similarity string.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default: 3, max: 10).",
            },
            "offset": {
                "type": "integer",
                "description": "Skip first N results (default: 0).",
            },
        },
        "required": [],
    },
}

RECALL_ALL_SCHEMA = {
    "name": "mempalace_recall_all",
    "description": (
        "Fetch all learnings at once. Loads fresh context from MemPalace. "
        "Called on first real interaction after session start."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "closet": {
                "type": "string",
                "description": "Filter by closet: 'personal', 'projects', 'world' (optional).",
            },
            "cap": {
                "type": "integer",
                "description": "Max learnings to return (default: 20, max: 100).",
            },
            "sort": {
                "type": "string",
                "enum": ["recent", "accessed", "relevance"],
                "description": "Sort order: 'recent' (default), 'accessed' (last_accessed desc), 'relevance'.",
            },
            "category": {
                "type": "string",
                "description": "Filter by category: 'fact', 'preference', 'decision', 'person', 'project', 'mistake'.",
            },
        },
        "required": [],
    },
}

LEARN_SCHEMA = {
    "name": "mempalace_learn",
    "description": (
        "File a new piece of knowledge. Automatically checks for existing similar facts before storing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The knowledge to file. Verbatim original phrasing.",
            },
            "title": {
                "type": "string",
                "description": "Concise identifier summarizing the core fact.",
            },
            "description": {
                "type": "string",
                "description": "Brief one-sentence summary.",
            },
            "subject": {
                "type": "string",
                "description": "Subject entity (e.g. 'Nehuen', 'Collatz').",
            },
            "predicate": {
                "type": "string",
                "description": "Predicate/relationship (e.g. 'age', 'project', 'conjecture').",
            },
            "category": {
                "type": "string",
                "description": "Category: 'fact', 'preference', 'decision', 'person', 'project', 'mistake'.",
            },
            "closet": {
                "type": "string",
                "description": "Closet: 'personal', 'projects', 'world'.",
            },
            "auto_detect": {
                "type": "boolean",
                "description": "If true, check for existing similar facts before filing (default: True).",
            },
            "source_session": {
                "type": "string",
                "description": "Session this was learned in.",
            },
            "domain": {
                "type": "string",
                "description": "Domain area for mistakes (e.g., 'general', 'android', 'ios', 'web'). Required when category='mistake'.",
            },
            "severity": {
                "type": "string",
                "enum": ["HIGH", "MED", "LOW"],
                "description": "Error severity. Required when category='mistake'.",
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
                "description": "Type of error. Optional, defaults to 'runtime' when category='mistake'.",
            },
        },
        "required": ["content"],
    },
}

UPDATE_SCHEMA = {
    "name": "mempalace_update",
    "description": (
        "Modify an existing learning entry. Additive/completing, not destructive. "
        "mode=distill: run LLM analysis to extract root_cause, lesson, counterfactual, "
        "related_concepts, improvement_score from any drawer. Works on any content."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "drawer_id": {
                "type": "string",
                "description": "ID of the drawer to update.",
            },
            "mode": {
                "type": "string",
                "enum": ["replace", "correct", "extend", "distill"],
                "description": "'replace' (swap), 'correct' (fix wrong part), 'extend' (add context without removing), 'distill' (LLM analysis to extract structured lessons).",
            },
            "content": {
                "type": "string",
                "description": "New content (for replace/correct modes).",
            },
            "extend_with": {
                "type": "string",
                "description": "Additional content to append (for extend mode).",
            },
            "title": {
                "type": "string",
                "description": "Updated title.",
            },
            "description": {
                "type": "string",
                "description": "Updated description.",
            },
            "closet": {
                "type": "string",
                "enum": ["personal", "projects", "world", ""],
                "description": (
                    "Optional closet for cross-filing when mode=distill. "
                    "'projects' for technical lessons, 'personal' for habits. "
                    "Default: none — only stored in wing_mistakes for mistakes."
                ),
            },
        },
        "required": ["drawer_id", "mode"],
    },
}

DRAWER_HISTORY_SCHEMA = {
    "name": "mempalace_drawer_history",
    "description": ("Get all versions of a drawer by following parent_id chain."),
    "parameters": {
        "type": "object",
        "properties": {
            "drawer_id": {
                "type": "string",
                "description": "Current or historical drawer ID.",
            },
            "limit": {
                "type": "integer",
                "description": "Max versions (default: 20).",
            },
        },
        "required": ["drawer_id"],
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

SWEEP_SCHEMA = {
    "name": "mempalace_sweep",
    "description": "Manually trigger expired drawer sweep. Runs TTL cleanup on all expired memories.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

DISTILL_MISTAKE_SCHEMA = {
    "name": "mempalace_distill_mistake",
    "description": (
        'DEPRECATED: Use mempalace_update with mode="distill" instead. '
        "Runs LLM analysis to extract root cause, lesson, counterfactual, "
        "and improvement_score from a mistake."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "drawer_id": {
                "type": "string",
                "description": "ID of the drawer to distill.",
            },
            "closet": {
                "type": "string",
                "enum": ["personal", "projects", "world", ""],
                "description": (
                    "Optional closet for cross-filing when mode=distill. "
                    "projects for technical lessons, 'personal' for habits. "
                    "Default: none - only stored in wing_mistakes for mistakes."
                ),
            },
        },
        "required": ["drawer_id"],
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
    GET_VERSIONS_SCHEMA,
    SESSION_WRITE_SCHEMA,
    SESSION_READ_SCHEMA,
    KG_QUERY_SCHEMA,
    KG_ADD_SCHEMA,
    KG_INVALIDATE_SCHEMA,
    KG_TIMELINE_SCHEMA,
    KG_STATS_SCHEMA,
    KG_EXPLORE_SCHEMA,
    REMEMBER_FACT_SCHEMA,
    PREVIEW_AAAK_SCHEMA,
    SET_DRAWER_FLAGS_SCHEMA,
    WATCH_SCHEMA,
    TRAVERSE_SCHEMA,
    FIND_TUNNELS_SCHEMA,
    GRAPH_STATS_SCHEMA,
    DIARY_WRITE_SCHEMA,
    DIARY_READ_SCHEMA,
    REMEMBER_SCHEMA,
    SUMMARIZE_SCHEMA,
    PROFILE_LIST_SCHEMA,
    PROFILE_SWITCH_SCHEMA,
    SWEEP_SCHEMA,
    RECORD_MISTAKE_SCHEMA,
    DISTILL_MISTAKE_SCHEMA,
    NOISE_FILTER_SCHEMA,
    EXPIRING_SCHEMA,
    BACKUP_SCHEMA,
    RESTORE_SCHEMA,
    SESSION_DIFF_SCHEMA,
    RECALL_SCHEMA,
    RECALL_ALL_SCHEMA,
    LEARN_SCHEMA,
    UPDATE_SCHEMA,
    DRAWER_HISTORY_SCHEMA,
]

__all__ = [
    "STATUS_SCHEMA",
    "LIST_WINGS_SCHEMA",
    "LIST_ROOMS_SCHEMA",
    "GET_TAXONOMY_SCHEMA",
    "SEARCH_SCHEMA",
    "CHECK_DUPLICATE_SCHEMA",
    "GET_AAAK_SPEC_SCHEMA",
    "ADD_DRAWER_SCHEMA",
    "DELETE_DRAWER_SCHEMA",
    "GET_VERSIONS_SCHEMA",
    "REMEMBER_SCHEMA",
    "KG_QUERY_SCHEMA",
    "KG_ADD_SCHEMA",
    "KG_INVALIDATE_SCHEMA",
    "KG_TIMELINE_SCHEMA",
    "KG_STATS_SCHEMA",
    "KG_EXPLORE_SCHEMA",
    "REMEMBER_FACT_SCHEMA",
    "PREVIEW_AAAK_SCHEMA",
    "SET_DRAWER_FLAGS_SCHEMA",
    "WATCH_SCHEMA",
    "TRAVERSE_SCHEMA",
    "FIND_TUNNELS_SCHEMA",
    "GRAPH_STATS_SCHEMA",
    "RECORD_MISTAKE_SCHEMA",
    "SESSION_WRITE_SCHEMA",
    "SESSION_READ_SCHEMA",
    "NOISE_FILTER_SCHEMA",
    "EXPIRING_SCHEMA",
    "BACKUP_SCHEMA",
    "RESTORE_SCHEMA",
    "SESSION_DIFF_SCHEMA",
    "RECALL_SCHEMA",
    "RECALL_ALL_SCHEMA",
    "LEARN_SCHEMA",
    "UPDATE_SCHEMA",
    "DRAWER_HISTORY_SCHEMA",
    "DIARY_WRITE_SCHEMA",
    "DIARY_READ_SCHEMA",
    "SUMMARIZE_SCHEMA",
    "PROFILE_LIST_SCHEMA",
    "PROFILE_SWITCH_SCHEMA",
    "SWEEP_SCHEMA",
    "DISTILL_MISTAKE_SCHEMA",
    "ALL_TOOL_SCHEMAS",
]
