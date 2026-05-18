"""
Multi-agent Tree-of-Thought Search (MaTTS) for strategy generation.

When uncertainty is high (LLM judge confidence < threshold or multiple valid
approaches exist), MaTTS generates multiple candidate strategies, evaluates
them, and selects the best approach.

Part of Phase 3 of the ReasoningBank implementation.
"""

import json
import logging
import time
import uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)

# --- Defaults ---
DEFAULT_NUM_CANDIDATES = 3
DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_MODE = "parallel"
MAX_RISK_LEVELS = 5  # very_low, low, medium, high, very_high
RISK_LEVELS = ["very_low", "low", "medium", "high", "very_high"]

# --- Sample candidates for mock mode ---
SAMPLE_CANDIDATES: list[dict[str, Any]] = [
    {
        "id": "candidate_a",
        "approach": "Decompose the problem into smaller sub-tasks and solve incrementally",
        "rationale": "Breaking down complexity reduces cognitive load and makes errors easier to isolate",
        "expected_difficulty": 0.4,
    },
    {
        "id": "candidate_b",
        "approach": "Search for existing solutions and adapt them to the current context",
        "rationale": "Leveraging prior work avoids reinventing the wheel and surfaces proven patterns",
        "expected_difficulty": 0.3,
    },
    {
        "id": "candidate_c",
        "approach": "Step back and analyze the root cause before attempting fixes",
        "rationale": "Understanding root causes prevents symptom-fixing and reduces trial-and-error cycles",
        "expected_difficulty": 0.5,
    },
]

SAMPLE_EVALUATIONS: list[dict[str, Any]] = [
    {"feasibility": 0.85, "risk": "low", "suggested_tools": ["read_file", "search_files"], "expected_turns": 3},
    {"feasibility": 0.70, "risk": "low", "suggested_tools": ["web_search", "web_extract"], "expected_turns": 4},
    {"feasibility": 0.60, "risk": "medium", "suggested_tools": ["read_file", "terminal", "execute_code"], "expected_turns": 5},
]

# --- LLM Prompts ---

MATTS_GENERATE_PROMPT = """You are a strategy generation system. Given a task description, generate {num_candidates} distinct candidate approaches.

Each candidate must be:
1. Concrete and actionable (not vague platitudes)
2. Sufficiently different from the other candidates
3. Appropriate for the described task

Output a JSON array of objects with fields:
- "approach": a concise description of the approach (1-2 sentences)
- "rationale": why this approach is likely to succeed
- "expected_difficulty": a float 0.0 (trivial) to 1.0 (extremely hard)

Task context:
{task_context}
"""

MATTS_EVALUATE_PROMPT = """You are a strategy evaluation system. Given a candidate approach and a task context, evaluate its feasibility.

CANDIDATE:
{approach}

Rationale: {rationale}
Expected Difficulty: {expected_difficulty}

Task Context:
{task_context}

Output JSON with fields:
- "feasibility": float 0.0 to 1.0 (how likely this approach will succeed)
- "risk": one of "very_low", "low", "medium", "high", "very_high"
- "suggested_tools": array of tool names that would help
- "expected_turns": integer estimate of how many turns needed
- "explanation": brief justification
"""

MATTS_SELECT_PROMPT = """You are a strategy selection system. Evaluate the following candidate approaches and select the best one.

Selection Strategy: {strategy}
- "max_feasibility": pick the one with highest feasibility score
- "min_risk": pick the one with lowest risk level
- "balanced": balance feasibility vs risk (prefer high feasibility with manageable risk)
- "consensus": pick the most similar to the average of all candidates

Candidates (with evaluations):
{candidates_with_eval}

Output JSON with fields:
- "selected_id": the ID of the best candidate
- "explanation": why this candidate was selected
- "runner_up_id": the second-best candidate
"""


