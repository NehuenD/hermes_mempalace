"""
Strategy injection into system prompt with self-contrast.

Retrieves top-k relevant strategies from wing_reasoningbank and injects
them with ReasoningBank-style reasoning instruction. The self-contrast
feature explicitly compares the current approach to past strategies,
triggering reflective reasoning rather than passive reading.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def retrieve_relevant_strategies(
    collection,
    query: str,
    top_k: int = 1,
    include_mistakes: bool = True,
) -> list:
    """
    Retrieve top-k relevant strategies for a given context query.

    Queries wing_reasoningbank for strategies, and optionally wing_mistakes.

    Args:
        collection: ChromaDB collection
        query: Current context/query to match against
        top_k: Number of strategies to retrieve (default 1 per paper)
        include_mistakes: Also query wing_mistakes for failure-based insights

    Returns:
        list of strategy dicts with metadata
    """
    if not collection:
        return []

    strategies = []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"wing": "wing_reasoningbank"},
            include=["documents", "metadatas", "distances"],
        )

        if results and results.get("ids") and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                doc = results["documents"][0][i] if results.get("documents") else ""
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results["distances"][0][i] if results.get("distances") else 0

                try:
                    strategy_data = json.loads(doc) if isinstance(doc, str) else doc
                except (json.JSONDecodeError, TypeError):
                    strategy_data = {"content": doc}

                strategies.append(
                    {
                        "id": doc_id,
                        "content": strategy_data,
                        "type": meta.get("type", "strategy"),
                        "domain": meta.get("domain", "general"),
                        "confidence": meta.get("confidence", 0.5),
                        "relevance": 1.0 - distance,
                    }
                )

        if include_mistakes:
            mistake_results = collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"$and": [{"wing": "wing_mistakes"}, {"room": "diary"}]},
                include=["documents", "metadatas", "distances"],
            )
            if (
                mistake_results
                and mistake_results.get("ids")
                and mistake_results["ids"][0]
            ):
                for i, doc_id in enumerate(mistake_results["ids"][0]):
                    doc = (
                        mistake_results["documents"][0][i]
                        if mistake_results.get("documents")
                        else ""
                    )
                    meta = (
                        mistake_results["metadatas"][0][i]
                        if mistake_results.get("metadatas")
                        else {}
                    )
                    distance = (
                        mistake_results["distances"][0][i]
                        if mistake_results.get("distances")
                        else 0
                    )

                    strategies.append(
                        {
                            "id": doc_id,
                            "content": {"lesson": doc, "type": "lesson"},
                            "type": "lesson",
                            "domain": meta.get("room", "general"),
                            "confidence": 0.5,
                            "relevance": 1.0 - distance,
                        }
                    )

    except Exception as e:
        logger.warning(f"Strategy retrieval failed: {e}")

    return strategies


def _extract_text(content) -> str:
    """Extract human-readable text from a strategy/lesson content dict."""
    if isinstance(content, dict):
        return (
            content.get("strategy")
            or content.get("lesson")
            or content.get("merged")
            or content.get("content", "")
        )
    return str(content)


def _infer_query_domain(query: str) -> str:
    """
    Heuristically infer the domain of the current query.

    Simple keyword-based detection for common domains. Returns 'general'
    when no specific domain is detected.
    """
    if not query:
        return "general"
    query_lower = query.lower()

    domain_keywords = {
        "debugging": [
            "debug", "error", "bug", "fix", "broken", "fail", "traceback",
            "exception", "crash", "issue", "problem", "doesn't work",
        ],
        "testing": [
            "test", "assert", "pytest", "unittest", "spec", "coverage",
        ],
        "api-design": [
            "api", "endpoint", "route", "rest", "graphql", "http",
        ],
        "database": [
            "database", "db", "sql", "query", "index", "migration",
            "schema", "table", "postgres", "mysql", "mongodb",
        ],
        "deployment": [
            "deploy", "ci", "cd", "pipeline", "docker", "kubernetes",
            "container", "build", "release", "production",
        ],
        "frontend": [
            "ui", "component", "react", "vue", "css", "html",
            "frontend", "layout", "responsive",
        ],
        "security": [
            "security", "auth", "permission", "token", "oauth",
            "encrypt", "vulnerability", "cve",
        ],
        "devops": [
            "infra", "server", "config", "provision", "ansible",
            "terraform", "nix", "arch", "linux",
        ],
    }

    scores = {}
    for domain, keywords in domain_keywords.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[domain] = score

    if scores:
        return max(scores, key=scores.get)
    return "general"


def build_strategy_block(strategies: list, current_query: Optional[str] = None) -> str:
    """
    Build a system prompt block with self-contrast reasoning.

    When current_query is provided, includes explicit contrastive prompts
    comparing each strategy to the current approach. Without a query, falls
    back to the basic strategy listing (backward compatible).

    Args:
        strategies: List of strategy dicts from retrieve_relevant_strategies()
        current_query: Optional current context query for contrastive framing

    Returns:
        Formatted system prompt block string, or empty string if no strategies
    """
    if not strategies:
        return ""

    query_domain = _infer_query_domain(current_query) if current_query else "general"

    lines = ["\n## Past Relevant Strategies (ReasoningBank)"]

    if current_query:
        # Self-contrast mode: active comparison
        lines.append(
            "You are currently working in a context that matches past experiences. "
            "For each strategy below, explicitly compare it to your current approach:"
        )
        lines.append("")
        lines.append("- Does this strategy apply to your current situation?")
        lines.append(
            "- If it applies, why might it work even better than what you're doing now?"
        )
        lines.append(
            "- If it doesn't apply, what's different about this situation?"
        )
        lines.append(
            "- Consider the confidence score: high-confidence strategies "
            "have been repeatedly validated."
        )
        lines.append("")
        lines.append(
            f"Context domain detected: {query_domain}. "
            "Domain-matched strategies are especially relevant — pay extra attention to them."
        )
    else:
        # Basic mode (backward compatible)
        lines.append("Consider these past strategies. Which apply here? Why?")

    lines.append("")

    for i, s in enumerate(strategies, 1):
        content = s.get("content", {})
        text = _extract_text(content)

        strategy_type = s.get("type", "strategy").upper()
        domain = s.get("domain", "general")
        confidence = s.get("confidence", 0.0)
        relevance = s.get("relevance", 0.0)

        lines.append(f"{i}. [{strategy_type}] ({domain}, confidence={confidence:.2f}, relevance={relevance:.2f})")
        lines.append(f"   {text}")

        # Add contrastive prompt when in self-contrast mode
        if current_query:
            domain_match = domain == query_domain
            if domain_match:
                lines.append(
                    f"   >> Domain match! This {strategy_type.lower()} is from the same "
                    f"domain ({domain}) as your current context — high priority to consider."
                )
            elif confidence > 0.7:
                lines.append(
                    f"   >> High-confidence {strategy_type.lower()} ({confidence:.0%}). "
                    "Even though the domain differs, the approach may transfer."
                )
            else:
                lines.append(
                    f"   >> Different domain ({domain} vs {query_domain}), "
                    f"lower confidence ({confidence:.0%}). Evaluate critically."
                )
        lines.append("")

    # Add closing meta-instruction for self-contrast mode
    if current_query and strategies:
        lines.append(
            "After reviewing, briefly note which strategy (if any) influenced "
            "your approach and why."
        )

    return "\n".join(lines)
