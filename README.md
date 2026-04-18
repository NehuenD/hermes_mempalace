# MemPalace Memory Provider Plugin

A local-first AI memory system with palace structure (Wings → Rooms → Closets → Drawers). Working on improving it periodically.

## About

This plugin is an implementation of [MemPalace](https://github.com/milla-jovovich/mempalace) as a memory provider for the Hermes Agent. This is my own version and I'm working on improving it and optimizing as much as I can. 

## Features

- **Local-first**: ChromaDB + SQLite, no cloud dependencies, no API key required
- **Palace Structure**: Hierarchical memory organization with Wings, Rooms, Closets, and Drawers
- **A Complete Set of Tools**: Full read/write access to palace, knowledge graph, navigation, diaries, and mistakes registry
- **Auto-Mining**: Automatic conversation chunking and room detection

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

## Available Tools (26 total)

### Read Tools
| Tool | Description |
|------|-------------|
| `mempalace_status` | Palace overview + AAAK spec |
| `mempalace_list_wings` | List wings with drawer counts |
| `mempalace_list_rooms` | List rooms within a wing |
| `mempalace_get_taxonomy` | Full wing → room → count tree |
| `mempalace_search` | Semantic search with wing/room filters |
| `mempalace_check_duplicate` | Check if content already exists |
| `mempalace_get_aaak_spec` | AAAK dialect reference |

### Write Tools
| Tool | Description |
|------|-------------|
| `mempalace_add_drawer` | File verbatim content |
| `mempalace_delete_drawer` | Remove by ID |
| `mempalace_remember` | Remember with auto-extraction (uses general_extractor) |

### Knowledge Graph Tools
| Tool | Description |
|------|-------------|
| `mempalace_kg_query` | Query entity relationships |
| `mempalace_kg_add` | Add fact triple |
| `mempalace_kg_invalidate` | Mark fact as ended |
| `mempalace_kg_timeline` | Chronological entity story |
| `mempalace_kg_stats` | Graph statistics |

### Navigation Tools
| Tool | Description |
|------|-------------|
| `mempalace_traverse` | Walk palace graph across wings |
| `mempalace_find_tunnels` | Find rooms bridging wings |
| `mempalace_graph_stats` | Graph connectivity stats |

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
