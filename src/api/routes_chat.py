"""POST /api/v1/chat — single user-facing endpoint.

Flow:
  1. Validate request (Pydantic).
  2. Guardrails classifier — refuse early if unsafe / out-of-scope.
  3. Coach Agent — tool-calling loop (rag_search, analyze_history).
  4. Return answer + tool traces + sources.

Also exposes GET /api/v1/sample-history for the UI to load demo
workout data without the user having to paste JSON.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.agent.orchestrator import run_agent
from src.api.schemas import ChatRequest, ChatResponse, CitationModel, ToolTraceModel
from src.guardrails.classifier import classify
from src.guardrails.refusal import refusal_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

SAMPLE_HISTORY_PATH = Path("workout_history/workout-history.json")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    classification = await classify(request.message)

    if not classification.is_safe:
        logger.info(
            "Refused: category=%s user=%s reason=%s",
            classification.category.value,
            request.user_id,
            classification.reason,
        )
        return ChatResponse(
            answer=refusal_message(classification.category),
            refused=True,
            refusal_category=classification.category.value,
        )

    try:
        result = await run_agent(
            message=request.message,
            user_id=request.user_id,
            history=request.history,
        )
    except Exception as exc:  # noqa: BLE001 — surface as 500 with detail
        logger.exception("Agent execution failed")
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc

    return ChatResponse(
        answer=result.answer,
        tool_traces=[
            ToolTraceModel(
                tool_name=t.tool_name,
                args=t.args,
                result_summary=t.result_summary,
                result_detail={
                    k: v for k, v in t.raw_result.items() if k != "usage"
                },
            )
            for t in result.tool_traces
        ],
        sources=[CitationModel(**s) for s in result.sources],
        usage=result.usage,
        iterations=result.iterations,
    )


@router.get("/sample-history")
async def sample_history(user_id: str = "user_a") -> dict:
    """Demo helper for the UI — returns one of the sample users' workouts."""
    if not SAMPLE_HISTORY_PATH.is_file():
        raise HTTPException(status_code=404, detail="Sample history file not found")
    data = json.loads(SAMPLE_HISTORY_PATH.read_text())
    if user_id not in data.get("users", {}):
        raise HTTPException(status_code=404, detail=f"Unknown user_id: {user_id}")
    user = data["users"][user_id]
    return {
        "user_id": user_id,
        "name": user.get("name"),
        "profile": user.get("profile"),
        "history": user.get("workouts", []),
    }
