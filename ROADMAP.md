# MemPalace + ReasoningBank — Roadmap

> Target: Transform MemPalace from a 4590-line monolithic MemoryProvider into a
> modular package and implement the ReasoningBank closed-loop agent learning
> protocol on top of it.

---

## Current Architecture

```
plugins/mempalace/
├── __init__.py          ← 4590-line MempalaceMemoryProvider (the monolith)
│                        • MemoryProvider lifecycle hooks
│                        • 44 tool methods (read/write/knowledge/diary/nav/meta)
│                        • 10+ private helper methods
│                        • All tool schemas (inline dicts)
├── mempalace/           ← Support modules (already split, 5375 lines)
│   ├── dialect.py       — AAAK compression dialect
│   ├── config.py        — Configuration loading
│   ├── searcher.py      — ChromaDB query logic
│   ├── layers.py        — L0/L1 identity layers
│   ├── knowledge_graph.py — KG operations
│   ├── kg_seed.py       — Initial KG seeding
│   ├── palace_graph.py  — Palace navigation graph
│   ├── entity_detector.py — Entity extraction
│   ├── entity_registry.py — Entity registry
│   ├── general_extractor.py — Memory extraction from text
│   └── mcp_server.py    — MCP server interface (also has diary_write/read)
├── client.py            — CLI client
├── cli.py               — CLI interface
├── plugin.yaml          — Hermes plugin registration
├── README.md            — Docs
└── tests/               — Test suite
```

**Pain points:**
- `__init__.py` mixes MemoryProvider lifecycle, tool definitions, tool schemas, business logic, and session hooks
- Adding ReasoningBank features (estimated 2000-3500 more lines) to this file is not viable
- No clear boundaries between read tools, write tools, knowledge tools, session tools, meta tools
- Hard to test isolated features

---

## Target Architecture

After refactoring, the MemoryProvider becomes a **thin coordinator** that imports
from focused submodules:

```
plugins/mempalace/
├── __init__.py           ← Thin MemoryProvider (~200 lines)
│                         • class wiring, tool registration, delegation
│                         • imports from submodules, no business logic
├── mempalace/
│   ├── __init__.py       ← empty (package marker)
│   │
│   ├── [EXISTING — keep as-is]
│   │   ├── dialect.py
│   │   ├── config.py
│   │   ├── searcher.py
│   │   ├── layers.py
│   │   ├── knowledge_graph.py
│   │   ├── kg_seed.py
│   │   ├── palace_graph.py
│   │   ├── entity_detector.py
│   │   ├── entity_registry.py
│   │   ├── general_extractor.py
│   │   └── mcp_server.py
│   │
│   ├── [NEW — split from __init__.py]     ← Phase 1
│   │   ├── schemas.py     — All tool schema dicts (moved out)
│   │   ├── tools_read.py  — status, list_wings, list_rooms, get_taxonomy,
│   │   │                    search, check_duplicate, get_aaak_spec, recall,
│   │   │                    recall_all, drawer_history
│   │   ├── tools_write.py — add_drawer, delete_drawer, remember, learn,
│   │   │                    update, session_write, session_read
│   │   ├── tools_knowledge.py — kg_query, kg_add, kg_invalidate,
│   │   │                    kg_timeline, kg_stats, kg_explore
│   │   ├── tools_nav.py   — traverse, find_tunnels, graph_stats
│   │   ├── tools_diary.py — diary_write, diary_read
│   │   ├── tools_mistake.py — record_mistake, distill_mistake,
│   │   │                    run_distillation_analysis
│   │   ├── tools_meta.py  — profile_list, profile_switch, sweep, backup,
│   │   │                    restore, session_diff, noise_filter, expiring,
│   │   │                    preview_aaak, set_drawer_flags, watch, summarize
│   │   └── helpers.py     — _is_noise, _parse_natural_fact, _compress_aaak,
│   │                        _load_noise_patterns, _save_noise_patterns,
│   │                        _detect_room, _detect_closet, _load_config,
│   │                        _get_palace_path
│   │
│   ├── [NEW — ReasoningBank features]    ← Phases 2-5
│   │   ├── extraction.py     — LLM-based strategy/failure extraction
│   │   ├── trajectory.py     — Task boundary detection, trajectory capture
│   │   ├── retrieval.py      — Strategy retrieval, top-k tuning, wing_mistakes bridge
│   │   ├── consolidation.py  — Dedup, abstraction, self-evolution loop
│   │   ├── strategy_system.py — System prompt injection for strategies
│   │   ├── llm_judge.py      — Task success/failure evaluation
│   │   └── matts.py          — Multi-agent Tree-of-Thought Search
```

