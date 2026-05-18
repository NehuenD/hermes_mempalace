"""
Closed-loop self-evolution for ReasoningBank strategies.

Consolidation is the "C" in the Retrieve-Judge-Extract-Consolidate loop.
Periodically run to:
1. Dedup similar strategies via embedding + LLM merge
2. Adjust confidence scores based on retrieval frequency / age
3. Prune outdated or low-confidence items
4. Store merged items back, removing originals
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Maximum number of items to process in one consolidation cycle
_MAX_BATCH = 100
# Default embedding similarity threshold for "near duplicate"
_DEFAULT_SIMILARITY = 0.85
# Absolute minimum confidence — below this, prune unconditionally
_MIN_CONFIDENCE = 0.15
# Default age in days after which low-confidence items are pruned
_MAX_AGE_DAYS = 90

MERGE_SYSTEM_PROMPT = """\
You are a strategy consolidation assistant. Two similar strategies or lessons \
have been extracted from agent sessions. Merge them into ONE abstract, \
generalizable item that preserves the core insight of both.

Rules:
1. The merged item must be MORE abstract than either input — never less.
2. Remove any session-specific details (URLs, filenames, IDs).
3. Keep the most informative domain label.

If they contradict each other, pick the one with higher confidence and explain the trade-off.

Output valid JSON matching this schema:
{
  "merged": "The abstract, generalizable strategy/lesson (1-3 sentences)",
  "domain": "best domain label for the merged item",
  "type": "strategy" or "lesson",
  "confidence": mean confidence of the two inputs (float 0.0-1.0),
  "rationale": "Brief justification of how they were merged"
}
"""


def _get_all_reasoningbank_items(collection, limit: int = _MAX_BATCH) -> list:
    """Fetch all items from wing_reasoningbank, newest first."""
    try:
        results = collection.get(
            where={"wing": "wing_reasoningbank"},
            limit=limit,
            include=["documents", "metadatas"],
        )
        items = []
        if results and results.get("ids"):
            ids_list = results["ids"]
            docs_list = results.get("documents") or []
            metas_list = results.get("metadatas") or []
            for i in range(len(ids_list)):
                meta = {}
                if metas_list and i < len(metas_list) and metas_list[i] is not None:
                    meta = metas_list[i]
                doc = ""
                if docs_list and i < len(docs_list) and docs_list[i] is not None:
                    doc = docs_list[i]
                items.append({
                    "id": ids_list[i],
                    "document": doc,
                    "metadata": meta,
                })
        return items
    except Exception as e:
        logger.warning("Failed to fetch reasoningbank items: %s", e)
        return []


def _parse_item(item: dict) -> dict:
    """Parse the JSON document from a stored item."""
    doc = item.get("document", "")
    if isinstance(doc, str):
        try:
            return json.loads(doc)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(doc, dict):
        return doc
    return {}


def _item_age_days(item: dict) -> float:
    """Calculate age in days from extracted_at metadata."""
    meta = item.get("metadata", {})
    extracted = meta.get("extracted_at") or meta.get("date", "")
    if not extracted:
        return 0.0
    try:
        dt = datetime.fromisoformat(extracted)
        return (datetime.now() - dt).total_seconds() / 86400
    except (ValueError, TypeError):
        return 0.0


def _get_confidence(item: dict) -> float:
    """Get confidence from metadata, defaulting to 0.5."""
    meta = item.get("metadata", {})
    return float(meta.get("confidence", 0.5))


def _content_text(item: dict) -> str:
    """Extract the human-readable strategy/lesson text."""
    parsed = _parse_item(item)
    return parsed.get("strategy") or parsed.get("lesson") or parsed.get("merged", "")


def find_candidates(collection, threshold: float = _DEFAULT_SIMILARITY) -> list:
    """
    Find pairs of similar strategies using ChromaDB's built-in similarity.

    For each item, queries the collection for its nearest neighbors within
    threshold distance. Returns list of (item_a, item_b, similarity) tuples.

    Args:
        collection: ChromaDB collection
        threshold: Minimum similarity (0.0-1.0) to consider a candidate pair

    Returns:
        List of (id_a, id_b, similarity) tuples for pairs above threshold
    """
    items = _get_all_reasoningbank_items(collection)
    if len(items) < 2:
        return []

    candidates = []
    seen_pairs = set()

    for item in items:
        item_id = item["id"]
        # Use the stored document text for querying, matching how embeddings
        # were computed (JSON blobs). Using plain text against JSON-embedded
        # items produces artificially low similarity scores.
        query_text = item.get("document", "") or _content_text(item)
        if not query_text:
            continue

        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=min(5, len(items)),
                where={"wing": "wing_reasoningbank"},
                include=["distances", "metadatas"],
            )

            if not results or not results.get("ids") or not results["ids"][0]:
                continue

            for j, neighbor_id in enumerate(results["ids"][0]):
                if neighbor_id == item_id:
                    continue
                distance = results["distances"][0][j]
                similarity = 1.0 - distance

                if similarity >= threshold:
                    pair_key = tuple(sorted([item_id, neighbor_id]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        candidates.append((item_id, neighbor_id, similarity))

        except Exception as e:
            logger.debug("Query failed for %s: %s", item_id, e)
            continue

    candidates.sort(key=lambda x: x[2], reverse=True)
    logger.info("Found %d candidate pairs above threshold %.2f", len(candidates), threshold)
    return candidates


def merge_pair(
    collection, id_a: str, id_b: str, similarity: float, llm_call_fn: Callable,
) -> Optional[str]:
    """
    Merge two similar strategy items using LLM.

    Args:
        collection: ChromaDB collection
        id_a, id_b: IDs of the items to merge
        similarity: Their embedding similarity score
        llm_call_fn: Function(prompt, system_prompt) -> str

    Returns:
        New item ID if merge succeeded, None otherwise
    """
    try:
        results = collection.get(
            ids=[id_a, id_b],
            include=["documents", "metadatas"],
        )
        if not results or not results.get("ids") or len(results["ids"]) < 2:
            logger.warning("Could not fetch both items for merge")
            return None

        item_a_doc = results["documents"][0] if results.get("documents") else ""
        item_b_doc = results["documents"][1] if results.get("documents") else ""
        item_a_meta = results["metadatas"][0] if results.get("metadatas") else {}
        item_b_meta = results["metadatas"][1] if results.get("metadatas") else {}

        prompt = (
            f"Merging two strategies/lessons (similarity={similarity:.2f}):\n\n"
            f"=== ITEM A (confidence={item_a_meta.get('confidence', '?')}, "
            f"domain={item_a_meta.get('domain', '?')}) ===\n"
            f"{item_a_doc}\n\n"
            f"=== ITEM B (confidence={item_b_meta.get('confidence', '?')}, "
            f"domain={item_b_meta.get('domain', '?')}) ===\n"
            f"{item_b_doc}\n\n"
            f"Merge these into ONE abstract strategy/lesson."
        )

        response = llm_call_fn(prompt, MERGE_SYSTEM_PROMPT)
        merged = json.loads(response)

        if not merged.get("merged"):
            logger.warning("LLM merge returned empty result")
            return None

        # Resolve type — prefer strategy if mixed
        merged_type = merged.get("type", "strategy")
        domain = merged.get("domain", item_a_meta.get("domain", "general"))
        confidence = merged.get("confidence", _get_confidence({"metadata": item_a_meta}))

        now = datetime.now()
        new_id = (
            f"reasoningbank_merged_{now.strftime('%Y%m%d_%H%M%S')}_"
            f"{hash(merged['merged']) & 0xFFFFFF:06x}"
        )

        merged_item = {
            "strategy" if merged_type == "strategy" else "lesson": merged["merged"],
            "domain": domain,
            "type": merged_type,
            "confidence": confidence,
            "rationale": merged.get("rationale", ""),
            "merged_from": [id_a, id_b],
        }

        collection.add(
            ids=[new_id],
            documents=[json.dumps(merged_item)],
            metadatas=[{
                "wing": "wing_reasoningbank",
                "room": "room_strategies",
                "type": merged_type,
                "domain": domain,
                "confidence": confidence,
                "source_session": f"consolidation_merge:{id_a},{id_b}",
                "extracted_at": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "merged": True,
                "merged_from": f"{id_a},{id_b}",
            }],
        )

        # Remove originals
        collection.delete(ids=[id_a, id_b])

        logger.info(
            "Merged %s + %s -> %s (sim=%.2f, domain=%s)",
            id_a[:25], id_b[:25], new_id[:30], similarity, domain,
        )
        return new_id

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse merge response: %s", e)
        return None
    except Exception as e:
        logger.warning("Merge failed: %s", e)
        return None


def prune_strategies(
    collection,
    min_confidence: float = _MIN_CONFIDENCE,
    max_age_days: int = _MAX_AGE_DAYS,
) -> dict:
    """
    Remove strategies that are too old or have too low confidence.

    Args:
        collection: ChromaDB collection
        min_confidence: Items below this confidence are pruned
        max_age_days: Items older than this (with low confidence) are pruned

    Returns:
        dict with counts of pruned items
    """
    items = _get_all_reasoningbank_items(collection)
    to_prune = []
    pruned_low_conf = 0
    pruned_old = 0

    for item in items:
        meta = item.get("metadata", {})
        confidence = float(meta.get("confidence", 0.5))
        age = _item_age_days(item)
        item_id = item["id"]

        # Always prune extremely low confidence
        if confidence < min_confidence:
            to_prune.append(item_id)
            pruned_low_conf += 1
            continue

        # Prune old items with below-average confidence
        if age > max_age_days and confidence < 0.5:
            to_prune.append(item_id)
            pruned_old += 1

    if to_prune:
        collection.delete(ids=to_prune)
        logger.info(
            "Pruned %d items (%d low confidence, %d old)",
            len(to_prune), pruned_low_conf, pruned_old,
        )

    return {
        "pruned_total": len(to_prune),
        "pruned_low_confidence": pruned_low_conf,
        "pruned_old": pruned_old,
    }


def update_confidence_scores(
    collection, retrieval_history: Optional[dict] = None
) -> dict:
    """
    Adjust confidence scores based on retrieval frequency and age.

    Confidence formula:
        base_confidence * (1 + 0.1 * retrieval_count) * age_decay

    Where age_decay = max(0.5, 1.0 - age_days / 365)

    Args:
        collection: ChromaDB collection
        retrieval_history: Optional dict mapping item_id -> retrieval_count

    Returns:
        dict with update counts
    """
    items = _get_all_reasoningbank_items(collection, limit=_MAX_BATCH)
    updated = 0

    for item in items:
        meta = item.get("metadata", {})
        item_id = item["id"]
        base_conf = float(meta.get("confidence", 0.5))
        age = _item_age_days(item)

        # Calculate retrieval bonus
        retrieval_count = 0
        if retrieval_history:
            retrieval_count = retrieval_history.get(item_id, 0)

        retrieval_bonus = 1.0 + (0.1 * retrieval_count)
        age_decay = max(0.5, 1.0 - (age / 365.0))
        new_confidence = round(base_conf * retrieval_bonus * age_decay, 3)

        # Clamp
        new_confidence = max(_MIN_CONFIDENCE, min(1.0, new_confidence))

        if abs(new_confidence - base_conf) > 0.01:
            try:
                collection.update(
                    ids=[item_id],
                    metadatas=[{
                        **meta,
                        "confidence": new_confidence,
                        "last_confidence_update": datetime.now().isoformat(),
                    }],
                )
                updated += 1
            except Exception as e:
                logger.debug("Confidence update failed for %s: %s", item_id, e)

    if updated:
        logger.info("Updated confidence for %d items", updated)
    return {"updated": updated}


def consolidate_strategies(
    collection,
    llm_call_fn: Optional[Callable] = None,
    similarity_threshold: float = _DEFAULT_SIMILARITY,
    min_confidence: float = _MIN_CONFIDENCE,
    max_age_days: int = _MAX_AGE_DAYS,
    max_merges: int = 10,
) -> dict:
    """
    Run one full consolidation cycle.

    Order:
    1. Prune stale/low-confidence items
    2. Find duplicate candidates
    3. Merge pairs (top N by similarity)
    4. Update confidence scores

    Args:
        collection: ChromaDB collection
        llm_call_fn: Required for merging; if None, skips merge step
        similarity_threshold: Min similarity for dedup candidates
        min_confidence: Prune threshold
        max_age_days: Max age before low-confidence prune
        max_merges: Maximum pairs to merge per cycle

    Returns:
        dict with counts of all operations performed
    """
    result = {}

    # Step 1: Prune
    prune_result = prune_strategies(collection, min_confidence, max_age_days)
    result["prune"] = prune_result

    # Step 2: Find candidates
    candidates = find_candidates(collection, similarity_threshold)
    result["candidates_found"] = len(candidates)

    # Step 3: Merge (only if we have an LLM call function)
    merges_done = 0
    if llm_call_fn and candidates:
        for id_a, id_b, sim in candidates[:max_merges]:
            new_id = merge_pair(collection, id_a, id_b, sim, llm_call_fn)
            if new_id:
                merges_done += 1
    result["merges_done"] = merges_done

    # Step 4: Update confidence
    conf_result = update_confidence_scores(collection)
    result["confidence_updates"] = conf_result

    result["success"] = True
    logger.info(
        "Consolidation cycle complete: pruned=%d, candidates=%d, merges=%d, "
        "confidence_updates=%d",
        prune_result.get("pruned_total", 0),
        len(candidates),
        merges_done,
        conf_result.get("updated", 0),
    )
    return result
