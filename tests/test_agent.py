"""Offline structural tests for the agent layer.

Full end-to-end agent behavior is exercised in the eval pipeline
(Phase 6) where adversarial + multi-step cases run against a live API.
Here we only assert wiring is correct and tool schemas conform.
"""
from src.agent.orchestrator import (
    AgentResult,
    ToolTrace,
    _history_hint,
    _result_for_model,
    _summarize_for_ui,
)
from src.agent.tools import TOOL_SCHEMAS


def test_tool_schemas_well_formed():
    assert len(TOOL_SCHEMAS) >= 2
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        fn = schema["function"]
        assert "name" in fn and isinstance(fn["name"], str)
        assert "description" in fn and len(fn["description"]) > 30
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]
        assert "required" in fn["parameters"]


def test_both_required_tools_present():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert "rag_search" in names
    assert "analyze_history" in names


def test_tool_schemas_do_not_expose_user_id_or_history():
    """user_id and history are request-context, injected by the orchestrator.

    Exposing them to the LLM would let it pass the wrong values, breaking
    the user-isolation invariant.
    """
    for schema in TOOL_SCHEMAS:
        params = schema["function"]["parameters"]["properties"]
        assert "user_id" not in params
        assert "history" not in params


def test_agent_result_defaults():
    r = AgentResult(answer="hello")
    assert r.answer == "hello"
    assert r.tool_traces == []
    assert r.sources == []
    assert r.usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_history_hint_empty_vs_populated():
    empty_hint = _history_hint(0)
    populated_hint = _history_hint(64)
    assert "do not call analyze_history" in empty_hint.lower()
    assert "64 entries" in populated_hint


def test_summarize_for_ui_rag_includes_source_count():
    summary = _summarize_for_ui(
        "rag_search",
        {"citations": [{"index": 1}, {"index": 2}], "confidence": "high"},
    )
    assert "2 sources" in summary
    assert "high" in summary


def test_summarize_for_ui_analysis_insufficient():
    summary = _summarize_for_ui("analyze_history", {"insufficient": True})
    assert "insufficient" in summary.lower()


def test_result_for_model_rag_keeps_essentials():
    import json
    payload = _result_for_model(
        "rag_search",
        {
            "answer": "Use a wider grip.",
            "citations": [
                {"index": 1, "source_file": "01-bench-press.md", "section_title": "Form", "extra": "drop"}
            ],
            "confidence": "high",
        },
    )
    parsed = json.loads(payload)
    assert parsed["answer"] == "Use a wider grip."
    assert parsed["confidence"] == "high"
    assert parsed["citations"][0]["source_file"] == "01-bench-press.md"
    # Extra fields stripped to keep token cost low
    assert "extra" not in parsed["citations"][0]


def test_tool_trace_holds_raw_result():
    t = ToolTrace(
        tool_name="rag_search",
        args={"query": "squat depth"},
        result_summary="Found 3 sources",
        raw_result={"answer": "Below parallel", "citations": []},
    )
    assert t.tool_name == "rag_search"
    assert t.raw_result["answer"] == "Below parallel"
