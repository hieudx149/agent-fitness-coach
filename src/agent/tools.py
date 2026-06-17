"""OpenAI function-call schemas for the Coach Agent tools.

We deliberately do NOT expose `user_id` or `history` as tool parameters.
Those are request-context, not LLM decisions — the orchestrator injects
them when dispatching. This:
  1. Prevents the model from passing the wrong user's data,
  2. Keeps tool schemas minimal so model token cost stays low,
  3. Makes the user-isolation invariant trivially auditable.

To add a third tool: append another entry here and add a branch in the
orchestrator's `_execute_tool`. No other code needs to change — the
agent reads tool selection straight from the schema.
"""
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Search a curated fitness knowledge base for evidence-based information about "
                "training principles, exercise technique, programming (PPL, upper/lower, full body), "
                "progressive overload, periodization, deloads, RPE/RIR, recovery, and nutrition "
                "fundamentals. Use this for generic 'how to' or 'what is' questions. Returns a "
                "grounded answer with source citations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural-language search query. Be specific — e.g. "
                            "'how to program a deload after 8 weeks of progressive overload' "
                            "instead of just 'deload'."
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_history",
            "description": (
                "Compute deterministic statistics on the current user's workout history. Returns a "
                "markdown table summarising sessions, max weight, e1RM, weekly weight trend, "
                "muscle-group balance, and frequency. NO LLM is invoked inside the tool — you read "
                "the table and synthesise the answer yourself, referencing specific numbers and "
                "dates. Use this when the user references THEIR OWN data — trends in specific lifts, "
                "neglected muscle groups, readiness to increase weight, recent volume, gaps in "
                "training. The user's workout history is provided as context (you do not pass it "
                "as an argument)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "The analysis question. E.g. 'what is the bench press trend over the "
                            "last month?', 'am I overtraining chest compared to back?'"
                        ),
                    }
                },
                "required": ["question"],
            },
        },
    },
]