---

## Submodule Map — Detailed

### Phase 0: Refactor (no behavioral changes)

| Submodule | What goes in it | From __init__.py lines | Complexity |
|---|---|---|---|
| `schemas.py` | All 40+ `*_SCHEMA = {...}` dicts | 109-1163 | Trivial (copy-paste) |
| `helpers.py` | Config loading, noise detection, room/closet detection, AAAK compression, natural fact parsing | `_load_config`, `_get_palace_path`, `_is_noise`, `_detect_room`, `_detect_closet`, `_parse_natural_fact`, `_compress_aaak`, `_load_noise_patterns`, `_save_noise_patterns` | Trivial |
| `tools_read.py` | All read-only tools | `_tool_status`, `_tool_list_wings`, `_tool_list_rooms`, `_tool_get_taxonomy`, `_tool_search`, `_tool_check_duplicate`, `_tool_get_aaak_spec`, `_tool_recall`, `_tool_recall_all`, `_tool_drawer_history`, `_tool_get_versions` | Trivial |
| `tools_write.py` | All write tools | `_tool_add_drawer`, `_tool_delete_drawer`, `_tool_remember`, `_tool_learn`, `_tool_update`, `_tool_session_write`, `_tool_session_read`, `_tool_remember_fact` | Trivial |
| `tools_knowledge.py` | Knowledge graph tools | `_tool_kg_query`, `_tool_kg_add`, `_tool_kg_invalidate`, `_tool_kg_timeline`, `_tool_kg_stats`, `_tool_kg_explore` | Trivial |
| `tools_nav.py` | Navigation tools | `_tool_traverse`, `_tool_find_tunnels`, `_tool_graph_stats` | Trivial |
| `tools_diary.py` | Diary tools | `_tool_diary_write`, `_tool_diary_read` | Trivial |
| `tools_mistake.py` | Mistake tracking | `_tool_record_mistake`, `_tool_distill_mistake`, `_run_distillation_analysis` | Trivial |
| `tools_meta.py` | Everything else | `_tool_profile_list`, `_tool_profile_switch`, `_tool_sweep`, `_tool_backup`, `_tool_restore`, `_tool_session_diff`, `_tool_noise_filter`, `_tool_expiring`, `_tool_preview_aaak`, `_tool_set_drawer_flags`, `_tool_watch`, `_tool_summarize` | Trivial |
| `__init__.py` (rewritten) | Thin MemoryProvider class + lifecycle hooks + tool registration | `__init__`, `name`, `is_available`, `get_config_schema`, `save_config`, `initialize`, `_load_wake_up_context`, `_get_recent_sessions_block`, `_get_learnings_block`, `_ensure_palace`, `_build_taxonomy_cache`, `_update_taxonomy_cache`, `_sweep_expired_drawers`, `_seed_kg_if_empty`, `system_prompt_block`, `prefetch`, `queue_prefetch`, `sync_turn`, `get_tool_schemas`, `handle_tool_call`, `on_turn_start`, `on_session_end`, `on_pre_compress`, `on_memory_write`, `on_delegation`, `shutdown` | Medium (wiring) |

The new `__init__.py` follows this pattern for each tool:
```python
from mempalace.tools_read import tool_status as _tool_status
# ...
def handle_tool_call(self, tool_name, args, **kwargs):
    handler = {
        "mempalace_status": _tool_status,
        "mempalace_list_wings": _tool_list_wings,
        # ...
    }.get(tool_name)
    if handler:
        return handler(self, args)
    # fallback...
```

---

### Phase 1: Doable ReasoningBank features

