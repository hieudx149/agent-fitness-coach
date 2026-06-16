"""Unit tests for the analysis stats engine.

All tests run offline — no LLM, no network. The critical test is
`test_user_isolation_*` which guards the data-boundary invariant
required by the brief.
"""
import json
from pathlib import Path

import pytest

from src.analysis.models import WorkoutEntry
from src.analysis.normalize import canonical_exercise_name, to_kg
from src.analysis.stats import (
    compute_frequency,
    compute_muscle_group_balance,
    compute_per_exercise,
    epley_1rm,
)

HISTORY_PATH = Path(__file__).parent.parent / "workout_history" / "workout-history.json"


def _load_user(user_key: str) -> list[WorkoutEntry]:
    data = json.loads(HISTORY_PATH.read_text())
    return [WorkoutEntry.model_validate(w) for w in data["users"][user_key]["workouts"]]


@pytest.fixture
def user_a_history():
    return _load_user("user_a")


@pytest.fixture
def user_b_history():
    return _load_user("user_b")


# ──────────────── normalize ────────────────


def test_to_kg_converts_lb():
    assert abs(to_kg(220, "lb") - 99.79) < 0.1


def test_to_kg_passes_through_kg():
    assert to_kg(100, "kg") == 100


def test_to_kg_handles_case_insensitive_unit():
    assert abs(to_kg(100, "LB") - 45.36) < 0.1


def test_canonical_name_aliases():
    assert canonical_exercise_name("BB Bench Press") == "bench press"
    assert canonical_exercise_name("OHP") == "overhead press"
    assert canonical_exercise_name("RDL") == "romanian deadlift"
    assert canonical_exercise_name("Pull-Up") == "pull-up"


def test_canonical_unknown_exercise_lowercased():
    assert canonical_exercise_name("Snatch") == "snatch"


# ──────────────── epley ────────────────


def test_epley_1rm_single_rep_is_identity():
    assert epley_1rm(100, 1) == 100


def test_epley_1rm_higher_reps_estimate_more():
    assert abs(epley_1rm(100, 10) - 133.33) < 0.1
    assert epley_1rm(100, 5) < epley_1rm(100, 10)


def test_epley_1rm_zero_weight():
    assert epley_1rm(0, 5) == 0


# ──────────────── per-exercise ────────────────


def test_per_exercise_real_data(user_a_history):
    stats = compute_per_exercise(user_a_history)
    assert "bench press" in stats
    bp = stats["bench press"]
    assert bp.sessions > 0
    assert bp.max_weight_kg > 0
    assert bp.e1rm_kg >= bp.max_weight_kg
    assert bp.first_date is not None
    assert bp.last_date is not None
    assert bp.first_date <= bp.last_date


def test_per_exercise_empty_history():
    stats = compute_per_exercise([])
    assert stats == {}


# ──────────────── user isolation (the critical test) ────────────────


def test_user_isolation_deadlift_only_in_user_a(user_a_history, user_b_history):
    """User B's history contains no deadlifts (per edge_cases_notes).

    Running compute_per_exercise on User B alone must not surface deadlift
    stats. If it did, it would prove our stats engine pulls data from
    somewhere other than the input list — a critical isolation breach.
    """
    a_stats = compute_per_exercise(user_a_history)
    b_stats = compute_per_exercise(user_b_history)

    assert "deadlift" in a_stats, "User A should have deadlift entries"
    assert "deadlift" not in b_stats, "User B has no deadlift — isolation breach"


def test_user_isolation_independent_session_counts(user_a_history, user_b_history):
    a_freq = compute_frequency(user_a_history)
    b_freq = compute_frequency(user_b_history)
    # Different users, different lifestyles, different session counts
    assert a_freq.total_sessions != b_freq.total_sessions
    assert a_freq.total_sessions > 0
    assert b_freq.total_sessions > 0


# ──────────────── muscle group balance ────────────────


def test_balance_flags_user_b_chest_dominance(user_b_history):
    """User B trains chest most sessions and skips legs (per edge_cases_notes)."""
    balance = compute_muscle_group_balance(user_b_history)
    chest = balance.get("chest")
    assert chest is not None
    legs = balance.get("legs")
    if legs is not None:
        # Chest volume should significantly exceed legs given the imbalance
        assert chest.total_volume_kg > legs.total_volume_kg


def test_balance_unit_normalization(user_b_history):
    """User B mixes lb and kg. All balance volumes should be in kg (numeric, finite)."""
    balance = compute_muscle_group_balance(user_b_history)
    for group_stats in balance.values():
        assert group_stats.total_volume_kg > 0
        assert isinstance(group_stats.total_volume_kg, float)


# ──────────────── frequency ────────────────


def test_frequency_handles_empty_history():
    freq = compute_frequency([])
    assert freq.total_sessions == 0
    assert freq.sessions_per_week == 0
    assert freq.first_date is None


def test_frequency_real_user_a(user_a_history):
    freq = compute_frequency(user_a_history)
    assert freq.total_sessions > 0
    assert freq.sessions_per_week > 0
    assert freq.span_days > 0
