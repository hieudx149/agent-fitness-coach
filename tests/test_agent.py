"""Offline structural tests for the agent layer.

Full end-to-end agent behavior is exercised in the eval pipeline
(Phase 6) where adversarial + multi-step cases run against a live API.
Here we only assert wiring is correct and tool schemas conform.
"""
from src.agent.orchestrator import (
    AgentResult,
    ToolTrace,
    _filter_cited_data_points,
    _finalize_sources,
    _history_hint,
    _offset_rag_citations,
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


def test_offset_rag_citations_zero_offset_is_noop():
    result = {
        "answer": "Use a wider grip [1].",
        "citations": [{"index": 1, "source_file": "01-bench-press.md"}],
    }
    _offset_rag_citations(result, 0)
    assert result["citations"][0]["index"] == 1
    assert result["answer"] == "Use a wider grip [1]."


def test_offset_rag_citations_shifts_indices_and_inline_refs():
    """A second rag_search batch must continue numbering after the first.

    This is the multi-hop citation-collision bug: without an offset, the
    second retrieval restarts at [1] and the UI shows two [1]..[N] blocks.
    """
    result = {
        "answer": "RPE measures effort [1]. RIR is the inverse [2][3].",
        "citations": [
            {"index": 1, "source_file": "11-rpe-rir.md"},
            {"index": 2, "source_file": "11-rpe-rir.md"},
            {"index": 3, "source_file": "11-rpe-rir.md"},
        ],
    }
    _offset_rag_citations(result, 7)
    assert [c["index"] for c in result["citations"]] == [8, 9, 10]
    assert result["answer"] == "RPE measures effort [8]. RIR is the inverse [9][10]."


def test_offset_rag_citations_handles_missing_answer():
    result = {"citations": [{"index": 1, "source_file": "x.md"}]}
    _offset_rag_citations(result, 5)
    assert result["citations"][0]["index"] == 6


def test_finalize_sources_empty_is_noop():
    sources, answer = _finalize_sources([], "no sources here")
    assert sources == []
    assert answer == "no sources here"


def test_finalize_sources_sorts_by_score_and_renumbers():
    """Merged multi-hop sources must end up globally sorted with sequential ids."""
    sources = [
        {"index": 1, "source_file": "a.md", "score": 0.886},
        {"index": 2, "source_file": "b.md", "score": 0.303},
        {"index": 3, "source_file": "c.md", "score": 0.794},  # 2nd hop outranks tail of 1st
    ]
    answer = "First [1], weak [2], second-hop [3]."
    ordered, remapped = _finalize_sources(sources, answer)

    assert [c["index"] for c in ordered] == [1, 2, 3]
    assert [c["score"] for c in ordered] == [0.886, 0.794, 0.303]
    # [1] stays [1] (still top), [3] becomes [2], [2] becomes [3].
    assert remapped == "First [1], weak [3], second-hop [2]."


def test_finalize_sources_leaves_unmatched_refs_untouched():
    sources = [{"index": 5, "source_file": "a.md", "score": 0.5}]
    ordered, remapped = _finalize_sources(sources, "cite [5] and a stray [9].")
    assert ordered[0]["index"] == 1
    assert remapped == "cite [1] and a stray [9]."


def test_filter_cited_data_points_keeps_only_referenced():
    data_points = [
        {"ref": "D1", "category": "Frequency", "label": "Training frequency", "detail": "…"},
        {"ref": "D2", "category": "Exercise", "label": "bench press", "detail": "…"},
        {"ref": "D3", "category": "Muscle group", "label": "chest", "detail": "…"},
    ]
    answer = "Your bench is trending up [D2] and chest volume leads [D3]."
    kept = _filter_cited_data_points(data_points, answer)
    assert [d["ref"] for d in kept] == ["D2", "D3"]


def test_filter_cited_data_points_no_citations_returns_empty():
    data_points = [{"ref": "D1", "category": "x", "label": "y", "detail": "z"}]
    assert _filter_cited_data_points(data_points, "no refs here") == []
    assert _filter_cited_data_points([], "mentions [D1]") == []


def test_tool_trace_holds_raw_result():
    t = ToolTrace(
        tool_name="rag_search",
        args={"query": "squat depth"},
        result_summary="Found 3 sources",
        raw_result={"answer": "Below parallel", "citations": []},
    )
    assert t.tool_name == "rag_search"
    assert t.raw_result["answer"] == "Below parallel"
