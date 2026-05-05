"""MemPalace tools — navigation tools.

Extracted from monolithic __init__.py during Phase 0 refactoring.
"""

from __future__ import annotations

import json

from pathlib import Path


class NavigationMixin:
    """Mixin providing navigation tools.

    Must be used alongside MempalaceMemoryProvider which provides:
    - self._collection, self._palace_path, self._kg
    - self._ensure_palace(), self._is_noise()
    - self._parse_natural_fact(), self._compress_aaak()
    - self._load_noise_patterns(), self._save_noise_patterns()
    - self._taxonomy_cache, self._default_wing, etc.
    """

    # ── Navigation tools ───────────────────────────────────

    def _tool_traverse(self, args: dict) -> str:
        try:
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.palace_graph import traverse

            start_room = args.get("start_room", "")
            max_hops = args.get("max_hops", args.get("max_depth", 3))
            results = traverse(start_room, max_hops=max_hops, col=self._collection)
            return json.dumps({"start_room": start_room, "traversal": results})
        except ImportError:
            return json.dumps({"error": "palace_graph not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_find_tunnels(self, args: dict) -> str:
        try:
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.palace_graph import find_tunnels

            wing_a = args.get("wing_a", "")
            wing_b = args.get("wing_b", "")
            tunnels = find_tunnels(wing_a=wing_a, wing_b=wing_b, col=self._collection)
            return json.dumps({"wing_a": wing_a, "wing_b": wing_b, "tunnels": tunnels})
        except ImportError:
            return json.dumps({"error": "palace_graph not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})
    def _tool_graph_stats(self) -> str:
        try:
            import sys

            _plugin_dir = Path(__file__).parent / "mempalace"
            if str(_plugin_dir) not in sys.path:
                sys.path.insert(0, str(_plugin_dir))
            from mempalace.palace_graph import graph_stats

            stats = graph_stats(col=self._collection)
            return json.dumps({"graph_stats": stats})
        except ImportError:
            return json.dumps({"error": "palace_graph not available"})
        except Exception as e:
            return json.dumps({"error": str(e)})