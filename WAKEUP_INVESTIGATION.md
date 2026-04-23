# Wake-Up Injection Investigation Report

**Date:** 2026-04-22
**Status:** ROOT CAUSE IDENTIFIED — NOT YET FIXED

---

## Observed Symptoms

The agent's MEMORY block (at session startup) shows:

```
## L0 — IDENTITY
No identity configured. Create ~/.mempalace/identity.txt

## L1 — No palace found. Run: mempalace mine <dir>
```

This appears even though the MemPalace plugin tools work correctly — `mempalace_session_read` returns 5 sessions with real data, and all drawer operations work fine.

---

## Architecture Overview

The wake-up injection involves **three separate systems** with **two separate ChromaDB databases**:

### System 1: Plugin Tool Layer (`mempalace_*` tools)
- **Location:** `~/.hermes/plugins/mempalace/__init__.py`
- **ChromaDB path:** `~/.mempalace/palace/` (via `self._palace_path / "palace"`)
- **Status:** ✅ Working correctly
- **Evidence:** `mempalace_session_read` returns 5 sessions, `mempalace_status` shows 475 drawers

### System 2: MemPalace Layers (`mempalace.layers`)
- **Location:** Installed at `~/.local/share/mise/installs/python/3.13.7/lib/python3.13/site-packages/mempalace/layers.py`
- **ChromaDB path:** `~/.mempalace/` (palace_path passed directly, no `/palace` suffix)
- **Status:** ❌ BROKEN — wrong path
- **Evidence:** ChromaDB error `file is not a database` when initializing Layer0/Layer1

### System 3: Hermes Memory Provider Integration
- **Location:** `~/.hermes/agent/memory_provider.py` and `memory_manager.py`
- **Method:** Calls `mempalace_plugin.system_prompt_block()` and `wake_up_injection_block()`
- **Status:** ⚠️ Inherits broken data from System 2

---

## ChromaDB Path Mismatch (Root Cause)

The plugin and layers module use **two completely different ChromaDB paths**:

| Component | Path Used | Actual Data? |
|---|---|---|
| Plugin tools | `~/.mempalace/palace/` | ✅ YES — 475 drawers, sessions |
| Layer0/Layer1 (layers.py) | `~/.mempalace/` | ❌ NO — "file is not a database" error |

Evidence:
```
$ ls ~/.mempalace/
chroma.sqlite3        # 188KB — NOT a valid SQLite DB (corrupt or wrong format)
knowledge_graph.sqlite3
palace/               # Subdirectory containing the actual ChromaDB
  chroma.sqlite3      # 4.9MB — THE REAL ChromaDB
```

The root-level `chroma.sqlite3` (188KB) is **not a valid SQLite database**:
```
Header bytes: 53544c69741703030013f0e6f8344de9
Is SQLite3 header: False
```

This file predates the `/palace` subdirectory structure and was never migrated.

---

## Failure Chain

### `_load_wake_up_context()` (Plugin, line 1268)
```python
palace_str = str(self._palace_path)  # → '/home/nehuen/.mempalace/'
l0 = Layer0(palace_path=palace_str, ...)
l1 = Layer1(palace_path=palace_str, wing=self._default_wing)
self._l0_identity = l0.render()
self._l1_story = l1.generate()
```

