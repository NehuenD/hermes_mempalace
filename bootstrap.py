"""Shared sys.path bootstrap for MemPalace.

Ensures the plugin root is on sys.path so that 'from .xxx import yyy'
resolves to the LOCAL plugin modules, not any PyPI-installed mempalace.

Usage:
    from .bootstrap import ensure_local_imports, purge_pypi_mempalace

    ensure_local_imports()   # call once at plugin init
    purge_pypi_mempalace()   # call if you want to evict PyPI mempalace from sys.modules
"""

import os
import sys
from pathlib import Path


def _plugin_root() -> Path:
    """Absolute path to the plugin root directory."""
    return Path(__file__).resolve().parent


def _mempalace_dir() -> Path:
    """Absolute path to the plugin root directory (used for PyPI shadow check)."""
    return Path(__file__).resolve().parent


def ensure_local_imports() -> None:
    """Add the plugin root to sys.path if not already present.

    Call this once at plugin initialization so that all 'from .xxx import yyy'
    imports resolve to the local subpackage rather than a PyPI-installed mempalace.
    """
    root = str(_plugin_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def purge_pypi_mempalace() -> None:
    """Remove a PyPI-installed 'mempalace' from sys.modules if one is cached.

    Only needed when a standalone script (cli.py, client.py, kg_seed.py) runs
    in an environment where a pip package might shadow the local plugin.
    """
    if "mempalace" not in sys.modules:
        return
    mp_mod = sys.modules["mempalace"]
    local_init = str(_mempalace_dir() / "__init__.py")
    mod_file = getattr(mp_mod, "__file__", None)
    if mod_file and os.path.exists(local_init) and not os.path.samefile(
        os.path.dirname(os.path.abspath(mod_file)),
        os.path.dirname(os.path.abspath(local_init)),
    ):
        del sys.modules["mempalace"]
