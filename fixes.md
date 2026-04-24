# MemPalace Fixes — Audit 2026-04-24

**Goal:** Fix all P0/P1/P2 bugs, stabilize search, and clean up architectural issues.
**Root cause for most bugs:** ChromaDB 1.x requires `$and` with ≥2 conditions — single-condition `$and` raises `ValueError`.

---

## P0 — SEARCH TOTALLY BROKEN

**All semantic search (`search`, `recall`, `recall_all`) returns 0 results due to ChromaDB 1.x `$and` constraint.**

### Fix 1.1 — `searcher.py` `$and` 1-element crash

**File:** `/home/nehuen/.hermes/plugins/mempalace/mempalace/searcher.py`
**Lines:** ~108–123

**Current code (lines 108-123):**
```python
conditions = []
if wing:
    conditions.append({"wing": wing})
if room:
    conditions.append({"room": room})
if closet and closet not in ["", "all"]:
    conditions.append({"closet": closet})
if category and category not in ["", "all"]:
    conditions.append({"category": category})
if subject:
    conditions.append({"subject": subject})

where = {"$and": conditions} if conditions else {}
```

**Problem:** When only 1 filter is non-empty (e.g., `wing="wing_myos"` only), `conditions = [{"wing": "wing_myos"}]` — a 1-element list passed to `$and`. ChromaDB 1.x raises:
```
ValueError: Expected where value for $and or $or to have at least two where expressions
```

Also, when ALL filters are empty/wrong, `conditions = []` and `where = {"$and": []}` — also crashes.

**Fix — replace the final WHERE construction with:**
```python
# Filter out empty/wholesale values before building conditions
_filter = lambda v: v and v not in ("", "all")

conditions = []
if _filter(wing):
    conditions.append({"wing": wing})
if _filter(room):
    conditions.append({"room": room})
if _filter(closet):
    conditions.append({"closet": closet})
if _filter(category):
    conditions.append({"category": category})
if _filter(subject):
    conditions.append({"subject": subject})

# Build WHERE: 0 conditions = no filter, 1 = direct field, 2+ = $and
if len(conditions) == 0:
    where = {}
elif len(conditions) == 1:
    where = conditions[0]
else:
    where = {"$and": conditions}
```

Also fix `_build_filter` function (lines ~90-108) with the same pattern.

---

### Fix 1.2 — `recall_all` missing `ids` capture

**File:** `/home/nehuen/.hermes/plugins/mempalace/__init__.py`
**Line:** ~3649

**Current code:**
```python
results = self._collection.get(
    where=where_filter, include=["metadatas", "documents"]
)
# ids = ??? — MISSING
```

**Fix — add after collection.get():**
```python
results = self._collection.get(
    where=where_filter, include=["metadatas", "documents"]
)
ids = results.get("ids", [])  # ← ADD THIS LINE
```

The variable `ids[i]` is used at line ~3660 but was never defined.

---

### Fix 1.3 — `check_duplicate` single-condition `$and`

**File:** `/home/nehuen/.hermes/plugins/mempalace/__init__.py`
**Line:** ~1956

**Current code:**
```python
conditions = [{"closet": closet}] if closet else []
if wing:
    conditions.append({"wing": wing})

return json.dumps({
    "is_duplicate": any(
        self._collection.get(
            where={"$and": conditions} if conditions else {},
```

**Problem:** If `closet="personal"` only, `conditions = [{"closet": "personal"}]` — 1-element `$and` crashes.

**Fix — apply 0/1/2+ pattern:**
```python
conditions = []
if closet and closet not in ("", "all"):
    conditions.append({"closet": closet})
if wing and wing not in ("", "all"):
    conditions.append({"wing": wing})

if len(conditions) == 0:
    where_filter = {}
elif len(conditions) == 1:
    where_filter = conditions[0]
else:
    where_filter = {"$and": conditions}

return json.dumps({
    "is_duplicate": any(
        self._collection.get(
            where=where_filter,
```

---

## P0 — `session_diff` ADDED/REMOVED LOGIC WRONG

**File:** `/home/nehuen/.hermes/plugins/mempalace/__init__.py`
**Lines:** ~3480–3520

**Problem:** The date comparison logic for determining "added" vs "removed" is inverted.

