# MemPalace — Hermes Memory Provider Plugin

Local-first AI memory system with palace structure (Wings → Rooms → Closets → Drawers), AAAK compression dialect, and ChromaDB-backed semantic search. 96.6% recall on LongMemEval benchmark.

## What It Is

MemPalace is a **long-term memory layer** for the Hermes AI agent. It sits on top of ChromaDB (vector store) and SQLite (knowledge graph) to give the agent persistent, searchable memory across sessions.

The core idea: memories are **spatial** and **semantic**. You navigate them like a building (wings → rooms → closets → drawers), and you find them by meaning, not just keywords.

---

## The Palace Metaphor

Think of your memory as a building:

| Level | What It Represents | Example |
|-------|-------------------|---------|
| **Wing** | Domain or agent | `wing_myos`, `wing_general` |
| **Room** | Topic or activity | `learnings`, `sessions`, `preferences` |
| **Closet** | Content classification | `personal`, `projects`, `world` |
| **Drawer** | Individual memory entry | A single fact, preference, or note |

Every drawer has:
- A unique **UUID**
- **Content** (the actual memory text or AAAK shorthand)
- **Metadata** — subject, closet, category, flags, timestamps
- **Embedding** — ChromaDB computes this automatically for semantic search
- **parent_id** — links to previous versions for versioning chains
- **TTL / expires_at** — optional expiry for transient memories

---

## The Learning Framework

The learning framework is the core API for filing, retrieving, and updating knowledge. It has three primary tools:

### 1. File — `mempalace_learn`

Store new knowledge in the palace. The key feature is **recall-before-filing**: before storing, it runs a broad semantic search to check if you already know something similar. If a duplicate exists, it returns that instead of filing redundant content.

```python
mempalace_learn(
    content="Nehuen prefers using Postgres for database work because it is more reliable",
    title="Nehuen's database preference",
    subject="Nehuen",
    predicate="prefers",
    category="preference",
    closet="personal",      # personal | projects | world
    auto_detect=True,       # default — runs duplicate check first
)
```

Returns:
```json
{
  "drawer_id": "c1b967c2-4acc-4980-88de-2e0dd04fe298",
  "title": "Nehuen's database preference",
  "subject": "Nehuen",
  "closet": "personal",
  "category": "preference",
  "stored": true
}
```

The drawer is stored in the `learnings` room under `wing_myos`, embedded and ready for semantic search.

### 2. Retrieve — `mempalace_recall`

Semantic search across all drawers. You can filter by subject, closet, category, or flags. Results are ranked by similarity.

```python
mempalace_recall(
    query="what database does Nehuen like",
    closet="personal",
    limit=3,
)
```

Returns:
```json
{
  "results": [
    {
      "id": "c1b967c2-4acc-4980-88de-2e0dd04fe298",
      "content": "Nehuen prefers using Postgres for database work because it is more reliable",
      "subject": "Nehuen",
      "closet": "personal",
      "category": "preference",
      "similarity_score": 0.812,
      "created_at": "2026-04-29T21:03:56+00:00",
      "last_accessed": "2026-04-30T01:17:50+00:00"
    }
  ],
  "count": 1,
  "total": 1
}
```

Each recall updates the `last_accessed` timestamp on matched drawers — this feeds the "accessed" sort mode.

### 3. Update — `mempalace_update`

Modify an existing drawer. Supports three modes:

```python
# Fix something wrong
mempalace_update(
    drawer_id="c1b967c2-4acc-4980-88de-2e0dd04fe298",
    mode="correct",
    content="...correction text...",
)

# Extend with new context (appends, doesn't overwrite)
mempalace_update(
    drawer_id="c1b967c2-4acc-4980-88de-2e0dd04fe298",
    mode="extend",
    extend_with="He also uses SQLite for small projects.",
)

# Replace entirely
mempalace_update(
    drawer_id="c1b967c2-4acc-4980-88de-2e0dd04fe298",
    mode="replace",
    content="New full content",
)
```

Every update creates a **new version** linked by `parent_id`. You can retrieve the full version chain with `mempalace_get_versions(drawer_id="...")`.

---

## Convenience Tools

### `mempalace_remember` — Natural Language Filing

