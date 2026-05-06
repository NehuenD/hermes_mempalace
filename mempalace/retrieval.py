"""
Strategy retrieval utilities — bridges wing_mistakes into search,
handles top-k tuning and result ranking.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def search_strategies(
    collection,
    query: str,
    top_k: int = 1,
    domains: Optional[list] = None,
    include_mistakes: bool = True,
    min_confidence: float = 0.0,
) -> list:
    """
    Unified strategy search across reasoningbank and optionally mistakes.

    This is the primary retrieval entry point used by strategy_system.py.

    Args:
        collection: ChromaDB collection
        query: Search query
        top_k: Results to return (default 1 per ReasoningBank paper)
        domains: Optional domain filter list
        include_mistakes: Whether to also search wing_mistakes
        min_confidence: Minimum confidence threshold

    Returns:
        Ranked list of strategy/lesson dicts
    """
    results = []

    try:
        where_clause = {"wing": "wing_reasoningbank"}
        if domains:
            where_clause["domain"] = {"$in": domains}

        query_results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )

        if query_results and query_results.get("ids") and query_results["ids"][0]:
            for i, doc_id in enumerate(query_results["ids"][0]):
                meta = query_results["metadatas"][0][i]
                if meta.get("confidence", 1.0) < min_confidence:
                    continue
                results.append(_format_result(doc_id, query_results, i))

        if include_mistakes:
            mistake_results = collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"wing": "wing_mistakes"},
                include=["documents", "metadatas", "distances"],
            )
            if (
                mistake_results
                and mistake_results.get("ids")
                and mistake_results["ids"][0]
            ):
                for i, doc_id in enumerate(mistake_results["ids"][0]):
                    meta = mistake_results["metadatas"][0][i]
                    results.append(
                        {
                            "id": doc_id,
                            "content": mistake_results["documents"][0][i],
                            "type": "lesson",
                            "domain": meta.get("room", "general"),
                            "confidence": 0.5,
                            "source": "wing_mistakes",
                            "relevance": 1.0
                            - (
                                mistake_results["distances"][0][i]
                                if mistake_results.get("distances")
                                else 0
                            ),
                        }
                    )

        results.sort(key=lambda x: x.get("relevance", 0), reverse=True)

        results = results[:top_k]

    except Exception as e:
        logger.warning(f"Strategy search failed: {e}")

    return results


def _format_result(doc_id: str, query_results, index: int) -> dict:
    """Format a single result from ChromaDB query output."""
    doc = query_results["documents"][0][index] if query_results.get("documents") else ""
    meta = (
        query_results["metadatas"][0][index] if query_results.get("metadatas") else {}
    )
    distance = (
        query_results["distances"][0][index] if query_results.get("distances") else 0
    )

    try:
        content = json.loads(doc) if isinstance(doc, str) else doc
    except (json.JSONDecodeError, TypeError):
        content = {"raw": str(doc)[:200]}

    return {
        "id": doc_id,
        "content": content,
        "type": meta.get("type", "strategy"),
        "domain": meta.get("domain", "general"),
        "confidence": meta.get("confidence", 0.5),
        "source": meta.get("wing", "unknown"),
        "relevance": 1.0 - distance,
    }
