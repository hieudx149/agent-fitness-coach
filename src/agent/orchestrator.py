"""Coach Agent — tool-calling loop using OpenAI function calling.

Design notes:
- No framework (LangGraph / CrewAI etc.). The control flow is short and
  more debuggable inline than wrapped in agentic abstractions.
- Tool dispatch is a plain `if/elif` over tool name — adding a third tool
  means one new branch here plus a schema entry in `tools.py`.
- `user_id` and `history` are injected by the dispatcher, never passed
  through the LLM (see comment in `tools.py`).
- We accumulate `tool_traces` for the UI (Perplexity-style inline display)
  and `sources` for citation cards.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from src.agent.tools import TOOL_SCHEMAS
from src.analysis.tool import analyze_history
from src.config import get_settings
from src.llm.openai_client import get_openai_client
from src.rag.tool import rag_search

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are Coach Assist, an AI assistant for fitness coaches and their clients.

You have access to two tools:
- rag_search(query): evidence-based info from a curated fitness knowledge base.
- analyze_history(question): analyzes the CURRENT user's workout history (provided as context).

Decide which tool(s) to call based on the user's question:
- Generic fitness / training / technique questions → rag_search
- Personal-data questions (their trends, progress, neglected work, readiness) → analyze_history
- Multi-part questions that need BOTH principles AND personal data → call both, in whichever order makes sense
- Greetings or clarification questions → respond directly without any tool

Rules:
1. Do not invent data. If a tool returns insufficient data or low confidence, acknowledge it explicitly.
2. When both tools are used, integrate them into a single coherent answer — reference data points from analyze_history AND principles from rag_search.
3. Cite knowledge-base sources inline using [1], [2] matching the rag_search result. Reference specific numbers and dates from analyze_history.
4. Be concise. Coaches want actionable insight, not lectures.

Multi-hop reasoning — use the output of the first tool to refine the second tool's query:
- After analyze_history returns, derive the lifter's level from the data BEFORE crafting your rag_search query. Heuristics:
    * Weekly weight gains close to every session OR e1RM under ~1.2x bodyweight on main lifts → beginner
    * Weekly or biweekly progression (≈ 0.5-2 kg/week on a main lift) → intermediate
    * Slow progression measured monthly or per training block, OR e1RM near 2x bodyweight → advanced
- Include the derived level (and any other concrete signal like progression rate, recent volume, or muscle imbalance) in your rag_search query. Example: instead of searching "progressive overload", search "rate of progression for an intermediate lifter".
- This applies symmetrically: if rag_search came first, use the principles it surfaced to ask analyze_history a sharper question (e.g. "is the volume in the past 4 weeks consistent with a hypertrophy block?")."""


@dataclass
class ToolTrace:
    tool_name: str
    args: dict[str, Any]
    result_summary: str
    raw_result: dict[str, Any]


@dataclass
class AgentResult:
    answer: str
    tool_traces: list[ToolTrace] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    iterations: int = 0


async def _execute_tool(
    name: str,
    args: dict[str, Any],
    user_id: str,
    history: list[dict],
) -> dict[str, Any]:
    """Dispatch a tool call. Injects request context into analyze_history."""
    if name == "rag_search":
        return await rag_search(query=args.get("query", ""))
    if name == "analyze_history":
        return await analyze_history(
            user_id=user_id,
            question=args.get("question", ""),
            history=history,
        )
    return {"error": f"Unknown tool: {name}"}


def _summarize_for_ui(name: str, result: dict[str, Any]) -> str:
    """Compact text used in the UI tool-trace card header."""
    if name == "rag_search":
        n_sources = len(result.get("citations", []))
        conf = result.get("confidence", "?")
        return f"Found {n_sources} sources (confidence={conf})"
    if name == "analyze_history":
        if result.get("insufficient"):
            return "Insufficient workout history"
        return "Computed workout summary"
    if "error" in result:
        return f"Tool error: {result['error']}"
    return ""


def _result_for_model(name: str, result: dict[str, Any]) -> str:
    """JSON payload fed back to the model — kept compact to save tokens."""
    if name == "rag_search":
        return json.dumps(
            {
                "answer": result.get("answer"),
                "citations": [
                    {
                        "index": c["index"],
                        "source_file": c["source_file"],
                        "section_title": c["section_title"],
                    }
                    for c in result.get("citations", [])
                ],
                "confidence": result.get("confidence"),
            }
        )
    if name == "analyze_history":
        return json.dumps(
            {
                "insight": result.get("insight"),
                "stats_summary": result.get("stats_summary", "")[:3500],
                "insufficient": result.get("insufficient", False),
            }
        )
    return json.dumps(result)


def _history_hint(n_entries: int) -> str:
    if n_entries == 0:
        return "[Context: no workout history provided — do not call analyze_history.]"
    return f"[Context: workout history with {n_entries} entries is available — call analyze_history when asked about the user's own data.]"


