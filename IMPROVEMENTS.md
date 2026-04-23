# MemPalace Learn — Implementation Roadmap
**Status:** In progress (last updated 2026-04-22)
**Design doc:** `~/Work/LEARN.md` (source of truth for concept)
**File to edit:** `~/.hermes/plugins/mempalace/__init__.py`

---

## Context

This roadmap is for implementing the **learning framework** defined in `LEARN.md`:
- A closed-loop memory system: Retrieve → Extract → Consolidate
- Four core tools: `mempalace_learn`, `mempalace_recall`, `mempalace_recall_all`, `mempalace_update`
- Wing: `wing_myos` | Room: `learnings` | Closets: `personal`, `projects`, `world`
- Inspired by ReasoningBank (arXiv:2509.25140)

This is separate from plugin infrastructure (backup/restore, expiring, session_diff) which already exists.

---

## ✅ Already Implemented (relevant)

| Tool | Status | Notes |
|------|--------|-------|
| `mempalace_remember` | ✅ Exists | Can store memories; detects duplicates |
| `mempalace_search` | ✅ Exists | Semantic search on drawers |
| `mempalace_kg_add` / `kg_query` / `kg_timeline` | ✅ Exist | KG triple storage and query |
| `mempalace_set_drawer_flags` | ✅ Exists | Can tag drawers |
| `mempalace_remember_fact` | ✅ Exists | NL → KG triple |
| `mempalace_preview_aaak` | ✅ Exists | AAAK compression preview |
| `mempalace_get_versions` | ✅ Exists | Version chain (but parent_id not set on update) |
| ChromaDB similarity | ✅ Works | `search_memories()` with embeddings |

---

## 🔴 HIGH PRIORITY

### #1 `mempalace_recall` — Core recall tool (DOES NOT EXIST)

**Why:** Defined in LEARN.md as a core tool. Access learnings with semantic similarity + filters.

**Schema:**
```python
RECALL_SCHEMA = {
    "name": "mempalace_recall",
    "description": "Access learnings with semantic similarity and filters. The primary tool for retrieving stored knowledge.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Semantic query — matches against all learnings."},
            "subject": {"type": "string", "description": "Filter by subject entity (e.g. 'Nehuen', 'T3Code')."},
            "closet": {"type": "string", "description": "Filter by closet: 'personal', 'projects', 'world'."},
            "category": {"type": "string", "description": "Filter by category: 'fact', 'preference', 'decision', 'person', 'project'."},
            "flag": {"type": "array", "items": {"type": "string"}, "description": "Filter by flags (e.g. ['CORE', 'EXPERIMENTAL'])."},
            "similarity": {"type": "string", "description": "Override query with explicit similarity string."},
            "limit": {"type": "integer", "description": "Max results (default: 3, max: 10). ReasoningBank: k=1 optimal — cap at 3."},
            "offset": {"type": "integer", "description": "Skip first N results (default: 0)."},
        },
        "required": [],
    },
}
```

**Implementation:**
1. Use existing `search_memories()` for semantic search (oversample ×5, filter post-query)
2. Apply closet/category/flag filters in Python on results
3. If `subject` provided, filter where metadata.subject matches
4. **Set `last_accessed` on returned drawers** (`_collection.update()`)
5. Return: `{results: [{id, content, subject, closet, category, flags, created_at, similarity_score}]}`

**Notes:**
- Default `limit=3` per ReasoningBank (k=1 optimal)
- Closet maps to: `personal` → Nehuen facts, `projects` → project facts, `world` → research facts

---

### #2 `mempalace_recall_all` — Fetch all learnings (DOES NOT EXIST)

**Why:** LEARN.md defines this as the startup loader. Called on first interaction to load fresh context.

**Schema:**
```python
RECALL_ALL_SCHEMA = {
    "name": "mempalace_recall_all",
    "description": "Fetch all learnings at once. Loads fresh context from MemPalace. Called on first real interaction after session start.",
    "parameters": {
        "type": "object",
        "properties": {
            "closet": {"type": "string", "description": "Filter by closet: 'personal', 'projects', 'world' (optional)."},
            "cap": {"type": "integer", "description": "Max learnings to return (default: 20, max: 100)."},
            "sort": {"type": "string", "enum": ["recent", "accessed", "relevance"], "description": "Sort order: 'recent' (default), 'accessed' (last_accessed desc), 'relevance'."},
        },
        "required": [],
    },
}
```

