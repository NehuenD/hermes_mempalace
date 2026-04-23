# MemPalace Coding Agent — TODO
**Generated from:** Full audit of `~/.hermes/plugins/mempalace/__init__.py` (4,023 lines) + mempalace package  
**Audited:** 2026-04-23  
**Palace state:** 510 drawers, 6 wings, ChromaDB 1.5.6, mempalace package v0.1  
**Primary files to modify:**  
- `~/.hermes/plugins/mempalace/__init__.py` (4,023 lines — the Hermes plugin)  
- `~/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/` (pip package)

---

## P0 — FIXES (broken right now)

### TODO 1: Fix `mempalace_recall_all` — ChromaDB compound filter bug

**Location:** `__init__.py`, `_tool_recall_all()` around line 3550

**Problem:** Uses flat compound filter in ChromaDB `get()`:
```python
where_filter = {"wing": "wing_myos", "room": "learnings"}
results = self._collection.get(where=where_filter, ...)
```
ChromaDB 1.5.6 requires `$and` for compound filters. This either raises `ValueError` or silently returns empty results.

**Fix:** Replace flat dict with `$and` syntax:
```python
where_filter = {"$and": [{"wing": "wing_myos"}, {"room": "learnings"}]}
results = self._collection.get(where=where_filter, ...)
```

**Test:** After fix, call `mempalace_recall_all` and verify it returns actual drawer results, not empty/error.

---

### TODO 2: Fix `mempalace_session_diff` — same ChromaDB compound filter bug

**Location:** `__init__.py`, `_tool_session_diff()` around line 3394

**Problem:** Same flat compound filter:
```python
where_filter = {"wing": "wing_myos", "room": "sessions"}
if project:
    where_filter["session_project"] = project  # 3-field flat filter
results = self._collection.get(where=where_filter, ...)
```

**Fix:** Build filter conditionally with `$and`:
```python
conditions = [{"wing": "wing_myos"}, {"room": "sessions"}]
if project:
    conditions.append({"session_project": project})
where_filter = {"$and": conditions} if len(conditions) > 1 else conditions[0]
results = self._collection.get(where=where_filter, ...)
```

**Test:** Call `mempalace_session_diff` with and without a `project` filter. Verify it returns actual sessions.

---

### TODO 3: Fix `_tool_recall` — closet/category post-hoc filtering is unreliable

**Location:** `__init__.py`, `_tool_recall()` around line 3451

**Problem:** Filters are applied AFTER fetching raw semantic results:
```python
n_to_fetch = (offset + limit) * 5
results = search_memories(query, ..., n_results=n_to_fetch)
# post-hoc Python filter — unreliable:
if closet and r_closet != closet:
    continue
```

Requesting `closet=personal, limit=3` can return 0 results because the top 15 semantic hits weren't in `personal`.

**Fix approach (pick one):**

**Option A (recommended):** Do the closet/category filtering server-side in ChromaDB using metadata filters in a pre-filter step, then run semantic search only on matching items.

**Option B:** Increase `n_to_fetch` multiplier significantly (e.g., 20x instead of 5x) to increase chance of finding matching closet/category. Simpler but less correct.

**Option C:** Use ChromaDB's `where_document` filter after semantic search to post-filter more reliably.

The core issue is that semantic similarity and metadata category are orthogonal. A better architecture would be: filter by metadata first, then rank by semantic similarity within that set.

**Test:** Call `mempalace_recall(closet=personal, limit=3)` — should return 3 results from the `personal` closet, not 0.

---

### TODO 4: Fix `mempalace_learn` auto_detect path — creates new ChromaDB client per call

**Location:** `__init__.py`, `_tool_learn()` around line 3592

**Problem:** `auto_detect=True` calls `self._tool_recall()` to check for duplicates. But `_tool_recall` -> `search_memories()` which creates a NEW ChromaDB client:
```python
# In searcher.py (mempalace package):
client = chromadb.PersistentClient(path=palace_path)
col = client.get_collection("mempalace_drawers")
```
This adds ~192ms per call overhead and can fail if the palace is locked.

**Fix:** There are two paths:

