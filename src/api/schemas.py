"""Pydantic schemas for the /chat endpoint.

Request/response shapes are intentionally flat — they map 1:1 to what
the UI needs to render and what the eval pipeline needs to score.
"""
from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field(default="anonymous", max_length=64)
    history: list[dict] = Field(
        default_factory=list,
        description="Optional workout history JSON array (passed when the user wants analysis).",
    )


class ToolTraceModel(BaseModel):
    tool_name: str
    args: dict[str, Any]
    result_summary: str


class CitationModel(BaseModel):
    index: int
    source_file: str
    section_title: str
    chunk_id: str | None = None
    score: float
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    refused: bool = False
    refusal_category: str | None = None
    tool_traces: list[ToolTraceModel] = Field(default_factory=list)
    sources: list[CitationModel] = Field(default_factory=list)
    usage: dict[str, int] | None = None
    iterations: int | None = None
