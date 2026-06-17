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
from fastapi.responses import StreamingResponse

from src.agent.orchestrator import run_agent, run_agent_stream
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    CitationModel,
    DataPointModel,
    ToolTraceModel,
)
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
            name=request.name,
            profile=request.profile,
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
        data_points=[DataPointModel(**d) for d in result.data_points],
        usage=result.usage,
        iterations=result.iterations,
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Streaming variant of /chat — emits NDJSON events as the agent works.

    Event types:
      {"type":"guardrail", "refused": bool, "category": str|null, "answer": str?}
      {"type":"tool_call", "tool_name": str, "args": {...}}
      {"type":"tool_result", "tool_name": str, "args": {...}, "summary": str, "detail": {...}}
      {"type":"delta", "text": str}
      {"type":"done", "answer": str, "sources": [...], "usage": {...}, "iterations": int}
      {"type":"error", "message": str}

    Each event is one JSON object on its own line (application/x-ndjson).
    """

    async def event_stream():
        classification = await classify(request.message)
        if not classification.is_safe:
            logger.info(
                "Stream refused: category=%s user=%s",
                classification.category.value,
                request.user_id,
            )
            yield (
                json.dumps(
                    {
                        "type": "guardrail",
                        "refused": True,
                        "category": classification.category.value,
                        "answer": refusal_message(classification.category),
                    }
                )
                + "\n"
            )
            yield json.dumps({"type": "done", "answer": refusal_message(classification.category),
                              "sources": [], "usage": None, "iterations": 0}) + "\n"
            return

        yield json.dumps({"type": "guardrail", "refused": False, "category": None}) + "\n"

        try:
            async for event in run_agent_stream(
                message=request.message,
                user_id=request.user_id,
                history=request.history,
                name=request.name,
                profile=request.profile,
            ):
                yield json.dumps(event) + "\n"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Stream agent failed")
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sample-history")
async def sample_history(user_id: str = "user_a") -> dict:
    """Returns the workout list for one user. Used by both eval and UI."""
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
        "role": user.get("role"),
        "history": user.get("workouts", []),
    }


@router.get("/users")
async def list_users() -> dict:
    """Roster of demo users grouped by role — drives the UI's role + target picker.

    Returns:
        {
          "coaches": [{id, name, profile, clients: [{id, name, n_workouts, profile}, ...]}],
          "gymers":  [{id, name, profile, n_workouts}, ...]
        }
    """
    if not SAMPLE_HISTORY_PATH.is_file():
        raise HTTPException(status_code=404, detail="Sample history file not found")
    data = json.loads(SAMPLE_HISTORY_PATH.read_text())
    users = data.get("users", {})

    coaches: list[dict] = []
    gymers: list[dict] = []

    for uid, u in users.items():
        role = u.get("role")
        if role == "coach":
            client_ids = u.get("clients", [])
            client_objs = []
            for cid in client_ids:
                c = users.get(cid, {})
                client_objs.append(
                    {
                        "id": cid,
                        "name": c.get("name", cid),
                        "profile": c.get("profile", ""),
                        "n_workouts": len(c.get("workouts", [])),
                    }
                )
            coaches.append(
                {
                    "id": uid,
                    "name": u.get("name", uid),
                    "profile": u.get("profile", ""),
                    "clients": client_objs,
                }
            )
        elif role == "gymer":
            gymers.append(
                {
                    "id": uid,
                    "name": u.get("name", uid),
                    "profile": u.get("profile", ""),
                    "n_workouts": len(u.get("workouts", [])),
                }
            )

    return {"coaches": coaches, "gymers": gymers}
