"""Build a markdown summary from computed stats, then ask the LLM the
user's question with that summary as context.

The brief is explicit: do NOT dump raw JSON into the prompt. So we
render structured stats as a markdown table — the LLM gets compact,
auditable data and references specific numbers in the answer.
"""
import logging
from typing import Any

from src.analysis.models import WorkoutEntry
from src.analysis.stats import (
    compute_frequency,
    compute_muscle_group_balance,
    compute_per_exercise,
)
from src.config import get_settings
from src.llm.openai_client import get_openai_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a fitness data analyst for a coaching platform. Answer the user's question using ONLY the workout summary provided.

Rules:
1. Reference SPECIFIC numbers, dates, and exercise names from the summary.
2. If the summary doesn't contain enough data to answer, say so explicitly — never invent stats.
3. Frame insights in coaching language — clear, supportive, but honest about gaps.
4. When suggesting changes, base them on the trends shown.
5. If the user asks about a muscle group with little data, name what IS present and what's missing."""


def build_summary(history: list[WorkoutEntry]) -> str:
    if not history:
        return "No workout data provided."

    per_ex = compute_per_exercise(history)
    by_group = compute_muscle_group_balance(history)
    freq = compute_frequency(history)

    lines: list[str] = []

    lines.append("## Time range & frequency")
    lines.append(f"- Span: {freq.first_date} to {freq.last_date} ({freq.span_days} days)")
    lines.append(f"- Total training days: {freq.total_sessions}")
    lines.append(f"- Sessions per week: {freq.sessions_per_week}")
    lines.append(f"- Longest gap: {freq.longest_gap_days} days")

    lines.append("\n## Per-exercise summary")
    lines.append(
        "| Exercise | Sessions | Sets | Max kg | e1RM kg | Volume kg | Trend kg/wk | First | Last |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    sorted_ex = sorted(per_ex.values(), key=lambda s: -s.sessions)
    for s in sorted_ex:
        trend = (
            f"{s.weight_trend_kg_per_week:+.2f}"
            if s.weight_trend_kg_per_week is not None
            else "—"
        )
        lines.append(
            f"| {s.exercise} | {s.sessions} | {s.total_sets} | {s.max_weight_kg} | "
            f"{s.e1rm_kg} | {s.total_volume_kg} | {trend} | {s.first_date} | {s.last_date} |"
        )

    lines.append("\n## Muscle group balance (primary attribution)")
    lines.append("| Group | Sessions | Sets | Volume kg | Last trained |")
    lines.append("|---|---|---|---|---|")
    sorted_groups = sorted(by_group.values(), key=lambda s: -s.total_volume_kg)
    for g in sorted_groups:
        lines.append(
            f"| {g.group} | {g.sessions} | {g.total_sets} | {g.total_volume_kg} | {g.last_trained} |"
        )

    return "\n".join(lines)


async def generate_insight(
    question: str,
    history: list[WorkoutEntry],
    user_id: str,
) -> dict[str, Any]:
    if not history:
        return {
            "insight": (
                "No workout data was provided yet — there's nothing to analyze. "
                "Once you log some training sessions I can help spot trends and "
                "suggest adjustments."
            ),
            "stats_summary": "",
            "insufficient": True,
            "user_id": user_id,
        }

    summary = build_summary(history)
    settings = get_settings()
    client = get_openai_client()

    user_message = f"Workout summary:\n\n{summary}\n\nQuestion: {question}"

    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        max_tokens=600,
    )
    answer = (response.choices[0].message.content or "").strip()

    return {
        "insight": answer,
        "stats_summary": summary,
        "insufficient": False,
        "user_id": user_id,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        },
    }
