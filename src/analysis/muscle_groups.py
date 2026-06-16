"""Exercise → primary muscle group mapping for balance analysis.

Each exercise maps to ONE primary group (used for chest-vs-back style
balance questions) and a list of SECONDARY groups (for finer attribution).

When the brief asks "Am I overtraining chest vs back?", the answer uses
PRIMARY groups. Deadlift is "back" by convention (it's the canonical
posterior-chain pull). Romanian Deadlift is "legs" since it's a hamstring/
glute exercise programmed as a leg accessory.

Unknown exercises return {"primary": "other", "secondary": []} so the
balance report still includes them under a catch-all.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MuscleGroupAttribution:
    primary: str
    secondary: tuple[str, ...]


_MAP: dict[str, MuscleGroupAttribution] = {
    "bench press": MuscleGroupAttribution("chest", ("triceps", "front_delts")),
    "incline dumbbell press": MuscleGroupAttribution("chest", ("triceps", "front_delts")),
    "overhead press": MuscleGroupAttribution("shoulders", ("triceps",)),
    "lateral raise": MuscleGroupAttribution("shoulders", ()),
    "face pull": MuscleGroupAttribution("shoulders", ("back",)),
    "barbell row": MuscleGroupAttribution("back", ("biceps", "rear_delts")),
    "pull-up": MuscleGroupAttribution("back", ("biceps",)),
    "deadlift": MuscleGroupAttribution("back", ("legs", "core")),
    "squat": MuscleGroupAttribution("legs", ("core",)),
    "leg press": MuscleGroupAttribution("legs", ()),
    "romanian deadlift": MuscleGroupAttribution("legs", ("back",)),
    "bicep curl": MuscleGroupAttribution("arms", ()),
    "tricep pushdown": MuscleGroupAttribution("arms", ()),
}

_UNKNOWN = MuscleGroupAttribution("other", ())


def muscle_group_for(canonical_name: str) -> MuscleGroupAttribution:
    return _MAP.get(canonical_name, _UNKNOWN)


def known_exercises() -> set[str]:
    return set(_MAP.keys())