**Option A (quick fix):** In `_tool_learn`, replace the `self._tool_recall()` dedup call with a direct, fast ChromaDB metadata-only check (no semantic search needed for exact/semantic dedup of a new filing). Use `col.count(where={"wing": wing, "room": room})` to check if the room has content, and for similarity use a pre-computed hash or embedding cache.

**Option B (proper fix):** Refactor `search_memories()` in the pip package to accept an optional pre-existing ChromaDB client instead of creating one every time. Then in `_tool_recall`, pass `self._chroma_client` instead of creating a new one.

**Test:** Call `mempalace_learn(content="test fact", title="test", auto_detect=True)` — should complete in <100ms and not create duplicate entries.

---

## P1 — PERFORMANCE IMPROVEMENTS

### TODO 5: Persist taxonomy cache to disk

**Location:** `__init__.py`, `_build_taxonomy_cache()` and `_ensure_palace()`

**Problem:** `_build_taxonomy_cache()` runs on every `initialize()` and does a full `col.get()` scan. The cache is in-memory only — `taxonomy_cache.json` is referenced but never written.

**Fix:** 
1. After building the cache, write it to `~/.mempalace/taxonomy_cache.json`
2. On startup, try to load from file first
3. Invalidate (delete and rebuild) only when drawers are added/deleted
4. The `taxonomy_cache` is a dict mapping `wing -> {room -> count}`

**Implementation:**
```python
cache_path = os.path.join(self._palace_path, "taxonomy_cache.json")
if os.path.exists(cache_path):
    with open(cache_path) as f:
        self._taxonomy_cache = json.load(f)
else:
    self._build_taxonomy_cache()
    with open(cache_path, 'w') as f:
        json.dump(self._taxonomy_cache, f)
```
Then call `_taxonomy_cache = None` and rebuild+persist when `add_drawer` or `delete_drawer` is called.

**Test:** Restart the plugin, verify `list_wings` works from cache (no full scan logged).

---

### TODO 6: Cache `build_graph()` output

**Location:** `__init__.py`, `build_graph()`, `palace_graph.py`

**Problem:** Every call to `traverse()`, `find_tunnels()`, or `graph_stats()` rebuilds the full graph from scratch — O(n) palace scan + 95ms. At 510 items fine, at 50,000 items this becomes slow.

**Fix:** Cache the graph adjacency data to `~/.mempalace/graph_cache.json`:
```python
graph_cache_path = os.path.join(self._palace_path, "graph_cache.json")
if os.path.exists(graph_cache_path):
    with open(graph_cache_path) as f:
        return json.load(f)
# else build and cache
```
Invalidate cache on drawer add/delete. For `graph_stats`, compute from cached graph rather than rebuilding.

**Test:** Call `mempalace_traverse(start_room="sessions")` twice in a row — second call should be <5ms (from cache), not 95ms.

---

### TODO 7: Fix redundant ChromaDB client creation in `searcher.py`

**Location:** `~/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/searcher.py`

**Problem:** `search_memories()` creates a new `chromadb.PersistentClient` on every call:
```python
client = chromadb.PersistentClient(path=palace_path)
col = client.get_collection("mempalace_drawers")
```
Every `_tool_recall` call goes through this, adding ~60ms of connection overhead.

**Fix:** Accept an optional `client` parameter:
```python
def search_memories(query, n_results=5, client=None, ...):
    if client is None:
        client = chromadb.PersistentClient(path=palace_path)
    col = client.get_collection("mempalace_drawers")
    ...
```
Then in the plugin's `_tool_recall`, pass `self._chroma_client`:
```python
results = search_memories(query, n_results=n_to_fetch, client=self._chroma_client, ...)
```

**Note:** This modifies the pip package, not the plugin. The plugin should work after this change.

**Test:** Call `mempalace_recall(query="Nehuen", limit=5)` twice rapidly — second call should be faster (reuses client connection).

---

## P2 — ARCHITECTURAL IMPROVEMENTS

### TODO 8: Auto-version drawers on `mempalace_update` with mode=replace

**Location:** `__init__.py`, `_tool_update()`

