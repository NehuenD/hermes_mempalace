#!/usr/bin/env python3
"""KG Seeding Migration Script.

One-time migration to populate the knowledge graph from SOUL.md and entity_registry.json.

Usage:
    python scripts/kg_seed.py

Entity codes follow AAAK format: NEH=Nehuen (user), others from entity_registry.json
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure local plugin modules shadow any PyPI mempalace package
_this_dir = os.path.dirname(os.path.abspath(__file__))
# _this_dir is now the plugin root (flat structure, no subpackage)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

# Purge any cached PyPI mempalace module
if 'mempalace' in sys.modules:
    _mp_mod = sys.modules['mempalace']
    _local_init = os.path.join(_this_dir, '__init__.py')
    if hasattr(_mp_mod, '__file__') and _mp_mod.__file__ is not None:
        _mod_dir = os.path.dirname(os.path.abspath(_mp_mod.__file__))
        if not os.path.samefile(_mod_dir, _this_dir):
            del sys.modules['mempalace']

from .bootstrap import ensure_local_imports, purge_pypi_mempalace

ensure_local_imports()
purge_pypi_mempalace()


def get_kg():
    try:
        from .knowledge_graph import KnowledgeGraph

        return KnowledgeGraph()
    except ImportError:
        print("ERROR: mempalace.knowledge_graph module not found in local plugin subpackage")
        sys.exit(1)


def seed_from_soul(kg, soul_path: Path) -> int:
    """Extract facts from SOUL.md and add to KG."""
    if not soul_path.exists():
        print(f"SKIP: SOUL.md not found at {soul_path}")
        return 0

    content = soul_path.read_text(encoding="utf-8")
    count = 0
    now = datetime.now().isoformat()

    facts = [
        ("NEH", "core_value", "genuine_helpful", now),
        ("NEH", "core_value", "have_opinions", now),
        ("NEH", "core_value", "resourceful", now),
        ("NEH", "core_value", "earn_trust", now),
        ("NEH", "core_value", "remember_guest", now),
    ]

    boundary_keywords = ["private", "period", "ask_before", "careful"]
    for kw in boundary_keywords:
        facts.append(("NEH", "boundary", kw, now))

    vibe_keywords = ["concise", "thorough", "not_corporate", "not_sycophant"]
    for kw in vibe_keywords:
        facts.append(("NEH", "vibe", kw, now))

    for subject, predicate, obj, valid_from in facts:
        try:
            kg.add_triple(subject, predicate, obj, valid_from=valid_from)
            count += 1
        except Exception as e:
            print(f"WARN: Failed to add ({subject}, {predicate}, {obj}): {e}")

    print(f"Added {count} triples from SOUL.md")
    return count


def seed_from_entity_registry(kg, registry_path: Path) -> int:
    """Extract entity facts from entity_registry.json."""
    if not registry_path.exists():
        print(f"SKIP: entity_registry.json not found")
        return 0

    content = json.loads(registry_path.read_text(encoding="utf-8"))
    count = 0
    now = datetime.now().isoformat()

    for name, data in content.get("people", {}).items():
        entity_code = name[:3].upper()
        aliases = data.get("aliases", [])
        contexts = data.get("contexts", [])
        relationship = data.get("relationship", "")

        if relationship:
            kg.add_triple(
                "NEH", "relationship", f"{entity_code}:{relationship}", valid_from=now
            )
            count += 1

        for ctx in contexts:
            kg.add_triple(entity_code, "context", ctx, valid_from=now)
            count += 1

        for alias in aliases:
            kg.add_triple(entity_code, "alias_of", alias, valid_from=now)
            count += 1

    print(f"Added {count} triples from entity_registry.json")
    return count


def main():
    hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    soul_path = Path(hermes_home) / "SOUL.md"
    registry_path = Path.home() / ".mempalace" / "entity_registry.json"

    print(f"KG Seeding Migration")
    print(f"  SOUL.md: {soul_path}")
    print(f"  entity_registry: {registry_path}")

    kg = get_kg()
    total = 0

    total += seed_from_soul(kg, soul_path)
    total += seed_from_entity_registry(kg, registry_path)

    print(f"\nMigration complete: {total} total triples added")


if __name__ == "__main__":
    main()