**Fix — simplify to project-set comparison:**
```python
forget_results = self._collection.get(
    where={"wing": "wing_myos", "room": "sessions"} if forget_filter else {},
    include=["metadatas"]
)
new_results = self._collection.get(
    where={"wing": "wing_myos", "room": "sessions"} if new_filter else {},
    include=["metadatas"]
)

forget_projects = {m.get("session_project") for m in forget_results.get("metadatas", []) if m.get("session_project")}
new_projects = {m.get("session_project") for m in new_results.get("metadatas", []) if m.get("session_project")}

added_projects = new_projects - forget_projects
removed_projects = forget_projects - new_projects

added = [m for m in new_results.get("metadatas", []) if m.get("session_project") in added_projects]
removed = [m for m in forget_results.get("metadatas", []) if m.get("session_project") in removed_projects]
```

---

## P1 — `learnings` ROOM NEVER BOOTSTRAPPED

**File:** `/home/nehuen/.hermes/plugins/mempalace/__init__.py`
**Function:** `_ensure_palace` (~line 2060)

**Fix — add to `_ensure_palace`:**
```python
# Bootstrap learnings room in wing_myos if not exists
try:
    existing = self._collection.get(
        where={"wing": "wing_myos", "room": "learnings"},
        include=["metadatas"]
    )
    if not existing.get("ids"):
        self._collection.add(
            documents=["[learnings room bootstrap]"],
            metadatas=[{"wing": "wing_myos", "room": "learnings", "closet": "system"}],
            ids=[f"bootstrap_learnings_{int(time.time())}"]
        )
except Exception:
    pass  # Non-fatal
```

Also modify `recall_all` and `recall` to NOT require room filter — fall back to wing-only:
```python
# In _tool_recall_all, change filter building:
conditions = [{"wing": wing}]
if room and room not in ("", "all"):
    conditions.append({"room": room})
# Apply 0/1/2+ pattern from Fix 1.1
```

---

## P2 — SEARCH METADATA FIELDS MISMATCH

**File:** `/home/nehuen/.hermes/plugins/mempalace/mempalace/searcher.py`
**Lines:** ~70–100

**Fix:** In `add_drawer` metadata:
```python
metadata = {
    "wing": wing,
    "room": room,
    "closet": closet or "general",
    "category": category or "general",
    "source_file": source_file or "",
    "created_at": created_at or datetime.now().isoformat(),
    "last_accessed": last_accessed or datetime.now().isoformat(),
    "ttl_days": ttl_days,
    "session_project": session_project or "",
    "subject": subject or "",           # ← add
    "flags": json.dumps(flags or []),   # ← add
}
```

In `search_memories` result construction:
```python
item = {
    "id": ids[i],
    "content": doc,
    "wing": meta.get("wing"),
    "room": meta.get("room"),
    "closet": meta.get("closet"),
    "category": meta.get("category"),
    "subject": meta.get("subject"),
    "flags": json.loads(meta.get("flags", "[]")),
    "created_at": meta.get("created_at"),
    "last_accessed": meta.get("last_accessed"),
}
```

---

## P2 — `_parse_natural_fact` LIMITED PATTERNS

**File:** `/home/nehuen/.hermes/plugins/mempalace/__init__.py`
**Lines:** ~2295–2370

**Add these patterns:**
```python
{"pattern": r"^(?P<subj>\w+(?:\s+\w+)*)\s+uses\s+(?P<obj>\w+(?:\s+\w+)*)$", "pred": "uses"},
{"pattern": r"^(?P<subj>\w+(?:\s+\w+)*)\s+knows\s+(?P<obj>\w+(?:\s+\w+)*)$", "pred": "knows"},
{"pattern": r"^(?P<subj>\w+(?:\s+\w+)*)\s+is\s+from\s+(?P<obj>\w+(?:\s+\w+)*)$", "pred": "from"},
{"pattern": r"^(?P<subj>\w+(?:\s+\w+)*)\s+built\s+(?P<obj>\w+(?:\s+\w+)*)$", "pred": "built"},
{"pattern": r"^(?P<subj>\w+(?:\s+\w+)*)\s+depends\s+on\s+(?P<obj>\w+(?:\s+\w+)*)$", "pred": "depends_on"},
{"pattern": r"^(?P<subj>\w+(?:\s+\w+)*)\s+is\s+located\s+in\s+(?P<obj>\w+(?:\s+\w+)*)$", "pred": "located_in"},
{"pattern": r"^(?P<subj>\w+(?:\s+\w+)*)\s+has\s+a?\s+(?P<obj>\w+(?:\s+\w+)*)$", "pred": "has"},
```

