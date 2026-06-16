"""analyze_history() — public entry point for the Coach Agent (and direct callers).

This is the boundary between the agent and the analysis module. The agent
only knows about this function; everything below (stats engine, prompt
construction) is an implementation detail it should never touch.

`user_id` is used only for logging/audit. The actual training data must be
passed in via `history` — there is no server-side lookup. This keeps the
data-isolation invariant trivially auditable: user A's data physically
cannot reach user B's analysis path.
"""
import logging
from typing import Any

from src.analysis.insight import generate_insight
from src.analysis.models import WorkoutEntry

logger = logging.getLogger(__name__)


async def analyze_history(
    user_id: str,
    question: str,
    history: list[dict] | list[WorkoutEntry],
) -> dict[str, Any]:
    """Analyze a user's workout history and answer a natural-language question.

    Args:
        user_id: identifier for logging/audit only — NOT used to fetch data
        question: natural-language question (e.g. "what's my bench press trend?")
        history: list of workout entries (dict or WorkoutEntry); validated here

    Returns:
        {
            "insight": str,           # markdown answer from the LLM
            "stats_summary": str,     # the markdown summary that was sent to the LLM
            "insufficient": bool,     # True if history was empty/unusable
            "user_id": str,
            "usage": {...},           # token counts (present when LLM was called)
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

    return await generate_insight(question, typed_history, user_id=user_id)
