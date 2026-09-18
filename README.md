# MemPalace — Hermes Memory Provider Plugin

Local-first persistent memory for Hermes. MemPalace layers a ChromaDB vector store (semantic search) with a SQLite knowledge graph (structured facts) and organizes memories by a palace taxonomy: **Wing → Room → Closet → Drawer**. An optional shorthand dialect (**AAAK**) keeps dense entries compact.

All storage is local. No accounts, no network calls for core operation.

## The palace metaphor

| Level | Meaning | Example |
|-------|---------|---------|
| **Wing** | High-level domain | `wing_general` (default, configurable) |
| **Room** | Topic or activity | `learnings`, `sessions`, `preferences` |
| **Closet** | Content classification | `personal`, `projects`, `world` |
| **Drawer** | One memory entry | a fact, preference, or note (UUID, content, metadata, TTL) |

## Install & Enable

1. Dependencies: `chromadb` and `pyyaml` (declared in `plugin.yaml`).
2. Place the plugin at `~/.hermes/plugins/mempalace/` (or under a named profile's plugins dir), or install from a git URL with `hermes plugins install <git-url>`.
3. Select it as the active memory provider:

   ```bash
   hermes config set memory.provider mempalace
   ```

When active, its 45 tools appear alongside Hermes's built-ins and the CLI below is wired automatically. **Installed ≠ enabled**: nothing runs until `memory.provider` names it. Only one external memory provider can be active at a time.

## Quick tour

### Remember

```python
mempalace_remember(content="Alex prefers dark mode in all terminals", category="preference")
```

Auto-detects subject, room, and closet, files the drawer, and embeds it for semantic search.

### Recall

```python
mempalace_recall(query="terminal color preference", closet="personal", limit=3)
```

Semantic search across drawers, ranked by similarity, with subject/closet/category/flags filters and pagination. Each recall updates `last_accessed`, which feeds the `accessed` sort mode.

### Learn (recall-before-filing)

```python
mempalace_learn(
    content="Alex prefers Postgres for database work because it is more reliable",
    title="Alex's database preference",
    subject="Alex",
    predicate="prefers",
    category="preference",
    closet="personal",
    auto_detect=True,   # runs a duplicate check first
)
```

If a near-duplicate exists, returns it instead of filing redundant content. Updates create a new version linked by `parent_id` — retrieve the chain with `mempalace_get_versions`.

### Cross-session project tracking

```python
# End of session
mempalace_session_write(
    project="acme-api:v2",
    summary="Migrated the ingredients endpoint to GraphQL; fixed the N+1 query on /recipes/:id; added cursor pagination.",
    next="Update /search. Write migration docs. Deploy to staging.",
)

# Next session — restore context
mempalace_session_read(project="acme-api", last_n=5)
```

The startup context block auto-injects the most recent sessions and learnings.

### Knowledge graph

```python
mempalace_kg_add(subject="Alex", predicate="lives_in", object="Montevideo", valid_from="2026-04-01")
mempalace_kg_query(entity="Alex")
mempalace_kg_explore(entity="Alex", depth=2, direction="out")
```

Facts are triples with temporal validity; query, timeline, invalidate, and traverse them.

## AAAK dialect

AAAK (Autonomous Autonomous Autonomous Knowledge) is a compact shorthand for dense memories — ideal for session summaries, compressed facts, and recurring patterns. Use full text for verbatim quotes and nuanced decisions.

```
Format: ENTITY → codes|topic|"key_quote"|flags

Example: AUTH_DB → Postgres|db,migration|reason:reliable|decision
Example: USER → pref:dark.mode|workflow|preference
Example: APP → project,api|architecture,goals|project
```

Flags: `DECISION, CORE, SENSITIVE, TECHNICAL, PIVOT`. Preview before saving with `mempalace_preview_aaak`.

## Mistakes

Record, recall, and distill mistakes into learnings:

```python
mempalace_record_mistake(
    content="ChromaDB compound filter with two top-level operators crashes — must use $and",
    domain="hermes",
    error_type="runtime",
    severity="HIGH",
)

# Recall mistakes via semantic search (category="mistake")
mempalace_recall(query="ChromaDB filter bugs", category="mistake")

# Distill into an actionable lesson (parent_id links back to the mistake)
mempalace_distill_mistake(drawer_id="...", closet="projects")
```

## Configuration

Priority: **environment variables > config file > defaults**.

- Palace directory (default: `$HERMES_HOME/.mempalace/`; ChromaDB data under `<palace>/palace`, KG at `<palace>/knowledge_graph.db`)
- Config file: `$HERMES_HOME/.mempalace/config.json` — `palace_path`, `collection_name`, `default_wing`, `user_entity` (KG subject used when seeding identity facts; default `USER`)
- Environment overrides:

| Variable | Meaning |
|----------|---------|
| `MEMPALACE_PATH` | Palace directory (highest priority) |
| `MEMPALACE_COLLECTION` | ChromaDB collection name |
| `MEMPALACE_DEFAULT_WING` | Default wing |
| `MEMPALACE_REFERER` | Optional OpenRouter referer for the LLM judge |

## CLI

When MemPalace is the active provider, Hermes wires the CLI automatically:

```bash
hermes mempalace setup         # interactive setup
hermes mempalace status        # palace overview
hermes mempalace init <dir>    # initialize a palace
hermes mempalace mine <dir>    # mine data into the palace
hermes mempalace memories      # list stored memories
hermes mempalace wings         # list wings and rooms
hermes mempalace summarize     # palace summary
hermes mempalace enable|disable
hermes mempalace profile list|create|switch|delete
```

## Tool index (45)

| Group | Tools |
|-------|-------|
| **Read & search** | `mempalace_status`, `mempalace_list_wings`, `mempalace_list_rooms`, `mempalace_get_taxonomy`, `mempalace_search`, `mempalace_recall`, `mempalace_recall_all`, `mempalace_check_duplicate`, `mempalace_get_aaak_spec`, `mempalace_drawer_history`, `mempalace_get_versions`, `mempalace_review` |
| **Write** | `mempalace_add_drawer`, `mempalace_remember`, `mempalace_remember_fact`, `mempalace_learn`, `mempalace_update`, `mempalace_delete_drawer`, `mempalace_set_drawer_flags`, `mempalace_preview_aaak` |
| **Knowledge graph** | `mempalace_kg_query`, `mempalace_kg_add`, `mempalace_kg_invalidate`, `mempalace_kg_timeline`, `mempalace_kg_stats`, `mempalace_kg_explore` |
| **Session & diary** | `mempalace_session_write`, `mempalace_session_read`, `mempalace_session_diff`, `mempalace_diary_write`, `mempalace_diary_read` |
| **Navigation** | `mempalace_traverse`, `mempalace_find_tunnels`, `mempalace_graph_stats` |
| **Mistakes** | `mempalace_record_mistake`, `mempalace_distill_mistake` |
| **Maintenance** | `mempalace_summarize`, `mempalace_watch`, `mempalace_expiring`, `mempalace_noise_filter`, `mempalace_backup`, `mempalace_restore`, `mempalace_sweep`, `mempalace_profile_list`, `mempalace_profile_switch` |

## Development

- Tests: `tests/test_mempalace_provider.py` — pure-logic and tool-dispatch tests that run without a live ChromaDB.
- Layout is flat: `__init__.py` (provider + lifecycle) with tool mixins (`tools_*.py`), `schemas.py` (all tool schemas), `layers.py` (wake-up context layers), `dialect.py` (AAAK), `strategy_system.py` / `llm_judge.py` / `consolidation.py` / `extraction.py` (ReasoningBank), `searcher.py` / `retrieval.py` (search), `knowledge_graph.py` / `entity_detector.py` / `entity_registry.py` / `palace_graph.py` (structured layer), `client.py` / `cli.py` / `mcp_server.py` (standalone surface).

## License

MIT