---

## P2 — `remember` NL CATEGORIES MISS MILESTONE/PROBLEM/EMOTIONAL

**File:** `/home/nehuen/.hermes/plugins/mempalace/__init__.py`
**Line:** ~2285

**Fix:**
```python
# OLD
if category in ["fact", "preference", "decision"]:

# NEW
if category in ["fact", "preference", "decision", "milestone", "problem", "emotional"]:
```

---

## P3 — TAXONOMY CACHE NOT PERSISTED

**File:** `/home/nehuen/.hermes/plugins/mempalace/__init__.py`
**Function:** `_update_taxonomy_cache` and `_ensure_palace`

**Fix — add JSON file persistence:**
```python
def _load_taxonomy_cache(self):
    cache_path = os.path.join(self._palace_dir, "taxonomy_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                return json.load(f)
        except Exception:
            pass
    return {"wings": {}, "rooms": {}, "closets": {}}

def _save_taxonomy_cache(self, cache):
    cache_path = os.path.join(self._palace_dir, "taxonomy_cache.json")
    with open(cache_path, "w") as f:
        json.dump(cache, f)
```

---

## P3 — KG IN-MEMORY ONLY

**Problem:** KG triples are stored in a Python dict, lost on restart.

**Fix:**
```python
kg_path = os.path.join(self._palace_dir, "kg_triples.json")

def _kg_load(self):
    if os.path.exists(kg_path):
        try:
            return json.load(open(kg_path))
        except Exception:
            pass
    return []

def _kg_save(self, triples):
    json.dump(triples, open(kg_path, "w"))

# In _tool_kg_add: load, append, save
# In _tool_kg_invalidate: load, mark ended, save
```

---

## P3 — `_is_noise` EMPTY CONTENT GUARD

**File:** `/home/nehuen/.hermes/plugins/mempalace/__init__.py`
**Line:** ~2030 in `_tool_add_drawer`

**Fix:**
```python
content = content.strip() if content else ""
if not content or len(content) < 3:
    return json.dumps({"error": "Content too short or empty"})
if self._is_noise(content):
    return json.dumps({"error": "Content matches noise filter"})
```

---

## VERIFICATION CHECKLIST

```bash
# Test search (previously returning 0)
mempalace_search({"query": "Nehuen", "limit": 5})
# Expected: results from wing_general

# Test recall_all (previously broken ids)
mempalace_recall_all({})
# Expected: learnings from wing_myos

# Test recall with wing/room filters
mempalace_recall({"query": "Collatz", "wing": "wing_myos", "limit": 3})
# Expected: results if any exist in wing_myos

# Test check_duplicate with wing filter
mempalace_check_duplicate({"content": "test", "wing": "wing_myos"})
# Expected: {"is_duplicate": false} (no crash)

# Test session_diff
mempalace_session_diff({})
# Expected: valid diff output, added/removed not swapped

# Test list_rooms
mempalace_list_rooms({"wing": "wing_general"})
# Expected: room counts for wing_general

# Verify taxonomy includes learnings room
mempalace_get_taxonomy({})
# Expected: learnings listed under wing_myos
```

---

## FILES TO MODIFY

1. `/home/nehuen/.hermes/plugins/mempalace/__init__.py` — main plugin (~4131 lines)
2. `/home/nehuen/.hermes/plugins/mempalace/mempalace/searcher.py` — search logic

## ESTIMATED CHANGES

| Fix | Lines touched | Risk |
|-----|-------------|------|
| 1.1 searcher $and | ~20 | Medium — core search path |
| 1.2 recall_all ids | ~2 | Low |
| 1.3 check_duplicate | ~8 | Low |
| session_diff swap | ~15 | Medium — business logic |
| learnings bootstrap | ~12 | Low |
| search metadata | ~15 | Medium — storage schema |
| NL patterns | ~20 | Low |
| remember categories | ~1 | Low |
| taxonomy cache | ~30 | Medium — adds file I/O |
| KG persistence | ~25 | Medium |
| noise guard | ~3 | Low |

Total: ~150 lines across 2 files.