def should_trigger_matts(
    messages: list[dict[str, Any]],
    judgment: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> bool:
    """
    Decide whether to run MaTTS based on session context.

    Triggers when:
    a) LLM judge reports low confidence (< threshold)
    b) Session has 3+ tool-calling turns without clear resolution
    c) Multiple distinct tool types were used (exploration/frustration)
    d) OR config has "force": true

    Args:
        messages: Session messages.
        judgment: LLM judge output dict (may have "confidence" key).
        config: MaTTS config dict with keys like "enabled", "force",
                "min_confidence_threshold".

    Returns:
        True if MaTTS should run.
    """
    config = config or {}
    if not config.get("enabled", True):
        return False
    if config.get("force", False):
        return True

    # a) Low confidence from judge
    if judgment:
        confidence = judgment.get("confidence", 1.0)
        threshold = config.get("min_confidence_threshold", DEFAULT_MIN_CONFIDENCE)
        if confidence is not None and confidence < threshold:
            logger.debug(
                "MaTTS trigger: low confidence (%.2f < %.2f)",
                confidence,
                threshold,
            )
            return True

    # b) 3+ tool turns without resolution
    tool_turns = sum(1 for msg in messages if msg.get("tool_calls"))
    if tool_turns >= 3:
        # Check if there's a final resolution in the last assistant message
        last_assistant = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                last_assistant = (msg.get("content") or "")
                break
        is_unresolved = bool(last_assistant and len(last_assistant) < 50)
        if is_unresolved:
            logger.debug(
                "MaTTS trigger: %d tool turns without clear resolution",
                tool_turns,
            )
            return True

    # c) Multiple distinct tool types
    tool_types: set[str] = set()
    for msg in messages:
        calls = msg.get("tool_calls") or []
        for call in calls:
            if isinstance(call, dict):
                name = call.get("function", {}).get("name", "") if "function" in call else call.get("name", "")
                if name:
                    tool_types.add(name)
    if len(tool_types) >= 4:
        logger.debug(
            "MaTTS trigger: %d distinct tool types used (exploration pattern)",
            len(tool_types),
        )
        return True

    return False


def generate_candidates(
    task_context: str,
    num_candidates: int = DEFAULT_NUM_CANDIDATES,
    llm_call_fn: Callable | None = None,
) -> list[dict[str, Any]]:
    """
    Generate N candidate approaches for a given task.

    Args:
        task_context: Description of the task to solve.
        num_candidates: Number of candidates to generate (default: 3).
        llm_call_fn: Optional LLM function (same pattern as llm_judge.py).
                     If None, returns sample candidates.

    Returns:
        List of candidate dicts:
            {id: str, approach: str, rationale: str,
             expected_difficulty: float}
    """
    if llm_call_fn:
        prompt = MATTS_GENERATE_PROMPT.format(
            num_candidates=num_candidates,
            task_context=task_context,
        )
        try:
            raw = llm_call_fn(
                system_prompt="You generate distinct strategy candidates.",
                user_prompt=prompt,
                response_type="json_object",
            )
            if isinstance(raw, str):
                candidates = json.loads(raw)
            elif isinstance(raw, dict):
                candidates = raw.get("candidates", raw)
            else:
                candidates = raw

            if isinstance(candidates, list) and len(candidates) > 0:
                for c in candidates:
                    if "id" not in c:
                        c["id"] = f"candidate_{uuid.uuid4().hex[:8]}"
                return candidates[:num_candidates]
        except Exception as e:
            logger.warning("LLM candidate generation failed: %s", e)
            # Fall through to sample candidates

    # Return sample candidates (deterministic, with different IDs)
    result: list[dict[str, Any]] = []
    for i, sample in enumerate(SAMPLE_CANDIDATES[:num_candidates]):
        candidate = dict(sample)
        candidate["id"] = f"candidate_{['a', 'b', 'c', 'd', 'e'][i]}"
        result.append(candidate)

    logger.debug("Generated %d sample candidates (mock mode)", len(result))
    return result


def evaluate_candidate(
    candidate: dict[str, Any],
    context: str = "",
    llm_call_fn: Callable | None = None,
) -> dict[str, Any]:
    """
    Evaluate a single candidate approach.

    Args:
        candidate: Dict with "id", "approach", "rationale",
                   "expected_difficulty".
        context: Additional task context.
        llm_call_fn: Optional LLM function.

    Returns:
        Evaluation dict:
            {id: str, feasibility: float, risk: str,
             suggested_tools: list[str], expected_turns: int}
    """
    candidate_id = candidate.get("id", "unknown")

    if llm_call_fn:
        prompt = MATTS_EVALUATE_PROMPT.format(
            approach=candidate.get("approach", ""),
            rationale=candidate.get("rationale", ""),
            expected_difficulty=candidate.get("expected_difficulty", 0.5),
            task_context=context or "General coding task",
        )
        try:
            raw = llm_call_fn(
                system_prompt="You evaluate strategy feasibility.",
                user_prompt=prompt,
                response_type="json_object",
            )
            if isinstance(raw, str):
                parsed = json.loads(raw)
            elif isinstance(raw, dict):
                parsed = raw
            else:
                parsed = raw

            parsed["id"] = candidate_id
            return parsed
        except Exception as e:
            logger.warning("LLM evaluation failed for %s: %s", candidate_id, e)
            # Fall through to sample evaluation

    # Deterministic sample evaluation
    idx = ord(candidate_id[-1]) - ord("a") if candidate_id[-1] in "abcde" else 0
    idx = max(0, min(idx, len(SAMPLE_EVALUATIONS) - 1))
    eval_sample = dict(SAMPLE_EVALUATIONS[idx])
    eval_sample["id"] = candidate_id
    return eval_sample


def select_best_strategy(
    candidates: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    strategy: str = "max_feasibility",
    llm_call_fn: Callable | None = None,
    context: str = "",
) -> dict[str, Any]:
    """
    Select the best candidate based on evaluation scores.

    Args:
        candidates: List of candidate dicts.
        evaluations: List of evaluation dicts (same order as candidates).
        strategy: Selection method ("max_feasibility", "min_risk",
                  "balanced", "consensus").
        llm_call_fn: Optional LLM function for LLM-based selection.
        context: Task context for LLM-based selection.

    Returns:
        Selected candidate dict with selection metadata.
    """
    if not candidates or not evaluations:
        return {}

    # Build lookup: id -> evaluation
    eval_by_id: dict[str, dict[str, Any]] = {}
    for ev in evaluations:
        eval_by_id[ev.get("id", "")] = ev

    if llm_call_fn and strategy in ("balanced", "consensus"):
        # LLM-based selection for complex strategies
        candidates_with_eval = []
        for cand in candidates:
            cid = cand.get("id", "")
            ev = eval_by_id.get(cid, {})
            candidates_with_eval.append({
                "id": cid,
                "approach": cand.get("approach", ""),
                "feasibility": ev.get("feasibility", 0.5),
                "risk": ev.get("risk", "medium"),
            })

        prompt = MATTS_SELECT_PROMPT.format(
            strategy=strategy,
            candidates_with_eval=json.dumps(candidates_with_eval, indent=2),
        )
        try:
            raw = llm_call_fn(
                system_prompt="You select the best strategy.",
                user_prompt=prompt,
                response_type="json_object",
            )
            if isinstance(raw, str):
                selection = json.loads(raw)
            else:
                selection = raw

            selected_id = selection.get("selected_id", "")
            for cand in candidates:
                if cand.get("id") == selected_id:
                    result = dict(cand)
                    result["selection_strategy"] = strategy
                    result["selection_explanation"] = selection.get("explanation", "")
                    result["feasibility"] = eval_by_id.get(selected_id, {}).get("feasibility", 0.0)
                    result["risk"] = eval_by_id.get(selected_id, {}).get("risk", "unknown")
                    return result
        except Exception as e:
            logger.warning("LLM selection failed: %s", e)
            # Fall through to heuristic

    # Heuristic selection
    best_idx = 0
    best_score = -1.0
    risk_order = {r: i for i, r in enumerate(RISK_LEVELS)}

    for i, cand in enumerate(candidates):
        cid = cand.get("id", "")
        ev = eval_by_id.get(cid, {})
        feasibility = ev.get("feasibility", 0.5)
        risk = ev.get("risk", "medium")
        risk_level = risk_order.get(risk, 2)  # default "medium"

        if strategy == "max_feasibility":
            score = feasibility
        elif strategy == "min_risk":
            score = MAX_RISK_LEVELS - risk_level
        elif strategy == "balanced":
            score = feasibility * 0.6 + (MAX_RISK_LEVELS - risk_level) * 0.4 / MAX_RISK_LEVELS
        else:  # default: max_feasibility
            score = feasibility

        if score > best_score:
            best_score = score
            best_idx = i

    selected = dict(candidates[best_idx])
    selected_id = selected.get("id", "")
    ev_selected = eval_by_id.get(selected_id, {})
    selected["selection_strategy"] = strategy
    selected["selection_explanation"] = f"Best score ({best_score:.2f}) using {strategy} strategy"
    selected["feasibility"] = ev_selected.get("feasibility", 0.0)
    selected["risk"] = ev_selected.get("risk", "unknown")
    return selected


def run_matts(
    task_context: str,
    config: dict[str, Any] | None = None,
    llm_call_fn: Callable | None = None,
) -> dict[str, Any]:
    """
    Full MaTTS pipeline: generate -> evaluate -> select -> return.

    Args:
        task_context: Description of the task to solve.
        config: MaTTS config with keys:
            - "num_candidates" (default: 3)
            - "mode" (default: "parallel")
            - "selection_strategy" (default: "balanced")
        llm_call_fn: Optional LLM function.

    Returns:
        Dict:
            {selected: dict, candidates: list, evaluations: list,
             mode: str, meta: {took_ms: int, num_candidates: int}}
    """
    config = config or {}
    num_candidates = config.get("num_candidates", DEFAULT_NUM_CANDIDATES)
    mode = config.get("mode", DEFAULT_MODE)
    selection_strategy = config.get("selection_strategy", "balanced")

    start = time.monotonic()

    # Generate candidates
    candidates = generate_candidates(
        task_context=task_context,
        num_candidates=num_candidates,
        llm_call_fn=llm_call_fn if mode == "parallel" else None,  # only parallel uses LLM here
    )
    if not candidates:
        logger.warning("MaTTS: no candidates generated")
        return {
            "selected": {},
            "candidates": [],
            "evaluations": [],
            "mode": mode,
            "meta": {"took_ms": 0, "num_candidates": 0, "error": "No candidates generated"},
        }

    # Evaluate each candidate
    evaluations: list[dict[str, Any]] = []
    for cand in candidates:
        ev = evaluate_candidate(
            candidate=cand,
            context=task_context,
            llm_call_fn=llm_call_fn,
        )
        evaluations.append(ev)

    # Select best
    selected = select_best_strategy(
        candidates=candidates,
        evaluations=evaluations,
        strategy=selection_strategy,
        llm_call_fn=llm_call_fn if selection_strategy in ("balanced", "consensus") else None,
        context=task_context,
    )

    took_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "MaTTS completed: %d candidates, %s mode, selected %s (%dms)",
        len(candidates),
        mode,
        selected.get("id", "none"),
        took_ms,
    )

    return {
        "selected": selected,
        "candidates": candidates,
        "evaluations": evaluations,
        "mode": mode,
        "meta": {
            "took_ms": took_ms,
            "num_candidates": len(candidates),
        },
    }