**Implementation:**
1. Fetch from `wing=wing_myos, room=learnings` using `_collection.get()` with metadata filter
2. If closet provided, filter by closet metadata
3. Sort by `created_at` desc (default) or `last_accessed` desc or ChromaDB relevance
4. Cap at `cap` results
5. **Set `last_accessed` on all returned drawers**
6. Return: `{learnings: [{id, content, subject, closet, category, flags, created_at}]}`

**Notes:**
- This is NOT injected into system prompt — actual content stays in MemPalace
- Startup instruction in system prompt tells MyOS to call this on first interaction
- If no learnings exist yet, return empty list (don't error)

---

## 🟡 MEDIUM PRIORITY

### #3 `mempalace_learn` — File new knowledge (PARTIAL — needs smart detection)

**Why:** `mempalace_remember` exists but the LEARN.md design calls for recall-before-filing detection.

**What LEARN.md specifies:**
1. New info arrives → call `recall(similarity=new_info)` to check existing
2. If nothing matches → file it
3. If something matches → compare → call `update` to correct/extend/replace
4. The recall IS the detection mechanism

**What needs to change:**
The `mempalace_remember` tool needs a new parameter to trigger this behavior:

```python
LEARN_SCHEMA = {
    "name": "mempalace_learn",
    "description": "File a new piece of knowledge. Automatically checks for existing similar facts before storing.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The knowledge to file. Verbatim original phrasing."},
            "title": {"type": "string", "description": "Concise identifier summarizing the core fact."},
            "description": {"type": "string", "description": "Brief one-sentence summary."},
            "subject": {"type": "string", "description": "Subject entity (e.g. 'Nehuen', 'Collatz')."},
            "predicate": {"type": "string", "description": "Predicate/relationship (e.g. 'age', 'project', 'conjecture')."},
            "category": {"type": "string", "description": "Category: 'fact', 'preference', 'decision', 'person', 'project'."},
            "closet": {"type": "string", "description": "Closet: 'personal', 'projects', 'world'."},
            "auto_detect": {"type": "boolean", "description": "If true, check for existing similar facts before filing (default: True)."},
            "source_session": {"type": "string", "description": "Session this was learned in."},
        },
        "required": ["content"],
    },
}
```

**Implementation:**
1. If `auto_detect=True`: call `mempalace_recall(similarity=content, limit=3)` first
2. If no similar results → call `_tool_add_drawer` with all fields
3. If similar results exist → return `{match_found: True, candidates: [...], action: 'update|correct|extend|skip'}`
4. Let the agent decide what to do with the match — don't auto-update (too risky)
5. If `auto_detect=False`: file directly without checking

**Storage format per LEARN.md:**
```
title | description | content | subject | predicate | category | closet | source_session | date_learned | flags
```

---

### #4 `mempalace_update` — Modify entry (DOES NOT EXIST as dedicated tool)

**Why:** `mempalace_remember` with mode='replace' exists but LEARN.md wants explicit update modes: replace, correct, extend.

**Schema:**
```python
UPDATE_SCHEMA = {
    "name": "mempalace_update",
    "description": "Modify an existing learning entry. Additive/completing, not destructive.",
    "parameters": {
        "type": "object",
        "properties": {
            "drawer_id": {"type": "string", "description": "ID of the drawer to update."},
            "mode": {"type": "string", "enum": ["replace", "correct", "extend"], "description": "'replace' (swap), 'correct' (fix wrong part), 'extend' (add context without removing)."},
            "content": {"type": "string", "description": "New content (for replace/correct modes)."},
            "extend_with": {"type": "string", "description": "Additional content to append (for extend mode)."},
            "title": {"type": "string", "description": "Updated title."},
            "description": {"type": "string", "description": "Updated description."},
        },
        "required": ["drawer_id", "mode"],
    },
}
```

**Implementation:**
1. Fetch existing drawer by `drawer_id`
2. **Set `parent_id` on new entry** pointing to old drawer_id (versioning)
3. **Add `correction` flag** to metadata when mode=replace/correct
4. **Auto-add KG triple** `(subject, had_{predicate}, old_object)` for timeline
5. Create new drawer with updated content
6. Return: `{new_drawer_id, parent_id, kg_triple_added}`

**Mode behavior:**
- `replace`: full swap, old kept via parent_id
- `correct`: keep old + mark with `corrected_to=new_drawer_id`, new entry has `corrected_from=old_id`
- `extend`: concatenate: `old_content + "\n---\n" + extend_with`, no deletion

---

### #5 `parent_id` tracking + `mempalace_drawer_history`

**Why:** Version chain doesn't exist. Updates lose history.

**Changes in `_tool_add_drawer`:**
```python
# When adding a drawer that is a new version of an existing one:
if parent_id:
    metadata["parent_id"] = parent_id  # already supported in schema
```

**New tool `mempalace_drawer_history`:**
```python
DRAWER_HISTORY_SCHEMA = {
    "name": "mempalace_drawer_history",
    "description": "Get all versions of a drawer by following parent_id chain.",
    "parameters": {
        "type": "object",
        "properties": {
            "drawer_id": {"type": "string", "description": "Current or historical drawer ID."},
            "limit": {"type": "integer", "description": "Max versions (default: 20)."},
        },
        "required": ["drawer_id"],
    },
}
```

**Implementation:**
1. Fetch `drawer_id` from `_collection.get(ids=[drawer_id])`
2. Follow `parent_id` chain backward
3. Return: `[{id, content, metadata, version_num}, ...]` newest-first

---

## 🟢 LOW PRIORITY (ReasoningBank changes)

### #6 Default `limit=3` on recall

**Change in `_tool_search` and any new recall tools:**
```python
"limit": {"type": "integer", "description": "Max results (default: 3, max: 10)."}
```

---

### #7 `type: correction` flag on updates

**Already noted in #4. Auto-applied when mode=replace/correct.**

---

### #8 Auto-add KG triple on fact updates (self-contrast)

**Already noted in #4. Adds `(subject, had_{predicate}, old_value)` triple.**

---

### #9 `last_accessed` metadata on recall

**Change in `_tool_recall` and `_tool_search`:** After returning results, update each drawer:
```python
_collection.update(
    ids=[result_ids],
    metadatas=[{"last_accessed": datetime.now().isoformat()}]
)
```

---

## ❌ Out of Scope

- Plugin infrastructure (backup/restore, expiring, session_diff) — already implemented separately
- Tool name aliases — framework-level, request separately
- `_tool_list_rooms` filter consistency — cosmetic fix

---

## ✅ All Implemented (2026-04-22)

| # | Tool | Status |
|---|------|--------|
| #1 | `mempalace_recall` | ✅ Core semantic recall, limit=3, last_accessed |
| #2 | `mempalace_recall_all` | ✅ Fetch all, sort (recent/accessed/relevance), last_accessed |
| #3 | `mempalace_learn` | ✅ Auto-detect similar facts (calls recall internally) |
| #4 | `mempalace_update` | ✅ replace/correct/extend modes, parent_id, correction flag, KG triple |
| #5 | `parent_id` + drawer_history | ✅ `mempalace_drawer_history` follows version chain |
| #6 | Default limit=3 | ✅ In schema |
| #7 | Correction flag | ✅ Auto on update |
| #8 | KG triple on updates | ✅ `(subject, had_{predicate}, old_value)` |
| #9 | last_accessed | ✅ Set on recall |

All schemas registered in `ALL_TOOL_SCHEMAS`, handlers in `handle_tool_call`.

**LSP errors:** Pre-existing type hints issues with ChromaDB — not from new code.

---

## File Reference

**Edit:** `~/.hermes/plugins/mempalace/__init__.py`

**Key existing functions to use/extend:**
- `search_memories()` — semantic search
- `_collection.get()` / `_collection.update()` — drawer read/write
- `_tool_kg_add()` — KG triple creation
- `mempalace_get_versions()` — version chain (verify it works)

**Closet mapping:**
| Closet | Content |
|--------|---------|
| `personal` | Facts about Nehuen (age, preferences, health) |
| `projects` | Facts about T3Code, Collatz research |
| `world` | Research facts, papers, world knowledge |

**Metadata fields on learnings:**
| Field | Source |
|-------|--------|
| `title` | Set by learn tool |
| `subject` | Set by learn tool |
| `predicate` | Set by learn tool |
| `category` | fact / preference / decision / person / project |
| `closet` | personal / projects / world |
| `source_session` | Current session ID |
| `created_at` | Auto on add |
| `parent_id` | Set on update |
| `last_accessed` | Set on recall |
| `flags` | Set by update or flag tool |
