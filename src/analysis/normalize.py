"""Unit + exercise name normalization.

The workout history mixes kg/lb (User B switches mid-period). All stats
math runs in kg, so every load passes through `to_kg` first.

Exercise names are canonicalized to lowercase with common alias mapping
so "BB Bench Press" and "barbell bench press" collapse to the same key.
"""
LB_TO_KG = 0.453592

# Known exercise aliases → canonical form. Keep keys lowercase + stripped.
# Extend as needed for new exercises (must also be added to muscle_groups.py).
_ALIASES: dict[str, str] = {
    "bb bench press": "bench press",
    "barbell bench press": "bench press",
    "bench press": "bench press",
    "incline db press": "incline dumbbell press",
    "incline dumbbell press": "incline dumbbell press",
    "incline bench press": "incline dumbbell press",
    "ohp": "overhead press",
    "military press": "overhead press",
    "overhead press": "overhead press",
    "shoulder press": "overhead press",
    "bb squat": "squat",
    "back squat": "squat",
    "high bar squat": "squat",
    "low bar squat": "squat",
    "squat": "squat",
    "front squat": "squat",
    "conventional deadlift": "deadlift",
    "sumo deadlift": "deadlift",
    "deadlift": "deadlift",
    "rdl": "romanian deadlift",
    "romanian deadlift": "romanian deadlift",
    "leg press": "leg press",
    "barbell row": "barbell row",
    "bent over row": "barbell row",
    "pendlay row": "barbell row",
    "pull-up": "pull-up",
    "pull up": "pull-up",
    "chin-up": "pull-up",
    "chin up": "pull-up",
    "bicep curl": "bicep curl",
    "biceps curl": "bicep curl",
    "barbell curl": "bicep curl",
    "dumbbell curl": "bicep curl",
    "tricep pushdown": "tricep pushdown",
    "triceps pushdown": "tricep pushdown",
    "cable pushdown": "tricep pushdown",
    "face pull": "face pull",
    "lateral raise": "lateral raise",
    "side lateral raise": "lateral raise",
}


def to_kg(weight: float, unit: str) -> float:
    """Convert weight to kilograms. Unknown units pass through unchanged."""
    u = (unit or "").strip().lower()
    if u == "lb":
        return weight * LB_TO_KG
    return weight


def canonical_exercise_name(name: str) -> str:
    """Map an exercise name to its canonical form (lowercase + aliased).

    Unknown names are returned lowercased and stripped — they'll still be
    counted in per-exercise stats, just without a muscle-group attribution.
    """
    if not name:
        return ""
    s = name.strip().lower()
    return _ALIASES.get(s, s)