**Problem:** `mempalace_update` with `mode=replace` overwrites content without creating a version chain. `get_versions` and `drawer_history` tools exist but no tool automatically uses them.

**Fix:** In `_tool_update`, when `mode=replace`:
1. Fetch the current drawer content
2. Set the new drawer's `parent_id` to the current drawer's ID
3. This creates an automatic version chain without user intervention

**Implementation note:** The `parent_id` field already exists in drawer metadata. The fix is to set it automatically on replace.

**Test:** Call `mempalace_update(drawer_id=X, mode=replace, content="new content")`, then `mempalace_get_versions(drawer_id=X)` — should show 2 versions.

---

### TODO 9: Bridge identity.txt and KG on startup

**Location:** `__init__.py`, `_ensure_palace()` or `_seed_kg_if_empty()`

**Problem:** `identity.txt` and the KG both store facts about Nehuen/MyOS. They are never synced.

**Fix:** On startup (in `_seed_kg_if_empty` or a new `_sync_identity_to_kg()`), parse `identity.txt` and create KG triples for each fact. Use regex or simple line parsing to extract facts from the L0 format.

**Approach:**
1. Read `~/.mempalace/identity.txt`
2. For each line with a fact pattern (e.g., "Nehuen lives in Argentina", "Omarchy is Arch/Hyprland"), create a KG triple
3. Use `mempalace_remember_fact` or direct `kg_add` calls

**Test:** After running, `mempalace_kg_query(entity="Nehuen")` should return all facts from identity.txt.

---

### TODO 10: TTL sweep on a schedule, not just at startup

**Location:** `__init__.py`, `_sweep_expired_drawers()`

**Problem:** `_sweep_expired_drawers()` only runs at plugin startup. If the system runs for weeks without restart, expired drawers accumulate.

**Fix:** Add a cron-based trigger. Options:
1. Export the sweep logic as a standalone function callable by a cron job
2. Add a `mempalace_sweep` tool that can be called by a cron
3. Use Hermes cron integration: `cronjob` tool to schedule nightly sweep

**Implementation:**
```python
def _tool_sweep_expired(self, args):
    """Manually trigger expired drawer sweep."""
    self._sweep_expired_drawers()
    return json.dumps({"status": "sweep completed"})
```

Then schedule it: `cronjob` with action='create', schedule='0 3 * * *' (3am daily).

**Test:** Create a drawer with `expires_at` of today, run `_tool_sweep_expired`, verify drawer is gone.

---

### TODO 11: Profile switch validation

**Location:** `__init__.py`, `_tool_profile_switch()`

**Problem:** `_tool_profile_switch` calls `get_or_create_collection()` on the new path with no validation that the palace is accessible.

**Fix:** Before switching:
1. Verify the target path exists and is readable
2. Try to get the collection to confirm it's a valid ChromaDB store
3. If invalid, return error instead of silently creating a broken profile

```python
target_path = os.path.join(os.path.dirname(self._palace_path), name)
try:
    test_client = chromadb.PersistentClient(path=target_path)
    test_client.get_collection("mempalace_drawers")
except Exception as e:
    return json.dumps({"error": f"Invalid profile: {e}"})
```

---

## P3 — CLEANUP

### TODO 12: Remove or integrate `mcp_server.py tool_diary_*` functions

**Problem:** `mcp_server.py` has `tool_diary_write` and `tool_diary_read` imported in `__init__.py` but never actually called. Two separate diary systems exist.

**Fix:** Either:
- **Option A:** Remove the MCP server diary imports/calls from the plugin if they're not used
- **Option B:** Wire up the MCP server diary functions so they actually get called

Check if `tool_diary_write` / `tool_diary_read` from `mcp_server.py` are meant to supersede the plugin's `_tool_diary_write`. If not used, remove the dead imports.

---

### TODO 13: Audit and fix `_tool_check_duplicate`

**Location:** `__init__.py`, `_tool_check_duplicate()` (around line 3010)

**Problem:** Uses `search_memories()` which creates a new ChromaDB client per call (slow). Also may not handle the compound filter issue.

**Fix:** Same as TODO 7 — pass `self._chroma_client` to `search_memories`. Also verify it doesn't have the compound filter bug.

