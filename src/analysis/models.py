"""Pydantic models for workout history input.

Lenient on unit casing and exercise name spelling — both are normalized
downstream in `normalize.py`. We don't reject ambiguous input at the
schema layer because the brief says we need to handle "unknown exercises"
gracefully.
"""
from pydantic import BaseModel, Field


class WorkoutSet(BaseModel):
    reps: int = Field(ge=0)
    weight: float = Field(ge=0)
    unit: str  # "kg" or "lb"; normalized to kg before stats


class WorkoutEntry(BaseModel):
    date: str  # ISO date string (YYYY-MM-DD)
    exercise: str
    sets: list[WorkoutSet]