The simplest interface. Just say what you want to remember:

```
mempalace_remember(content="Nehuen works out every morning")
mempalace_remember(content="T3Code uses Next.js 15 on port 3000", category="fact")
```

It auto-detects the subject, closet, and category, then files it into the right room.

### `mempalace_recall_all` — Bulk Context Load

Fetch all memories at once — useful at session start to restore context:

```
mempalace_recall_all(cap=20, closet="personal", sort="recent")
```

Supports closet filtering and three sort modes: `recent` (created_at), `accessed` (last_accessed), `relevance`.

---

## Session & Diary Tools

### Cross-Session Project Tracking

When you finish a working session, file what happened:

```
mempalace_session_write(
    project="recipe-api:rest-v2",
    summary="Migrated ingredients endpoint to GraphQL. Resolved N+1 query on /recipes/:id. Added cursor pagination.",
    next="Update /search endpoint. Write migration docs. Deploy to staging."
)
```

Next session, restore context:

```
mempalace_session_read(project="recipe-api", last_n=5)
```

The system prompt auto-injects the 5 most recent sessions at startup — no manual tracking needed.

### Agent Diary

Each agent (e.g. `reviewer`, `architect`) maintains its own diary in AAAK shorthand:

```
mempalace_diary_write(
    agent="architect",
    entry="SESSION → 2026-04-29|design|chose Postgres over SQLite|next: migration script"
)
```

---

## The AAAK Compression Dialect

AAAK (Autonomous Autonomous Autonomous Knowledge) is a 30x lossless shorthand for storing compressed knowledge in drawers. It keeps context loading fast without losing information.

### Format

```
ENTITY → codes|topic|"key_quote"|flags
```

- **codes** — comma-separated tags (language, framework, domain)
- **topic** — short topic descriptor
- **"key_quote"** — verbatim phrase worth preserving
- **flags** — DECISION, CORE, TECHNICAL, SENSITIVE, PIVOT

### Examples

```
NEHUEN → workout,daily|pref_exercise|streak:7days|DECISION
AUTH_DB → Postgres|db,migration|reason:reliable|DECISION
MYSQL → MySQL8,production|db,legacy|reason:maturity|PROJECT
RECIPE_APP → recipe,api|stack|Node+Postgres|FACT
```

### When to Use AAAK

