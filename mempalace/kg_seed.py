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


def get_kg():
    try:
        from mempalace.knowledge_graph import KnowledgeGraph

        return KnowledgeGraph()
    except ImportError:
        print("ERROR: mempalace not installed. pip install mempalace")
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