| Feature | Submodule | What it does | Reference |
|---|---|---|---|
| **1. LLM-based extraction from trajectories** | `extraction.py` | After a session ends, use LLM to extract transferable strategies (success prompt) and preventative lessons (failure prompt) from the session trajectory. Stores as `wing_reasoningbank` drawers with metadata `{type: "strategy"|"lesson", domain, confidence}`. | ReasoningBank §3.2 (Extract) |
| **2. Bridge `wing_mistakes` into retrieval** | `retrieval.py` | When doing strategy search, also query `wing_mistakes` contents so failure-based strategies are surfaced alongside success-based ones. | ReasoningBank §3.2 — failure extraction pathway |
| **3. Strategy injection in system prompt** | `strategy_system.py` | `system_prompt_block()` retrieves top-k strategies relevant to current context and injects with explicit ReasoningBank-style reasoning instruction: "Consider these past strategies. Which apply here? Why?" | ReasoningBank §3.1 (Retrieve) |
| **4. Top-k default = 1** | `retrieval.py` | Per paper ablation, optimal recall is top-1. Change default from 3 to 1. Still allow override via parameter. | ReasoningBank §4.2 (Ablation) |
| **5. Abstraction constraints** | `extraction.py` | Enforce that extracted strategies are abstract and generalizable — no specific websites, queries, or unrepeatable context. Discard or request re-extraction. | ReasoningBank §3.2 (Memory Content Design) |

#### Implementation Order (Phase 1):
1. **Item #4 first** — trivial one-line change, instant warm fuzzy
2. **Item #1** (`extraction.py`) — the core benefit, unlocks everything else
3. **Item #3** (`strategy_system.py`) — makes extracted strategies actually useful
4. **Item #2** (`retrieval.py`) — bridge wing_mistakes into the loop
5. **Item #5** (`extraction.py`) — quality gate on what gets stored

---

### Phase 2: Moderate ReasoningBank features

| Feature | Submodule | What it does | Reference |
|---|---|---|---|
| **6. LLM-as-Judge for task success/failure** | `llm_judge.py` | After each trajectory, run an LLM judge to determine: (a) Did the agent succeed? (b) What was the task goal? (c) What was the critical bottleneck? This enables the success vs. failure extraction routing. Requires defining task boundaries. | ReasoningBank §3.2 (Judge) |
| **7. Closed-loop self-evolution** | `consolidation.py` | Periodically: deduplicate similar strategies, merge related ones, prune outdated ones, increase confidence scores for strategies that keep getting retrieved. The system improves itself. | ReasoningBank §3.3 (Consolidate) |
| **8. Self-contrast** | `strategy_system.py` | When injecting strategies, explicitly compare the current approach to past approaches. "You're doing X, but strategy #3 says Y worked better in similar situations. What's different here?" | ReasoningBank §3.1 — implicit in retrieval |

---

### Phase 3: Complex ReasoningBank features

| Feature | Submodule | What it does | Reference |
|---|---|---|---|
| **9. MaTTS (Multi-agent Tree-of-Thought Search)** | `matts.py` | When uncertainty is high, spawn multiple candidate strategies, evaluate each in parallel, select the best. Parallel mode: evaluate all at once. Sequential mode: adaptive, explores promising branches deeper. Requires subagent delegation. | ReasoningBank §3.3 (MaTTS) |
| **10. Formal task/trajectory boundaries** | `trajectory.py` | Detect when a "task" starts and ends within a session. Currently Hermes has no formal task model. Could be: (a) tool-call-clusters, (b) user intent shifts, (c) explicit `/task` commands. This is a pre-requisite for Items #6 and #9. | ReasoningBank §3.1 (Act) |

MaTTS is deliberately last — it depends on task boundaries (Phase 2), extraction (Phase 1), and retrieval (Phase 1) all working. Without those, the tree-of-thought would be searching through empty space.

---

## Design Principles

1. **Backward compatible at each step.** Every phase leaves existing tools working. The `handle_tool_call` dispatch doesn't change — only where the handlers live.

2. **Existing data is untouched.** `wing_reasoningbank` is a new wing alongside existing ones. Old `wing_mistakes` drawers keep working. The refactor doesn't migrate or transform stored data.

