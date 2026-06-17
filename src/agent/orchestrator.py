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
- analyze_history(question): returns a deterministic markdown summary of stats over the CURRENT user's workout history (sessions, max weight, e1RM, weekly trend, muscle-group balance, frequency). The tool itself runs no LLM — you read the summary and synthesise the answer.

Tool selection:
- Generic fitness / training / technique / principle questions → rag_search
- Personal-data questions (their trends, progress, neglected work, readiness) → analyze_history
- Greetings or clarification questions → respond directly without any tool
- When the answer requires BOTH personal data AND general principles, follow the multi-hop protocol below.

Rules:
1. Do not invent data. If a tool returns insufficient data or low confidence, acknowledge it explicitly.
2. Cite knowledge-base sources inline using [1], [2] matching the rag_search result. Reference specific numbers and dates from analyze_history.
3. Be concise. Coaches want actionable insight, not lectures.

Multi-hop protocol — when a question needs information from BOTH tools:
- Call tools SEQUENTIALLY, never in the same turn. Each call is one hop. Wait for one tool's result before deciding the next tool's input.
- After each hop, READ the result, then DERIVE one or more concrete facts (training stage / level, recent progression rate, muscle imbalance, neglected exercise, programming style — whatever the data actually reveals). The next tool's input MUST include at least one of those derived facts.
- A query that re-uses only the user's original wording is a failure of the protocol. You must inject what you just learned.
- Concrete example you SHOULD follow:
    User asks: "Based on my history, is my bench ready to go up? What does progressive overload look like for my level?"
    Hop 1: analyze_history → reveals weekly weight gain of ~1 kg/week with a stable rep range (consistent with an intermediate stage).
    Hop 2 (correct): rag_search("rate of progression for intermediate lifters")
    Hop 2 (wrong — same wording as user, no derivation): rag_search("what does progressive overload look like for bench press")
- Coverage rule: when the user asks for a RECOMMENDATION, ADVICE, or "what should I tell my client / do next" — you almost always need BOTH analyze_history (to see what the user actually does) AND rag_search (to ground the recommendation in evidence). Do not answer a recommendation-style question from one tool alone.
- Only skip the second hop when the user's question is purely informational (e.g. "what is RPE?") or purely about their stats (e.g. "what's my bench trend?") — never when they are asking what to do.
- The final answer must integrate both sources when both were called: name the specific data points from analyze_history and the principles (with [n] citations) from rag_search side by side."""


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
                "stats_summary": result.get("stats_summary", "")[:3500],
                "insufficient": result.get("insufficient", False),
                "n_workouts": result.get("n_workouts", 0),
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
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
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
