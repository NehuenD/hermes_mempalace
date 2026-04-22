# MemPalace Memory Provider Plugin

A local-first AI memory system with palace structure (Wings → Rooms → Closets → Drawers). Working on improving it periodically.

## About

This plugin is an implementation of [MemPalace](https://github.com/milla-jovovich/mempalace) as a memory provider for the Hermes Agent. This is my own version and I'm working on improving it and optimizing as much as I can. 

## Features

- **Local-first**: ChromaDB + SQLite, no cloud dependencies, no API key required
- **Palace Structure**: Hierarchical memory organization with Wings, Rooms, Closets, and Drawers
- **A Complete Set of Tools**: Full read/write access to palace, knowledge graph, navigation, diaries, and mistakes registry
- **Auto-Mining**: Automatic conversation chunking and room detection
- **AAAK Compression**: 30x lossless compression for fast context loading
- **KG Auto-Storage**: Facts extracted via `mempalace_remember` are automatically added to the knowledge graph
- **Pagination**: Offset/limit support on all list and search tools
- **Watching**: Monitor drawers for changes over time

## Requirements

- Python 3.9+
- `mempalace` package
- `chromadb>=0.4.0`
- `pyyaml>=6.0`

## Installation

```bash
# Clone into your Hermes plugins directory
git clone https://github.com/NehuenD/hermes_mempalace.git \
  ~/.hermes/plugins/mempalace

# Symlink into the memory providers directory
ln -s ~/.hermes/plugins/mempalace \
      ~/.hermes/hermes-agent/plugins/memory/mempalace

# Install dependencies
pip install mempalace chromadb>=0.4.0 pyyaml>=6.0

# Configure
hermes config set memory.provider mempalace
hermes mempalace setup
```

## Quick Start

```bash
# Initialize your palace
hermes mempalace init ~/.mempalace/

# Mine your data (projects, conversations)
hermes mempalace mine ~/projects/myapp

# Or mine conversations
hermes mempalace mine ~/chats/ --mode convos

# Check status
hermes mempalace status
```

## Configuration 

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `palace_path` | string | `~/.mempalace/` | Palace directory |
| `collection_name` | string | `mempalace_drawers` | ChromaDB collection |
| `default_wing` | string | `wing_general` | Default wing name |

Config is stored in `$HERMES_HOME/.mempalace/config.json`.

## Available Tools (35 total)

### Read Tools
| Tool | Description |
|------|-------------|
| `mempalace_status` | Palace overview + AAAK spec |
| `mempalace_list_wings` | List wings with drawer counts (+ pagination) |
| `mempalace_list_rooms` | List rooms within a wing (+ pagination) |
| `mempalace_get_taxonomy` | Full wing → room → count tree (+ pagination) |
| `mempalace_search` | Semantic search with wing/room filters (+ pagination) |
| `mempalace_check_duplicate` | Check if content already exists |
| `mempalace_get_aaak_spec` | AAAK dialect reference |

### Write Tools
| Tool | Description |
|------|-------------|
| `mempalace_add_drawer` | File verbatim content |
| `mempalace_delete_drawer` | Remove by ID |
| `mempalace_remember` | Remember with auto-extraction (+ auto-kg storage) |
| `mempalace_remember_fact` | Add KG triple via natural language |
| `mempalace_preview_aaak` | Preview AAAK compression before saving |
| `mempalace_set_drawer_flags` | Tag drawers with flags |

### Knowledge Graph Tools
| Tool | Description |
|------|-------------|
| `mempalace_kg_query` | Query entity relationships |
| `mempalace_kg_add` | Add fact triple (subject→predicate→object) |
| `mempalace_kg_invalidate` | Mark fact as ended |
| `mempalace_kg_timeline` | Chronological entity story |
| `mempalace_kg_stats` | Graph statistics |
| `mempalace_kg_explore` | Directional KG traversal (out/in/both) with depth |

### Navigation Tools
| Tool | Description |
|------|-------------|
| `mempalace_traverse` | Walk palace graph across wings |
| `mempalace_find_tunnels` | Find rooms bridging wings |
| `mempalace_graph_stats` | Graph connectivity stats |

### Monitoring Tools
| Tool | Description |
|------|-------------|
| `mempalace_watch` | Monitor queries for changes over time |
| `mempalace_expiring` | Preview drawers about to expire |

### Diary Tools
| Tool | Description |
|------|-------------|
| `mempalace_diary_write` | Write AAAK diary entry |
| `mempalace_diary_read` | Read recent diary entries |

### Mistakes Registry Tools
| Tool | Description |
|------|-------------|
| `mempalace_record_mistake` | Record a mistake to prevent repetition |
| `mempalace_search_mistakes` | Search mistakes by query |
| `mempalace_recall_mistakes` | Recall mistakes by domain |

### Utility Tools
| Tool | Description |
|------|-------------|
| `mempalace_noise_filter` | Manage noise patterns |
| `mempalace_backup` | Export palace to JSON |
| `mempalace_restore` | Restore from JSON backup |
| `mempalace_session_write` | Write session entry |
| `mempalace_session_read` | Read session entries |
| `mempalace_session_diff` | Compare sessions |
| `mempalace_summarize` | Palace summary |
| `mempalace_profile_list` | List profiles |
| `mempalace_profile_switch` | Switch profile |

## New Feature Usage

### mempalace_remember_fact — Natural Language KG Triple Entry

Add facts to the knowledge graph using simple sentences instead of subject/predicate/object:

```
Tool: mempalace_remember_fact
Parameters:
  - fact: "Nehuen lives in Argentina"
  - valid_from: "2024-01-01" (optional, defaults to today)
```

**Supported patterns:**
- `X lives in Y` → predicate: `lives_in`
- `X works as Y` → predicate: `works_as`
- `X is a Y` / `X is an Y` → predicate: `is_a`
- `X has Y` → predicate: `has`
- `X loves Y` → predicate: `loves`
- `X likes Y` → predicate: `likes`
- `X knows Y` → predicate: `knows`
- `X was born in Y` → predicate: `born_in`
- `X is from Y` → predicate: `is_from`

### mempalace_preview_aaak — Dry-Run AAAK Compression

Preview how content will be compressed before saving:

```
Tool: mempalace_preview_aaak
Parameters:
  - content: "Multi-line content to compress"
```

Returns:
- `original`: the raw input
- `aaak`: compressed output
- `original_length` / `compressed_length`: character counts
- `compression_ratio`: 30x means 30:1 compression

### mempalace_set_drawer_flags — Tagging Drawers

Add flags/tags to drawers for organization:

```
Tool: mempalace_set_drawer_flags
Parameters:
  - drawer_id: "uuid-of-drawer"
  - flags: ["important", "review"]
  - mode: "set" | "add" | "remove"
```

- `set`: Replace all flags
- `add`: Append to existing flags
- `remove`: Delete specified flags

### mempalace_watch — Monitor Changes

Watch a query and get notified when matching drawers change:

```
Tool: mempalace_watch
Parameters:
  - query: "search term"
  - wing: "optional wing filter"
  - room: "optional room filter"
  - watch_id: "optional from previous call"
  - limit: 10
```

**First call:** Returns a new `watch_id`. Save it.

**Subsequent calls:** Pass the `watch_id` to detect changes:
- `changes.added`: Number of new matching drawers
- `changes.removed`: Number of removed drawers
- `changes.added_ids` / `changes.removed_ids`: The drawer IDs

### mempalace_kg_explore — Directional KG Traversal

Explore the knowledge graph directionally from an entity:

```
Tool: mempalace_kg_explore
Parameters:
  - entity: "Nehuen"
  - direction: "out" | "in" | "both" (default: both)
  - depth: 2
  - limit: 20
```

- `out`: Find what this entity points to (subject→)
- `in`: Find what points to this entity (←object)
- `both`: All connections

Returns results grouped by depth level.

### Pagination

All list/search tools support offset/limit pagination:

```
Tool: mempalace_list_wings (or list_rooms, get_taxonomy, search)
Parameters:
  - offset: 0  (default: 0)
  - limit: 50 (default: varies by tool)
```

Response includes:
- `total`: Total available items
- `offset`: Current offset
- `limit`: Current limit

### KG Auto-Storage in mempalace_remember

When using `mempalace_remember`, facts, preferences, and decisions are automatically extracted and added to the knowledge graph.

Response includes:
- `kg_triples`: Array of {subject, predicate, object}
- `kg_count`: Number of triples added

## CLI Commands

```bash
hermes mempalace setup        # Interactive setup wizard
hermes mempalace status       # Show palace overview
hermes mempalace memories     # List all stored memories
hermes mempalace wings        # List all wings and their rooms
hermes mempalace init <dir>   # Initialize new palace
hermes mempalace mine <dir>   # Mine data into palace
hermes mempalace enable       # Enable plugin
hermes mempalace disable      # Disable plugin
```

## Memory Architecture

```
~/.mempalace/
├── palace/                      # ChromaDB vector store
│   ├── chroma.sqlite3
│   └── ...
├── knowledge.db                 # SQLite knowledge graph
├── config.json                 # Config (palace_path, collection)
├── identity.txt                # L0 identity (~50 tokens)
└── wing_config.json            # Wing definitions
```

## The Palace System

MemPalace organizes memory into a hierarchical structure:

- **Wings**: Major categories (people, projects, topics)
- **Rooms**: Specific topics within a wing (auth, billing, deploy)
- **Closets**: Compressed summaries pointing to original content
- **Drawers**: Original verbatim content


## Testing

```bash
# Run tests
pytest tests/ -v

# Or with uv
uv run --with pytest pytest tests -v
```

## License

MIT License - see LICENSE file.

## See Also

- [MemPalace](https://github.com/milla-jovovich/mempalace) - The underlying memory system
- [Hermes Agent](https://github.com/nousresearch/hermes-agent) - The agent framework
