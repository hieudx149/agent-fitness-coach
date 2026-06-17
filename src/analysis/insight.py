"""Build a markdown summary of computed workout stats.

The brief is explicit: do NOT dump raw JSON into the prompt. We render
structured stats as a markdown table that the Coach Agent uses directly
when synthesising its answer — there is no separate LLM call here.
"""
from src.analysis.models import WorkoutEntry
from src.analysis.stats import (
    compute_frequency,
    compute_muscle_group_balance,
    compute_per_exercise,
)


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
