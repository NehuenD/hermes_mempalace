"""
Formal task/trajectory boundary detection for session trajectories.

Detects when a "task" starts and ends within a conversation. Hermes has no
formal task model — a session can contain multiple user requests. This module
segments sessions into task boundaries using heuristics.

Part of Phase 3 of the ReasoningBank implementation.
"""

import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# --- Tunable thresholds ---

# Maximum consecutive user messages without tool calls before splitting
TOOL_GAP_THRESHOLD = 3

# Minimum number of messages to form a task segment
MIN_TASK_LENGTH = 2

# Jaccard similarity threshold for merging adjacent tasks
SIMILARITY_THRESHOLD = 0.7

# Intent shift marker phrases (lowercase)
INTENT_SHIFT_MARKERS: list[str] = [
    "now let",
    "next up",
    "switching to",
    "moving on",
    "while you're at it",
    "also check",
    "can you also",
    "another thing",
    "one more",
    "different topic",
    "new task",
    "separately",
    "on a different note",
    "change of plans",
    "let's try something else",
]


def _tokenize(text: str) -> set[str]:
    """Tokenize text into a set of lowercase alphanumeric words."""
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _has_intent_shift(message_content: str) -> bool:
    """Check if a user message contains intent shift markers."""
    content_lower = message_content.lower()
    for marker in INTENT_SHIFT_MARKERS:
        if marker in content_lower:
            return True
    return False


