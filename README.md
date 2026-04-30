# MemPalace — Hermes Memory Provider Plugin

Local-first AI memory system with palace structure (Wings → Rooms → Closets → Drawers) backed by ChromaDB.

## Features

- **Local-only**: ChromaDB + SQLite, no cloud, no API keys
- **Palace hierarchy**: Organize memories in wings, rooms, closets
- **Semantic recall**: Search with filters (wing, room, closet, category, subject, flags)
- **Knowledge graph**: Store and query facts (subject→predicate→object)
- **Session memory**: Auto-remember conversations with context
- **Tools**: 45 tools for read, write, search, KG, navigation, and more

## Requirements

- Python 3.9+
- `chromadb`
- `pyyaml`

## Quick Start

```bash
# Initialize palace
hermes mempalace init ~/.mempalace/

# Mine data
hermes mempalace mine ~/projects/myapp

# Check status
hermes mempalace status
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
- `mempalace_record_mistake` — Record mistake
- `mempalace_search_mistakes` — Search mistakes
- `mempalace_recall_mistakes` — Recall by domain

### Utilities
- `mempalace_summarize` — Palace summary
- `mempalace_watch` — Monitor changes
- `mempalace_expiring` — Expiring drawers
- `mempalace_noise_filter` — Manage noise patterns
- `mempalace_backup` — Export to JSON
- `mempalace_restore` — Restore from backup
- `mempalace_profile_list` — List profiles
- `mempalace_profile_switch` — Switch profile

## Architecture

```
~/.mempalace/
├── palace/              # ChromaDB vector store
├── knowledge_graph.db  # SQLite KG
├── config.json         # Palace config
└── identity.txt        # L0 identity
```