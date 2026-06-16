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
from typing import Any

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
4. Be concise. Coaches want actionable insight, not lectures."""


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


def _assistant_message_dict(msg: Any) -> dict:
    """Convert an OpenAI assistant message into a serializable conversation entry."""
    entry: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        entry["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return entry


def _history_hint(n_entries: int) -> str:
    if n_entries == 0:
        return "[Context: no workout history provided — do not call analyze_history.]"
    return f"[Context: workout history with {n_entries} entries is available — call analyze_history when asked about the user's own data.]"


async def run_agent(
    message: str,
    user_id: str,
    history: list[dict],
    max_iterations: int = 5,
) -> AgentResult:
    settings = get_settings()
    client = get_openai_client()

    system_content = SYSTEM_PROMPT + "\n\n" + _history_hint(len(history))
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message},
    ]

    result = AgentResult(answer="")

    for iteration in range(max_iterations):
        response = await client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=800,
        )
        u = response.usage
        result.usage["prompt_tokens"] += u.prompt_tokens
        result.usage["completion_tokens"] += u.completion_tokens
        result.usage["total_tokens"] += u.total_tokens

        msg = response.choices[0].message
        messages.append(_assistant_message_dict(msg))

        if not msg.tool_calls:
            result.answer = (msg.content or "").strip()
            result.iterations = iteration + 1
            return result

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}

            tool_result = await _execute_tool(tc.function.name, args, user_id, history)

            if tc.function.name == "rag_search":
                for c in tool_result.get("citations", []):
                    result.sources.append(c)

            result.tool_traces.append(
                ToolTrace(
                    tool_name=tc.function.name,
                    args=args,
                    result_summary=_summarize_for_ui(tc.function.name, tool_result),
                    raw_result=tool_result,
                )
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _result_for_model(tc.function.name, tool_result),
                }
            )

    logger.warning("Agent exhausted max_iterations=%d before producing final answer", max_iterations)
    result.answer = (
        "I gathered information but couldn't synthesize a final response within the iteration budget. "
        "Could you rephrase or narrow down your question?"
    )
    result.iterations = max_iterations
    return result