3. **All new features are opt-in.** The ReasoningBank extraction pipeline only runs if configured. If `config.json` has `enable_reasoningbank: false`, the system behaves exactly as today.

4. **Feature independence.** `extraction.py` can be tested without `trajectory.py` (seed it with mock trajectories). `retrieval.py` can be tested without `extraction.py` (seed it with manual strategies). This is the whole point of the submodule architecture.

5. **LLM calls are configurable.** Extraction, judge, and consolidation all call LLM APIs. The provider/model for these calls is configurable (default: same as the main agent model). Each call has a cost limit — if the session has budget constraints, extraction is skipped.

---

## ReasoningBank → MemPalace Concept Mapping

| ReasoningBank Concept | MemPalace Equivalent | Notes |
|---|---|---|
| Memory Bank (vector DB) | ChromaDB collection `mempalace_drawers` | Same storage, separate wing |
| Memory Item `{title, description, content}` | Drawer with metadata `{aaak, type, confidence, domain, parent_id}` | Enriched schema |
| Task Trajectory | Sequence of turns in a session (from `messages`) | New: need session-level trajectory buffer |
| Retrieve (embedding similarity) | `_tool_search` / `_tool_recall` | Already works, just tune top-k |
| Judge (success/failure) | New: `llm_judge.py` | No current equivalent |
| Extract (strategy/lesson) | New: `extraction.py` | No current equivalent |
| Consolidate (dedup/merge) | New: `consolidation.py` | No current equivalent |
| MaTTS | New: `matts.py` | No current equivalent, spawns subagents |

---

## Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Refactor breaks existing tools | Medium | Test each tool after move; existing test suite covers 44 tools |
| LLM extraction costs too high | Medium | Configurable skip threshold; cost budget per session |
| Task boundary detection is unreliable | High | Start with simple heuristic (tool-call gaps + user intent markers), iterate |
| ChromaDB import conflicts between submodules | Low | Single searcher instance, initialized once in `__init__.py`, passed to submodules |
| ReasoningBank features fight mempalace for context injection space | Low | `strategy_system.py` is additive — strategies are injected alongside existing AAAK/learnings blocks |
| MaTTS subagent spawning is expensive | High | Configurable depth/breadth limits; only triggers on high-uncertainty thresholds |

---

## Quick Reference: File Ownership

After Phase 0, each part of MemPalace lives in exactly one file:

| Concern | File |
|---|---|
| MemoryProvider class + lifecycle | `__init__.py` |
| All tool schema dicts | `schemas.py` |
| Read tools (search, recall, list, etc.) | `tools_read.py` |
| Write tools (add, remember, learn, etc.) | `tools_write.py` |
| Knowledge graph tools | `tools_knowledge.py` |
| Navigation tools | `tools_nav.py` |
| Diary tools | `tools_diary.py` |
| Mistake tracking tools | `tools_mistake.py` |
| Meta/utility tools | `tools_meta.py` |
| Shared helper functions | `helpers.py` |
| Strategy extraction | `extraction.py` |
| Task/trajectory tracking | `trajectory.py` |
| Strategy retrieval + top-k tuning | `retrieval.py` |
| Dedup + self-evolution | `consolidation.py` |
| Strategy injection into prompts | `strategy_system.py` |
| LLM judge for task eval | `llm_judge.py` |
| Multi-agent Tree-of-Thought | `matts.py` |
| AAk dialect (existing) | `dialect.py` |
| Entity detection (existing) | `entity_detector.py` |
| ChromaDB searcher (existing) | `searcher.py` |
| Knowledge graph (existing) | `knowledge_graph.py` |

---

## Phase Status Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0 (Refactor) | **COMPLETE** | All 11 submodule extraction tasks done, __init__.py reduced from 4590→~2000 lines |
| Phase 1 (Doable RB) | **COMPLETE** | All 5 features (top-k=1, extraction.py, strategy_system.py, retrieval.py, abstraction constraints) implemented and wired into lifecycle |
| Phase 2 (Moderate RB) | **NEXT** | llm_judge.py, consolidation.py, self-contrast |
| Phase 3 (Complex RB) | **QUEUED** | trajectory.py, matts.py |

*Last updated: 2026-05-05*
