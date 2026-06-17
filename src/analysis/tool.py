"""analyze_history() — public entry point for the Coach Agent (and direct callers).

This is the boundary between the agent and the analysis module. The agent
only knows about this function; everything below (stats engine, summary
construction) is an implementation detail it should never touch.

`user_id` is used only for logging/audit. The actual training data must be
passed in via `history` — there is no server-side lookup. This keeps the
data-isolation invariant trivially auditable: user A's data physically
cannot reach user B's analysis path.

This tool runs NO LLM — only deterministic Python aggregation. The Coach
Agent uses the returned summary as context when synthesising its answer,
which saves one LLM round-trip per analysis question and keeps the cost
attribution clean (one LLM call per `/chat` round, period).
"""
import logging
from typing import Any

from src.analysis.insight import build_summary
from src.analysis.models import WorkoutEntry
from src.analysis.stats import detect_flags, detect_missing_compounds

logger = logging.getLogger(__name__)


async def analyze_history(
    user_id: str,
    question: str,
    history: list[dict] | list[WorkoutEntry],
    name: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Compute deterministic statistics over a user's workout history.

    Args:
        user_id: identifier for logging/audit only — NOT used to fetch data
        question: natural-language question (logged for audit; the summary
                  itself is question-agnostic so the agent picks what to use)
        history: list of workout entries (dict or WorkoutEntry); validated here
        name: athlete display name, rendered in the summary header for context
        profile: free-text athlete profile (level, bodyweight, style) for context

    Returns:
        {
            "stats_summary": str,    # markdown table of computed stats
            "data_points": list,     # citable {ref, category, label, detail} facts
            "flags": list,           # detected {kind, severity, message} red flags
            "missing_compounds": list,  # expected compounds absent from history
            "insufficient": bool,    # True when history is empty / all malformed
            "user_id": str,
            "n_workouts": int,       # raw count, for quick agent gating
        }
    """
    typed_history: list[WorkoutEntry] = []
    for item in history:
        if isinstance(item, WorkoutEntry):
            typed_history.append(item)
            continue
        try:
            typed_history.append(WorkoutEntry.model_validate(item))
        except Exception as exc:
            logger.warning("Skipping malformed workout entry: %s — %s", item, exc)

    logger.info(
        "analyze_history: user=%s n_entries=%d question=%r",
        user_id,
        len(typed_history),
        question[:80],
    )

    if not typed_history:
        return {
            "stats_summary": "",
            "data_points": [],
            "flags": [],
            "missing_compounds": [],
            "insufficient": True,
            "user_id": user_id,
            "n_workouts": 0,
        }

    summary, data_points = build_summary(typed_history, name=name, profile=profile)
    flags = [
        {"kind": f.kind, "severity": f.severity, "message": f.message}
        for f in detect_flags(typed_history)
    ]
    return {
        "stats_summary": summary,
        "data_points": data_points,
        "flags": flags,
        "missing_compounds": detect_missing_compounds(typed_history),
        "insufficient": False,
        "user_id": user_id,
        "n_workouts": len(typed_history),
    }
