"""MemPalace tools — diary tools.

Extracted from monolithic __init__.py during Phase 0 refactoring.
"""

from __future__ import annotations

import json

from pathlib import Path


class DiaryMixin:
    """Mixin providing diary tools.

    Must be used alongside MempalaceMemoryProvider which provides:
    - self._collection, self._palace_path, self._kg
    - self._ensure_palace(), self._is_noise()
    - self._parse_natural_fact(), self._compress_aaak()
    - self._load_noise_patterns(), self._save_noise_patterns()
    - self._taxonomy_cache, self._default_wing, etc.
    """

    # ── Diary tools ────────────────────────────────────────

    def _tool_diary_write(self, args: dict) -> str:
        try:
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.mcp_server import tool_diary_write

            agent = args.get("agent", "")
            entry = args.get("entry", "")
            result = tool_diary_write(agent, entry)
            return json.dumps({"result": result})
        except ImportError:
            return json.dumps({"error": "mcp_server not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_diary_read(self, args: dict) -> str:
        try:
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.mcp_server import tool_diary_read

            agent = args.get("agent", "")
            last_n = args.get("last_n", 10)
            result = tool_diary_read(agent, last_n)
            return json.dumps({"agent": agent, "entries": result})
        except ImportError:
            return json.dumps({"error": "mcp_server not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})