Use AAAK for:
- Session summaries (file at end of each session)
- Cross-session project status (what we did, what's next)
- Compressed facts with multiple dimensions (language + preference + reason)
- Recurring patterns (Mistakes registry entries)

Use **full text** for:
- Verbatim quotes worth preserving exactly
- Complex decisions with nuanced reasoning
- First-time discoveries with full context

Preview compression before saving:

```
mempalace_preview_aaak(content="Nehuen prefers Postgres for database work because...")
# Returns: "NEHUEN → Postgres,db|pref|reason:reliable|DECISION"
```

---

## Knowledge Graph

Beyond vector search, MemPalace has a **structured knowledge graph** backed by SQLite. Use it for explicit relationships:

```python
# Store a fact triple
mempalace_kg_add(
    subject="Nehuen",
    predicate="lives_in",
    object="Buenos Aires",
    valid_from="2026-04-01",
)

# Query all relationships for an entity
mempalace_kg_query(entity="Nehuen")

# Explore outward from an entity
mempalace_kg_explore(entity="Nehuen", depth=2, direction="out")
```

---

## Workflow Examples

### Remembering a User Preference

```
User: Remember that I prefer dark mode in all my terminals

Assistant:
mempalace_remember(content="Nehuen prefers dark mode in all terminals", category="preference")
# → filed in wing_myos / learnings / personal
```

### Project Session Tracking

```
# End of session:
mempalace_session_write(
    project="recipe-api:rest-v2",
    summary="Migrated ingredients endpoint to GraphQL. Resolved N+1 query on /recipes/:id. Added cursor pagination.",
    next="Update /search endpoint. Write migration docs. Deploy to staging."
)

# Next session — start fresh:
mempalace_session_read(project="recipe-api", last_n=3)
# → system_prompt_block auto-injects 5 recent sessions at startup
```

### Finding a Past Decision

```
mempalace_recall(
    query="why did we choose Postgres over SQLite",
    closet="personal",
    category="decision",
    limit=5,
)
```

### Recording a Mistake

```
mempalace_record_mistake(
    content="ChromaDB compound filter {\"wing\": \"x\", \"room\": \"y\"} is invalid — must use $and operator",
    domain="hermes",
    error_type="runtime",
    severity="HIGH",
)
```

Next time you touch ChromaDB filters, check the mistakes registry first:

```
mempalace_recall_mistakes(domain="hermes")
```

---

## Architecture

```
~/.mempalace/
├── palace/                  # ChromaDB vector store (embeddings + metadata)
│   └── mempalace_drawers   # Collection of all drawer documents
├── knowledge_graph.db       # SQLite KG (triples, timelines)
├── config.json              # Palace config
└── identity.txt             # L0 identity layer
```

### ChromaDB vs SQLite

| Use ChromaDB (vector) | Use SQLite KG |
|----------------------|---------------|
| Semantic search | Explicit relationships |
| Natural language recall | Fact triples with temporal validity |
| Similarity matching | Timelines, exploration |
| Unstructured content | Structured, linkable entities |

---

## Requirements

- Python 3.9+
- `chromadb`
- `pyyaml`

## Quick Start

```bash
# Initialize palace
hermes mempalace init ~/.mempalace/

# Check status
hermes mempalace status

# Mine data
hermes mempalace mine ~/projects/myapp
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `hermes mempalace setup` | Interactive setup |
| `hermes mempalace status` | Palace overview |
| `hermes mempalace init <dir>` | Initialize palace |
| `hermes mempalace mine <dir>` | Mine data |
| `hermes mempalace memories` | List memories |
| `hermes mempalace wings` | List wings and rooms |
| `hermes mempalace enable` | Enable plugin |
| `hermes mempalace disable` | Disable plugin |

---

## Tools (45 total)

### Read
- `mempalace_status` — Palace overview + drawer count
- `mempalace_list_wings` — List wings with counts
- `mempalace_list_rooms` — List rooms in a wing
- `mempalace_get_taxonomy` — Full hierarchy tree
- `mempalace_search` — Semantic search with filters
- `mempalace_recall` — Semantic recall with pagination
- `mempalace_recall_all` — List all drawers
- `mempalace_check_duplicate` — Check for duplicates
- `mempalace_get_aaak_spec` — AAAK dialect reference

### Write
- `mempalace_add_drawer` — Store verbatim content
- `mempalace_remember` — Remember with auto-room detection
- `mempalace_remember_fact` — Add KG fact via natural language
- `mempalace_delete_drawer` — Remove by ID
- `mempalace_set_drawer_flags` — Tag drawers
- `mempalace_preview_aaak` — Preview compression

### Knowledge Graph
- `mempalace_kg_query` — Query entity relationships
- `mempalace_kg_add` — Add fact triple
- `mempalace_kg_invalidate` — Mark fact as ended
- `mempalace_kg_timeline` — Entity timeline
- `mempalace_kg_stats` — Graph stats
- `mempalace_kg_explore` — Directional traversal

### Session & Diary
- `mempalace_session_write` — Write session entry
- `mempalace_session_read` — Read sessions
- `mempalace_session_diff` — Compare sessions
- `mempalace_diary_write` — Write diary
- `mempalace_diary_read` — Read diary

### Navigation
- `mempalace_traverse` — Walk graph across wings
- `mempalace_find_tunnels` — Find rooms bridging wings
- `mempalace_graph_stats` — Connectivity stats

### Mistakes
- `mempalace_record_mistake` — Record a mistake (domain, severity, error_type)
- `mempalace_recall_mistakes` — Recall all mistakes for a domain
- `mempalace_search_mistakes` — Search mistakes semantically
- `mempalace_distill_mistake` — Distill a recorded mistake into a structured lesson

### Utilities
- `mempalace_summarize` — Palace summary
- `mempalace_watch` — Monitor changes
- `mempalace_expiring` — Expiring drawers
- `mempalace_noise_filter` — Manage noise patterns
- `mempalace_backup` — Export to JSON
- `mempalace_restore` — Restore from backup
- `mempalace_profile_list` — List profiles
- `mempalace_profile_switch` — Switch profile