---

### TODO 14: Investigate `mempalace_watch` — never tested

**Problem:** `watch` tool uses periodic polling and a `watch_id` for change detection. Never tested. May have bugs.

**Fix:** Test it. If broken, either fix or document that it's experimental. The watch mechanism likely needs a persistent state file to track `watch_id` -> last-seen results.

---

### TODO 15: Document the hall/closet concept

**Problem:** The `closet` field and hall/closet detection from `general_extractor` exists but is not documented or used in the plugin.

**Fix:** Either:
- Document how to use `closet` fields in `add_drawer` and how halls connect wings
- Or remove the `closet` parameter from tools if it's not meant to be used

Check `general_extractor.py` for the hall keyword detection logic. Determine if it's meant to be a user-facing feature or internal.

---

### TODO 16: Sync SOUL.md and identity.txt automatically

**Location:** `__init__.py`, `_ensure_palace()` or a new `_sync_soul_and_identity()`

**Problem:** `SOUL.md` at `~/.hermes/SOUL.md` and `~/.mempalace/identity.txt` both describe MyOS's identity and are manually kept in sync.

**Fix:** On startup, compare timestamps or content hashes of both files. If they differ, emit a warning or auto-sync selected fields (like the "Last updated" timestamp, key facts).

Better approach: have one be the source of truth. Recommend `identity.txt` as L0 and have `_ensure_palace` import it into the KG on startup.

---

## FILE LOCATIONS REFERENCE

### Plugin (main file to modify)
- `/home/nehuen/.hermes/plugins/mempalace/__init__.py` — 4,023 lines, all 44 tool implementations

### mempalace pip package (modify for TODO 7)
- `/home/nehuen/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/searcher.py` — `search_memories()` function
- `/home/nehuen/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/knowledge_graph.py` — KG operations
- `/home/nehuen/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/general_extractor.py` — hall/closet detection
- `/home/nehuen/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/palace_graph.py` — graph operations
- `/home/nehuen/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/layers.py` — L0/L1 layer generation
- `/home/nehuen/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/config.py` — palace path config

### Palace data
- `/home/nehuen/.mempalace/` — main palace directory
- `/home/nehuen/.mempalace/palace/` — ChromaDB storage
- `/home/nehuen/.mempalace/knowledge_graph.db` — SQLite KG
- `/home/nehuen/.mempalace/identity.txt` — L0 identity file
- `~/.mempalace/taxonomy_cache.json` — (should be created by TODO 5)
- `~/.mempalace/graph_cache.json` — (should be created by TODO 6)

### Other references
- `/home/nehuen/Work/palace.md` — full audit document
- `/home/nehuen/hermes_mempalace/` — development directory
- `/home/nehuen/.hermes/SOUL.md` — MyOS soul file

---

## TESTING CHECKLIST

After completing each TODO, verify:

- [ ] TODO 1: `mempalace_recall_all` returns results, not empty/error
- [ ] TODO 2: `mempalace_session_diff` works with and without project filter
- [ ] TODO 3: `mempalace_recall(closet=personal, limit=3)` returns 3 results from personal closet
- [ ] TODO 4: `mempalace_learn(auto_detect=True)` completes in <100ms, no duplicates
- [ ] TODO 5: `list_wings` uses persisted cache (no full scan on restart)
- [ ] TODO 6: Second `traverse()` call uses graph cache (<5ms vs 95ms)
- [ ] TODO 7: Sequential `recall` calls reuse ChromaDB client (faster second call)
- [ ] TODO 8: `update(mode=replace)` creates version chain automatically
- [ ] TODO 9: KG contains facts from identity.txt after startup
- [ ] TODO 10: TTL sweep can be triggered manually and via cron
- [ ] TODO 11: `profile_switch` to invalid path returns error, not silent failure
- [ ] TODO 12: Dead MCP diary imports removed or wired up
- [ ] TODO 13: `check_duplicate` is fast and correct
- [ ] TODO 14: `watch` works or is documented as experimental
- [ ] TODO 15: closet/hall concept documented or removed
- [ ] TODO 16: SOUL.md and identity.txt sync warning or auto-sync works