def detect_task_boundaries(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Detect task boundaries within a list of conversation messages.

    Detection strategies (in priority order):
    1. **Tool-call clusters** — gaps of >TOOL_GAP_THRESHOLD consecutive user
       messages without tool calls = new task.
    2. **Intent shift markers** — phrases like "now let's", "next up", etc.
    3. **Content segmentation** — distinct topic clusters via keyword overlap.

    Args:
        messages: List of message dicts with 'role', 'content', and optionally
                  'tool_calls' keys.

    Returns:
        List of task segment dicts:
            {start_idx, end_idx, intent: str, type: str}
        Returns empty list if no clear boundaries found (single-task session).
    """
    if not messages or len(messages) < MIN_TASK_LENGTH:
        return []

    segments: list[dict[str, Any]] = []
    current_start = 0
    consecutive_user_no_tool = 0

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "") or ""
        has_tool = bool(msg.get("tool_calls"))

        if role == "user":
            if has_tool:
                # This shouldn't normally happen (users don't have tool_calls),
                # but handle gracefully
                consecutive_user_no_tool = 0
                continue

            consecutive_user_no_tool += 1

            # Strategy 1: Tool-call gap detection
            if consecutive_user_no_tool > TOOL_GAP_THRESHOLD:
                segment_end = i - 1
                if segment_end - current_start >= MIN_TASK_LENGTH:
                    segments.append({
                        "start_idx": current_start,
                        "end_idx": segment_end,
                        "intent": _infer_intent(
                            messages[current_start : segment_end + 1]
                        ),
                        "type": "tool_gap",
                    })
                    current_start = i
                consecutive_user_no_tool = 1  # reset, counting this msg

            # Strategy 2: Intent shift markers
            elif _has_intent_shift(content):
                if i - current_start >= MIN_TASK_LENGTH:
                    segments.append({
                        "start_idx": current_start,
                        "end_idx": i - 1,
                        "intent": _infer_intent(
                            messages[current_start:i]
                        ),
                        "type": "intent_shift",
                    })
                    current_start = i
                    consecutive_user_no_tool = 1

        elif role in ("assistant", "tool"):
            # Reset user-no-tool counter when we see assistant/tool messages
            consecutive_user_no_tool = 0

    # Close the final segment
    if len(messages) - 1 - current_start >= MIN_TASK_LENGTH:
        segments.append({
            "start_idx": current_start,
            "end_idx": len(messages) - 1,
            "intent": _infer_intent(messages[current_start:]),
            "type": "final",
        })

    # Strategy 3: Content-based segmentation
    segments = _content_segmentation(messages, segments)

    # Merge adjacent similar tasks
    if len(segments) > 1:
        segments = _merge_similar_tasks(segments, messages)

    logger.debug(
        "detect_task_boundaries: %d messages → %d segments",
        len(messages),
        len(segments),
    )
    return segments


def _infer_intent(messages: list[dict[str, Any]]) -> str:
    """Infer the task intent from a segment of messages.

    Uses the first user message content as a rough intent descriptor.
    """
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if content:
                # Take first sentence or first 100 chars
                content = content.strip()[:100]
                # Remove trailing punctuation
                content = content.rstrip(".,!?;:")
                return content
    return "unknown"


def _content_segmentation(
    messages: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply content-based keyword segmentation to refine segments.

    Looks for keyword topic shifts within large segments and splits them.
    """
    if not segments:
        return segments

    # Only segment if segments are large (10+ messages)
    result: list[dict[str, Any]] = []
    for seg in segments:
        seg_len = seg["end_idx"] - seg["start_idx"] + 1
        if seg_len < 10:
            result.append(seg)
            continue

        # Try to find content shifts within this segment
        seg_messages = messages[seg["start_idx"] : seg["end_idx"] + 1]
        splits = _find_content_shifts(seg_messages)

        if not splits:
            result.append(seg)
            continue

        # Create sub-segments at split points
        prev = 0
        for split_idx in splits:
            if split_idx - prev >= MIN_TASK_LENGTH:
                result.append({
                    "start_idx": seg["start_idx"] + prev,
                    "end_idx": seg["start_idx"] + split_idx - 1,
                    "intent": _infer_intent(
                        seg_messages[prev:split_idx]
                    ),
                    "type": "content_shift",
                })
                prev = split_idx
            else:
                prev = split_idx  # skip too-small segments

        # Final sub-segment
        if len(seg_messages) - prev >= MIN_TASK_LENGTH:
            result.append({
                "start_idx": seg["start_idx"] + prev,
                "end_idx": seg["end_idx"],
                "intent": _infer_intent(seg_messages[prev:]),
                "type": "content_shift",
            })

    return result if result else segments


def _find_content_shifts(messages: list[dict[str, Any]]) -> list[int]:
    """Find content shift indices within a list of messages.

    Uses keyword overlap between consecutive user messages.
    Returns indices where a shift occurs.
    """
    user_msgs: list[tuple[int, set[str]]] = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "user":
            tokens = _tokenize(msg.get("content", "") or "")
            user_msgs.append((i, tokens))

    shifts: list[int] = []
    for j in range(1, len(user_msgs)):
        prev_tokens = user_msgs[j - 1][1]
        curr_tokens = user_msgs[j][1]
        sim = _jaccard_similarity(prev_tokens, curr_tokens)
        if sim < 0.3 and len(curr_tokens) > 3:
            # Significant topic shift
            shifts.append(user_msgs[j][0])
            logger.debug(
                "Content shift at message %d (similarity=%.2f)",
                user_msgs[j][0],
                sim,
            )

    return shifts


def _merge_similar_tasks(
    segments: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge adjacent task segments with similar intents."""
    if len(segments) < 2:
        return segments

    merged: list[dict[str, Any]] = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        # Compare intents via token overlap
        prev_intent_tokens = _tokenize(prev.get("intent", ""))
        curr_intent_tokens = _tokenize(seg.get("intent", ""))
        sim = _jaccard_similarity(prev_intent_tokens, curr_intent_tokens)

        if sim >= SIMILARITY_THRESHOLD:
            # Merge: extend the previous segment
            merged[-1] = {
                "start_idx": prev["start_idx"],
                "end_idx": seg["end_idx"],
                "intent": prev["intent"],
                "type": f"merged_{prev['type']}_{seg['type']}",
            }
        else:
            merged.append(seg)

    return merged


def get_current_task(
    messages: list[dict[str, Any]],
    current_idx: int = -1,
) -> dict[str, Any]:
    """
    Get the task segment containing a specific message index.

    Args:
        messages: Full conversation messages.
        current_idx: Message index (default: -1 = last message).

    Returns:
        Task dict with:
            {task_id: str, intent: str, start_idx, end_idx: int | None,
             duration: int}
        If no boundaries detected, returns a single task covering all messages.
    """
    if not messages:
        return {
            "task_id": str(uuid.uuid4()),
            "intent": "empty session",
            "start_idx": 0,
            "end_idx": None,
            "duration": 0,
        }

    if current_idx < 0:
        current_idx = len(messages) - 1

    boundaries = detect_task_boundaries(messages)

    if not boundaries:
        return {
            "task_id": str(uuid.uuid4()),
            "intent": _infer_intent(messages),
            "start_idx": 0,
            "end_idx": len(messages) - 1,
            "duration": len(messages),
        }

    for seg in boundaries:
        if seg["start_idx"] <= current_idx <= seg["end_idx"]:
            return {
                "task_id": str(uuid.uuid4()),
                "intent": seg["intent"],
                "start_idx": seg["start_idx"],
                "end_idx": seg["end_idx"],
                "duration": seg["end_idx"] - seg["start_idx"] + 1,
            }

    # Fallback: last segment
    last = boundaries[-1]
    return {
        "task_id": str(uuid.uuid4()),
        "intent": last["intent"],
        "start_idx": last["start_idx"],
        "end_idx": last["end_idx"],
        "duration": last["end_idx"] - last["start_idx"] + 1,
    }


def summarize_task(
    messages: list[dict[str, Any]],
    task_range: dict[str, Any],
    max_turns: int = 5,
) -> str:
    """
    Condense a task segment into a concise summary.

    Uses the first user message and last assistant/tool response. Mentions
    key tools used and the apparent outcome.

    Args:
        messages: Full conversation messages.
        task_range: Task dict from get_current_task or detect_task_boundaries.
        max_turns: Maximum number of turns to include in summary.

    Returns:
        Concise task summary string.
    """
    start = task_range.get("start_idx", 0)
    end = task_range.get("end_idx", len(messages) - 1)
    if end is None:
        end = len(messages) - 1

    segment = messages[start : end + 1]
    if not segment:
        return ""

    # First user message
    first_user: str | None = None
    for msg in segment:
        if msg.get("role") == "user":
            first_user = (msg.get("content") or "")[:200]
            break

    # Last assistant response
    last_assistant: str | None = None
    for msg in reversed(segment):
        if msg.get("role") == "assistant":
            last_assistant = (msg.get("content") or "")[:200]
            break

    # Count tool types used
    tool_types: set[str] = set()
    for msg in segment:
        calls = msg.get("tool_calls") or []
        for call in calls:
            name = call.get("function", {}).get("name", "") if isinstance(call, dict) else ""
            if name:
                tool_types.add(name)

    # Count user turns
    user_turns = sum(1 for msg in segment if msg.get("role") == "user")

    summary_parts: list[str] = []
    if first_user:
        summary_parts.append(f"Request: {first_user}")
    if tool_types:
        summary_parts.append(f"Tools: {', '.join(sorted(tool_types)[:5])}")
    if last_assistant:
        summary_parts.append(f"Outcome: {last_assistant}")
    summary_parts.append(f"Turns: {user_turns}")

    return " | ".join(summary_parts)


def merge_tasks(
    tasks: list[dict[str, Any]],
    similarity_threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """
    Merge adjacent tasks whose intents overlap.

    Uses Jaccard similarity on intent description tokens.

    Args:
        tasks: List of task dicts from detect_task_boundaries.
        similarity_threshold: Jaccard similarity threshold for merging
                              (default: 0.7).

    Returns:
        Merged list of task dicts.
    """
    if not tasks or len(tasks) < 2:
        return tasks

    merged: list[dict[str, Any]] = [tasks[0]]
    for task in tasks[1:]:
        prev = merged[-1]
        prev_tokens = _tokenize(prev.get("intent", ""))
        curr_tokens = _tokenize(task.get("intent", ""))

        if _jaccard_similarity(prev_tokens, curr_tokens) >= similarity_threshold:
            merged[-1] = {
                "start_idx": prev["start_idx"],
                "end_idx": task["end_idx"],
                "intent": prev["intent"],
                "type": f"merged_{prev['type']}_{task['type']}",
            }
        else:
            merged.append(task)

    return merged
