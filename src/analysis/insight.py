"""Build a markdown summary of computed workout stats + citable data points.

The brief is explicit: do NOT dump raw JSON into the prompt. We render
structured stats as a markdown table that the Coach Agent uses directly
when synthesising its answer — there is no separate LLM call here.

Alongside the markdown we emit a parallel list of `data_points`. Each is a
citable stat carrying a stable `[Dn]` reference id that is ALSO embedded in
the markdown the agent reads. This lets the agent cite a specific number,
date, or trend the same way it cites a knowledge-base chunk with `[n]` — and
the UI renders these as reference cards so a data-backed claim is traceable
to the exact computed figure behind it.
"""
from src.analysis.models import WorkoutEntry
from src.analysis.stats import (
    compute_frequency,
    compute_muscle_group_balance,
    compute_per_exercise,
    detect_flags,
    detect_missing_compounds,
)


def _fmt_trend(value: float | None) -> str:
    return f"{value:+.2f} kg/wk" if value is not None else "trend n/a (<2 sessions)"


def build_summary(
    history: list[WorkoutEntry],
    name: str | None = None,
    profile: str | None = None,
) -> tuple[str, list[dict]]:
    """Render computed stats as markdown and a parallel list of data points.

    Args:
        history: the user's workout entries.
        name: athlete display name (rendered as context, not a citable stat).
        profile: free-text athlete profile (level, bodyweight, training style).

    Returns:
        (markdown_summary, data_points) where each data point is
        {ref, category, label, detail}. The same `[ref]` tag is embedded in
        the markdown so the agent cites the exact figure it used.
    """
    if not history:
        return "No workout data provided.", []

    per_ex = compute_per_exercise(history)
    by_group = compute_muscle_group_balance(history)
    freq = compute_frequency(history)
    flags = detect_flags(history)
    missing = detect_missing_compounds(history)

    data_points: list[dict] = []

    def _ref(category: str, label: str, detail: str) -> str:
        ref = f"D{len(data_points) + 1}"
        data_points.append(
            {"ref": ref, "category": category, "label": label, "detail": detail}
        )
        return ref

    lines: list[str] = []

    # ── Athlete (context, not a citable stat) ──────────────────
    if name or profile:
        lines.append("## Athlete")
        if name:
            lines.append(f"- Name: {name}")
        if profile:
            lines.append(f"- Profile: {profile}")
        lines.append("")

    # ── Frequency ──────────────────────────────────────────────
    freq_detail = (
        f"{freq.total_sessions} training days over {freq.span_days} days "
        f"({freq.first_date} → {freq.last_date}) · "
        f"{freq.sessions_per_week} sessions/week · "
        f"longest gap {freq.longest_gap_days} days"
    )
    freq_ref = _ref("Frequency", "Training frequency", freq_detail)
    lines.append(f"## Time range & frequency [{freq_ref}]")
    lines.append(f"- Span: {freq.first_date} to {freq.last_date} ({freq.span_days} days)")
    lines.append(f"- Total training days: {freq.total_sessions}")
    lines.append(f"- Sessions per week: {freq.sessions_per_week}")
    lines.append(f"- Longest gap: {freq.longest_gap_days} days")

    # ── Per-exercise ───────────────────────────────────────────
    lines.append("\n## Per-exercise summary")
    lines.append(
        "| Ref | Exercise | Sessions | Sets | Max kg | e1RM kg | Volume kg | Trend kg/wk | First | Last |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    sorted_ex = sorted(per_ex.values(), key=lambda s: -s.sessions)
    for s in sorted_ex:
        trend = (
            f"{s.weight_trend_kg_per_week:+.2f}"
            if s.weight_trend_kg_per_week is not None
            else "—"
        )
        detail = (
            f"{s.sessions} sessions · {s.total_sets} sets · max {s.max_weight_kg} kg · "
            f"e1RM {s.e1rm_kg} kg · volume {s.total_volume_kg} kg · {_fmt_trend(s.weight_trend_kg_per_week)} · "
            f"{s.first_date} → {s.last_date}"
        )
        ref = _ref("Exercise", s.exercise, detail)
        lines.append(
            f"| [{ref}] | {s.exercise} | {s.sessions} | {s.total_sets} | {s.max_weight_kg} | "
            f"{s.e1rm_kg} | {s.total_volume_kg} | {trend} | {s.first_date} | {s.last_date} |"
        )

    # ── Muscle group balance ───────────────────────────────────
    lines.append("\n## Muscle group balance (primary attribution)")
    lines.append("| Ref | Group | Sessions | Sets | Volume kg | Last trained |")
    lines.append("|---|---|---|---|---|---|")
    sorted_groups = sorted(by_group.values(), key=lambda s: -s.total_volume_kg)
    for g in sorted_groups:
        detail = (
            f"{g.sessions} sessions · {g.total_sets} sets · volume {g.total_volume_kg} kg · "
            f"last trained {g.last_trained}"
        )
        ref = _ref("Muscle group", g.group, detail)
        lines.append(
            f"| [{ref}] | {g.group} | {g.sessions} | {g.total_sets} | {g.total_volume_kg} | {g.last_trained} |"
        )

    # ── Programming flags (heuristic detection) ────────────────
    lines.append("\n## Programming flags")
    if not flags and not missing:
        lines.append("- None detected — training looks balanced and consistent.")
    else:
        for f in flags:
            icon = "⚠️" if f.severity == "warning" else "ℹ️"
            ref = _ref("Flag", f"{f.kind} ({f.severity})", f.message)
            lines.append(f"- {icon} [{ref}] {f.kind}: {f.message}")
        for m in missing:
            detail = f"{m['exercise']} ({m['pattern']}) not present in history"
            ref = _ref("Flag", f"missing compound: {m['exercise']}", detail)
            lines.append(f"- ⚠️ [{ref}] missing: {detail}")

    return "\n".join(lines), data_points