async def run_agent_stream(
    message: str,
    user_id: str,
    history: list[dict],
    max_iterations: int = 5,
) -> AsyncIterator[dict]:
    """Async generator yielding events as the agent runs.

    Event shapes:
      {"type": "delta",       "text": "..."}                 # final-answer token chunk
      {"type": "tool_call",   "tool_name": "...", "args": {...}}
      {"type": "tool_result", "tool_name": "...", "args": {...},
                              "summary": "...", "detail": {...}}
      {"type": "done",        "answer": "...", "sources": [...],
                              "usage": {...}, "iterations": int}
    """
    settings = get_settings()
    client = get_openai_client()

    system_content = SYSTEM_PROMPT + "\n\n" + _history_hint(len(history))
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    accumulated_sources: list[dict] = []
    final_answer = ""

    for iteration in range(max_iterations):
        stream = await client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=800,
            stream=True,
            stream_options={"include_usage": True},
        )

        content_buffer = ""
        tool_calls_buffer: dict[int, dict] = {}

        async for chunk in stream:
            if chunk.usage is not None:
                total_usage["prompt_tokens"] += chunk.usage.prompt_tokens or 0
                total_usage["completion_tokens"] += chunk.usage.completion_tokens or 0
                total_usage["total_tokens"] += chunk.usage.total_tokens or 0

            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                content_buffer += delta.content
                # Stream content deltas live. If this round turns out to be a
                # tool-call round (tool_calls accumulated later), the small
                # preamble already emitted is still legitimate "thinking aloud".
                yield {"type": "delta", "text": delta.content}

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    slot = tool_calls_buffer.setdefault(
                        idx,
                        {"id": "", "function": {"name": "", "arguments": ""}},
                    )
                    if tc_delta.id:
                        slot["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            slot["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            slot["function"]["arguments"] += tc_delta.function.arguments

        # End of one round. Reconstruct the assistant message for conversation history.
        assistant_entry: dict[str, Any] = {"role": "assistant", "content": content_buffer or ""}
        if tool_calls_buffer:
            assistant_entry["tool_calls"] = [
                {
                    "id": tool_calls_buffer[i]["id"],
                    "type": "function",
                    "function": {
                        "name": tool_calls_buffer[i]["function"]["name"],
                        "arguments": tool_calls_buffer[i]["function"]["arguments"],
                    },
                }
                for i in sorted(tool_calls_buffer)
            ]
        messages.append(assistant_entry)

        if not tool_calls_buffer:
            final_answer = content_buffer.strip()
            yield {
                "type": "done",
                "answer": final_answer,
                "sources": accumulated_sources,
                "usage": total_usage,
                "iterations": iteration + 1,
            }
            return

        # Execute each tool, emit start + result events, feed result back to LLM.
        for i in sorted(tool_calls_buffer):
            tc = tool_calls_buffer[i]
            tool_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
            except json.JSONDecodeError:
                args = {}

            yield {"type": "tool_call", "tool_name": tool_name, "args": args}

            tool_result = await _execute_tool(tool_name, args, user_id, history)
            if tool_name == "rag_search":
                for c in tool_result.get("citations", []):
                    accumulated_sources.append(c)

            yield {
                "type": "tool_result",
                "tool_name": tool_name,
                "args": args,
                "summary": _summarize_for_ui(tool_name, tool_result),
                "detail": {k: v for k, v in tool_result.items() if k != "usage"},
            }

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": _result_for_model(tool_name, tool_result),
                }
            )

    logger.warning("Agent exhausted max_iterations=%d before producing final answer", max_iterations)
    yield {
        "type": "done",
        "answer": (
            "I gathered information but couldn't synthesize a final response within the "
            "iteration budget. Could you rephrase or narrow down your question?"
        ),
        "sources": accumulated_sources,
        "usage": total_usage,
        "iterations": max_iterations,
    }


async def run_agent(
    message: str,
    user_id: str,
    history: list[dict],
    max_iterations: int = 5,
) -> AgentResult:
    """Non-streaming entry point — consumes the stream into an AgentResult.

    Kept so the eval pipeline and any other JSON consumer can call this
    without dealing with NDJSON parsing.
    """
    result = AgentResult(answer="")
    streamed_chunks: list[str] = []

    async for event in run_agent_stream(message, user_id, history, max_iterations):
        if event["type"] == "delta":
            streamed_chunks.append(event["text"])
        elif event["type"] == "tool_result":
            result.tool_traces.append(
                ToolTrace(
                    tool_name=event["tool_name"],
                    args=event["args"],
                    result_summary=event["summary"],
                    raw_result=event["detail"],
                )
            )
        elif event["type"] == "done":
            result.answer = event.get("answer") or "".join(streamed_chunks).strip()
            result.sources = event.get("sources", [])
            result.usage = event.get("usage", result.usage)
            result.iterations = event.get("iterations", 0)

    return result
