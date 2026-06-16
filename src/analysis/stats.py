"""Deterministic statistics over workout history.

NO LLM in this file. Everything here is pure Python — testable in
milliseconds and 100% reproducible. The LLM only sees the markdown
summary built from these stats, never the raw JSON.

Key computations:
  - Per-exercise: sessions, sets, reps, total volume kg, max weight,
    e1RM (Epley), date range, weight trend (kg/week via least-squares).
  - Muscle group balance: primary-group attribution for "chest vs back"
    style questions.
  - Frequency: total unique training days, sessions/week, longest gap.

All loads are converted to kg before any aggregation.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src.analysis.models import WorkoutEntry, WorkoutSet
from src.analysis.muscle_groups import muscle_group_for
from src.analysis.normalize import canonical_exercise_name, to_kg


def _parse_date(s: str) -> date:
    return datetime.fromisoformat(s).date()


def epley_1rm(weight_kg: float, reps: int) -> float:
    """Estimate one-rep max via the Epley formula: w * (1 + r/30)."""
    if reps <= 0 or weight_kg <= 0:
        return weight_kg
    if reps == 1:
        return weight_kg
    return weight_kg * (1 + reps / 30)


@dataclass
class ExerciseStats:
    exercise: str
    sessions: int = 0
    total_sets: int = 0
    total_reps: int = 0
    total_volume_kg: float = 0.0
    max_weight_kg: float = 0.0
    e1rm_kg: float = 0.0
    first_date: date | None = None
    last_date: date | None = None
    weight_trend_kg_per_week: float | None = None  # None when <2 sessions


@dataclass
class MuscleGroupStats:
    group: str
    sessions: int = 0
    total_sets: int = 0
    total_volume_kg: float = 0.0
    last_trained: date | None = None


@dataclass
class FrequencyStats:
    total_sessions: int  # unique training days
    sessions_per_week: float
    longest_gap_days: int
    span_days: int
    first_date: date | None
    last_date: date | None


def _linear_slope(xs: list[float], ys: list[float]) -> float:
    """Least-squares slope of y vs x. Returns 0 if variance is zero."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    var = sum((xs[i] - mean_x) ** 2 for i in range(n))
    return cov / var if var != 0 else 0.0


def _weight_trend_kg_per_week(entries: list[WorkoutEntry]) -> float | None:
    """Linear regression of max-weight-per-session over time (kg/week)."""
    per_date: dict[date, float] = {}
    for e in entries:
        d = _parse_date(e.date)
        weights = [to_kg(s.weight, s.unit) for s in e.sets]
        if not weights:
            continue
        per_date[d] = max(per_date.get(d, 0.0), max(weights))

    if len(per_date) < 2:
        return None

    sorted_dates = sorted(per_date.keys())
    first = sorted_dates[0]
    xs = [float((d - first).days) for d in sorted_dates]
    ys = [per_date[d] for d in sorted_dates]
    slope_per_day = _linear_slope(xs, ys)
    return round(slope_per_day * 7, 2)


def compute_per_exercise(history: list[WorkoutEntry]) -> dict[str, ExerciseStats]:
    """Aggregate stats grouped by canonical exercise name."""
    by_exercise: dict[str, list[WorkoutEntry]] = defaultdict(list)
    for entry in history:
        by_exercise[canonical_exercise_name(entry.exercise)].append(entry)

    stats: dict[str, ExerciseStats] = {}
    for exercise, entries in by_exercise.items():
        sessions = len({_parse_date(e.date) for e in entries})
        total_sets = sum(len(e.sets) for e in entries)
        total_reps = sum(s.reps for e in entries for s in e.sets)
        total_volume = sum(to_kg(s.weight, s.unit) * s.reps for e in entries for s in e.sets)
        all_weights = [to_kg(s.weight, s.unit) for e in entries for s in e.sets]
        max_weight = max(all_weights) if all_weights else 0.0
        e1rm = max(
            (epley_1rm(to_kg(s.weight, s.unit), s.reps) for e in entries for s in e.sets),
            default=0.0,
        )
        dates = sorted({_parse_date(e.date) for e in entries})

        stats[exercise] = ExerciseStats(
            exercise=exercise,
            sessions=sessions,
            total_sets=total_sets,
            total_reps=total_reps,
            total_volume_kg=round(total_volume, 1),
            max_weight_kg=round(max_weight, 1),
            e1rm_kg=round(e1rm, 1),
            first_date=dates[0] if dates else None,
            last_date=dates[-1] if dates else None,
            weight_trend_kg_per_week=_weight_trend_kg_per_week(entries),
        )
    return stats


def compute_muscle_group_balance(
    history: list[WorkoutEntry],
) -> dict[str, MuscleGroupStats]:
    """Aggregate sessions, sets, and volume per primary muscle group."""
    by_group: dict[str, list[tuple[WorkoutEntry, WorkoutSet]]] = defaultdict(list)
    for entry in history:
        primary = muscle_group_for(canonical_exercise_name(entry.exercise)).primary
        for s in entry.sets:
            by_group[primary].append((entry, s))

    stats: dict[str, MuscleGroupStats] = {}
    for group, items in by_group.items():
        sessions = len({_parse_date(e.date) for e, _ in items})
        total_sets = len(items)
        total_volume = sum(to_kg(s.weight, s.unit) * s.reps for _, s in items)
        last_trained = max(_parse_date(e.date) for e, _ in items)
        stats[group] = MuscleGroupStats(
            group=group,
            sessions=sessions,
            total_sets=total_sets,
            total_volume_kg=round(total_volume, 1),
            last_trained=last_trained,
        )
    return stats


def compute_frequency(history: list[WorkoutEntry]) -> FrequencyStats:
    if not history:
        return FrequencyStats(
            total_sessions=0,
            sessions_per_week=0.0,
            longest_gap_days=0,
            span_days=0,
            first_date=None,
            last_date=None,
        )

    unique_dates = sorted({_parse_date(e.date) for e in history})
    span = (unique_dates[-1] - unique_dates[0]).days + 1
    sessions_per_week = round(len(unique_dates) / max(span / 7, 1), 2)

    if len(unique_dates) >= 2:
        gaps = [(unique_dates[i] - unique_dates[i - 1]).days for i in range(1, len(unique_dates))]
        longest_gap = max(gaps)
    else:
        longest_gap = 0

    return FrequencyStats(
        total_sessions=len(unique_dates),
        sessions_per_week=sessions_per_week,
        longest_gap_days=longest_gap,
        span_days=span,
        first_date=unique_dates[0],
        last_date=unique_dates[-1],
    )


def filter_recent(history: list[WorkoutEntry], days: int) -> list[WorkoutEntry]:
    """Keep only entries within `days` of the most recent training date."""
    if not history:
        return []
    unique_dates = sorted({_parse_date(e.date) for e in history})
    cutoff = unique_dates[-1] - timedelta(days=days)
    return [e for e in history if _parse_date(e.date) >= cutoff]