1. `self._palace_path` = `~/.mempalace/` (plugin's palace root)
2. `palace_str` = `'/home/nehuen/.mempalace/'`
3. **Layer0** initializes its own ChromaDB client at `~/.mempalace/`
4. ChromaDB tries to open the corrupt/wrong `chroma.sqlite3` → **FAILS SILENTLY**
5. Exception caught at line 1284, falls back to template text:
   ```python
   except Exception as e:
       logger.debug("Failed to load wake-up context: %s", e)
       self._l0_identity = "## L0 — IDENTITY\nNo identity configured..."
       self._l1_story = "## L1 — No palace found. Run: mempalace mine <dir>"
   ```

### `_get_recent_sessions_block()` (Plugin, line 1290)
```python
results = self._db.get(
    limit=5,
    where={"$and": [{"wing": {"$eq": "wing_myos"}}, {"room": {"$eq": "sessions"}}]}
)
```
- Uses the **plugin's own ChromaDB client** at `~/.mempalace/palace/`
- **Working correctly** — sessions load fine through this path
- BUT: This is a **separate code path** from the L0/L1 rendering
- Sessions appear in `Recent Sessions` section of system prompt ✅

### `system_prompt_block()` vs `wake_up_injection_block()`
- Both call `_load_wake_up_context()` to get L0/L1 content
- Both inherit the same failure (Layer0/Layer1 rendering with wrong path)
- Sessions block (separate query) works correctly ✅

---

## Why Sessions Work But L0/L1 Don't

Sessions use the plugin's own ChromaDB client:
```python
# In _tool_session_read / _get_recent_sessions_block:
results = self._db.get(...)  # self._db = self._palace_path / "palace"
```

L0/Layer1 use the external `mempalace.layers` module which has the wrong path hardcoded.

---

## Layer0/Layer1 Initialization in `layers.py`

From `layers.py` line ~118:
```python
def __init__(self, palace_path: str):
    self.palace_path = palace_path  # Gets '/home/nehuen/.mempalace/'
    self._client = chromadb.PersistentClient(path=palace_path)
    # Creates client at ~/.mempalace/ — WRONG PATH
```

The `/palace` subdirectory was introduced in the plugin (not in the upstream mempalace package), creating a path divergence between the plugin and the layers module.

---

## Why The Failure Is Silent

The `_load_wake_up_context()` exception handler at line 1284 catches all exceptions with `logger.debug()` — it logs at DEBUG level only, which:

1. Never appears in normal logs (only visible with verbose logging)
2. Silently replaces real data with template text
3. Makes the issue invisible unless you:
   - Run with DEBUG logging enabled, OR
   - Inspect session JSON files, OR
   - Read the plugin code directly

---

## Session Files Confirm the Broken State

In session file `session_20260422_220451_95b877.json` (from previous session):

```
MemPalace Memory
## L0 — IDENTITY
No identity configured. Create ~/.mempalace/identity.txt

## L1 — No palace found. Run: mempalace mine <dir>

When user asks to 'remember' something, use mempalace_remember...

Recent Sessions
- SESSION → 2026-04-20|MyOS:mempalace-session-tools|reviewed mempalace_session_write/read...
- SESSION → 2026-04-20|mempalace:session-tools-v1|MemPalace session tools are fully live...
- SESSION → 2026-04-20|mempalace:session-tools-v1|MemPalace session tools are fully live...
```

The `Recent Sessions` section has real data ✅, but L0/L1 show template text ❌.

---

## The `~/.mempalace/identity.txt` File

- **Does NOT exist** at `~/.mempalace/identity.txt`
- Even if it did, Layer0 renders the identity file directly from disk (not ChromaDB)
- This is a **separate issue** from the ChromaDB path mismatch
- But it also contributes to L0 showing the "No identity configured" template

---

## Summary

| Issue | Location | Severity | 
|---|---|---|
| ChromaDB path mismatch: layers.py uses `~/.mempalace/`, plugin uses `~/.mempalace/palace/` | `layers.py` + plugin `_load_wake_up_context()` | **CRITICAL** |
| Silent failure: exception caught with only `logger.debug()` | Plugin `_load_wake_up_context()` line 1284 | **HIGH** |
| identity.txt doesn't exist | `~/.mempalace/identity.txt` | **LOW** |
| Sessions work via separate code path, L0/L1 don't | Separate query paths | **N/A** |

---

## Fix Direction (Not Applied)

The fix requires reconciling the path between the plugin and `layers.py`:

1. **Option A (layers.py):** Make `Layer0`/`Layer1` append `/palace` to the path, matching the plugin's structure
2. **Option B (plugin):** Have the plugin pass `~/.mempalace/palace/` instead of `~/.mempalace/` to the layers
3. **Option C (both):** Add path normalization in `_load_wake_up_context()` before passing to layers

The fix should also:
- Log failures at WARNING level (not DEBUG) so the issue is visible
- Handle the `~/.mempalace/identity.txt` file existence
- Possibly add validation that the ChromaDB path actually contains valid data
