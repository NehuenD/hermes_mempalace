#!/usr/bin/env python3
"""
searcher.py — Find anything. Exact words.

Semantic search against the palace.
Returns verbatim text — the actual words, never summaries.
"""

import sys
from pathlib import Path

import chromadb


def search(
    query: str, palace_path: str, wing: str = None, room: str = None, n_results: int = 5
):
    """
    Search the palace. Returns verbatim drawer content.
    Optionally filter by wing (project) or room (aspect).
    """
    try:
        client = chromadb.PersistentClient(path=palace_path)
        col = client.get_collection("mempalace_drawers")
    except Exception:
        print(f"\n  No palace found at {palace_path}")
        print("  Run: mempalace init <dir> then mempalace mine <dir>")
        sys.exit(1)

    # Build where filter
    where = {}
    if wing and room:
        where = {"$and": [{"wing": wing}, {"room": room}]}
    elif wing:
        where = {"wing": wing}
    elif room:
        where = {"room": room}

    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)

    except Exception as e:
        print(f"\n  Search error: {e}")
        sys.exit(1)

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    if not docs:
        print(f'\n  No results found for: "{query}"')
        return

    print(f"\n{'=' * 60}")
    print(f'  Results for: "{query}"')
    if wing:
        print(f"  Wing: {wing}")
    if room:
        print(f"  Room: {room}")
    print(f"{'=' * 60}\n")

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        similarity = round(1 - dist, 3)
        source = Path(meta.get("source_file", "?")).name
        wing_name = meta.get("wing", "?")
        room_name = meta.get("room", "?")

        print(f"  [{i}] {wing_name} / {room_name}")
        print(f"      Source: {source}")
        print(f"      Match:  {similarity}")
        print()
        # Print the verbatim text, indented
        for line in doc.strip().split("\n"):
            print(f"      {line}")
        print()
        print(f"  {'─' * 56}")

    print()


def search_memories(
    query: str,
    palace_path: str,
    wing: str = None,
    room: str = None,
    closet: str = None,
    category: str = None,
    subject: str = None,
    n_results: int = 5,
    client: "chromadb.PersistentClient" = None,
) -> dict:
    """
    Programmatic search — returns a dict instead of printing.
    Used by the MCP server and other callers that need data.
    Supports metadata pre-filtering for closet/category.
    Accepts optional pre-existing client to avoid redundant creation.
    """
    try:
        if client is None:
            client = chromadb.PersistentClient(path=palace_path)
        col = client.get_collection("mempalace_drawers")
    except Exception as e:
        return {"error": f"No palace found at {palace_path}: {e}"}

    # Build where filter - support closet/category pre-filtering
    def _filter(v):
        return v and v not in ("", "all")

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

    if len(conditions) == 0:
        where = {}
    elif len(conditions) == 1:
        where = conditions[0]
    else:
        where = {"$and": conditions}

    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)
    except Exception as e:
        return {"error": f"Search error: {e}"}

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]
    ids = results["ids"][0]

    hits = []
    import json as json_module

    for id, doc, meta, dist in zip(ids, docs, metas, dists):
        hits.append(
            {
                "id": id,
                "text": doc,
                "wing": meta.get("wing", "unknown"),
                "room": meta.get("room", "unknown"),
                "closet": meta.get("closet", ""),
                "category": meta.get("category", ""),
                "subject": meta.get("subject", ""),
                "flags": json_module.loads(meta.get("flags", "[]")),
                "source_file": Path(meta.get("source_file", "?")).name,
                "similarity": round(1 - dist, 3),
            }
        )

    return {
        "query": query,
        "filters": {"wing": wing, "room": room, "closet": closet, "category": category},
        "results": hits,
    }
