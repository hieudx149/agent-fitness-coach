# AI_WORKFLOW.md

> How I used AI tooling to direct, correct, and review this build — not just whether I used it, but how I structured the collaboration, where it helped, where it hurt, and what I actually did about it.

---

## Core Strategy: Align First, Generate Second

My fundamental approach was to treat Claude not as a code generator but as a **technical collaborator that needed to be aligned before it could be trusted to produce anything**.

The workflow had two distinct phases before any code was written:

**Phase A — Requirements Internalization**
I fed Claude the full requirements and asked it to interview me — not to summarize the brief, but to ask clarifying questions until it could explain back to me what the system needed to do, what the constraints were, and where the ambiguities were. This produced a shared mental model before any design decision was made.

Example exchange:
> Me: "Read the requirements document and ask me everything you need to know before proposing any architecture."
>
> Claude: "A few things I want to confirm before designing:
>   1. Is the agent expected to maintain conversation history across turns, or is each query stateless?
>   2. Should guardrails run before or after the agent decides which tool to call?
>   3. Data isolation — is this enforced at the API layer or should the LLM itself be instructed never to mix users?"

These questions forced me to make decisions I hadn't consciously made yet. My answers became the constraints Claude designed against.

**Phase B — Architecture Review Before Commitment**
Only after alignment did I ask Claude to propose architecture and tech stack. I then spent time at this stage — reviewing every proposal, pushing back on choices that didn't fit the constraints we'd aligned on, and asking Claude to justify each decision with tradeoffs, not just recommendations.

This front-loaded investment meant that by the time code was being written, Claude was working inside a well-defined boundary — and deviations were easier to catch because I had a clear reference point.

---

## Tools Used at Each Stage

| Stage | Tool | What I used it for | What I changed or overrode |
|---|---|---|---|
| Requirements alignment | Claude (Opus 4.7) | Asked Claude to interview me on the brief — surface ambiguities, confirm constraints, align on scope before any design | Added explicit data isolation constraint that Claude hadn't flagged as a design concern |
| Architecture proposal | Claude Code (plan mode) | Proposed overall system architecture, tech stack options with tradeoffs, API contract shape | Overrode Claude's Chroma recommendation in favour of Qdrant (dashboard UX matters for the demo + better metadata filtering for future per-coach partitioning); collapsed Claude's initial 3-endpoint design (`/rag`, `/analysis`, `/agent`) into a single `/chat` going through the agent — the brief asks for 3 features, not 3 endpoints |
| Coding | Claude Code (interactive) | Writing every module — chunker, FPT client, retriever, generator, guardrail classifier, stats engine, orchestrator, UI | Rejected the OOP-default `StatsEngine` class in favour of pure functions (see "rejected suggestion" section — it would have made user-isolation a code-review property instead of a structural one); removed 3 unnecessary try/except wrapper layers Claude added defensively |
| Prompt engineering | Claude as drafting partner, calibrated against eval | Draft system prompts for classifier, RAG generator, insight builder, agent | The two load-bearing prompts (classifier and agent) went through 4 revisions each — every change driven by an observed failure (smoke test or eval case), not a priori guessing. RAG generator + insight builder needed only minor tweaks |
| Code review | My eyes + pytest + live smoke tests | Never accepted a generated file without reading line by line and running its tests or hitting the live endpoint | — |
| Evaluation | GPT-4o as LLM-as-judge | Faithfulness and refusal correctness scoring | Combined with rule-based metrics so the judge isn't the sole arbiter |
| Documentation | Claude for first drafts | README, EVALUATION.md, this file | Every committed .md was rewritten for tone and structure — Claude's drafts were outlines, not final copy |

---

## My Prompting Strategy — and How It Evolved

### Stage 1: Interview mode (requirements)

Before writing a single line, I prompted Claude to ask me questions:

```
"I'm going to give you a take-home assignment brief. Before you propose anything, I want you to ask me every clarifying question you need until you can explain back to me:
1. What the system needs to do
2. What the hard constraints are
3. Where the brief is ambiguous"
```

This produced 11 questions. Three of them surfaced decisions I hadn't made: stateless vs stateful agent, where guardrails sit in the call stack, and whether data isolation was an API concern or an LLM-prompt concern. My answers to those three shaped the entire architecture.

### Stage 2: Architecture proposal + structured review

Once aligned, I asked for an architecture proposal with explicit tradeoffs — not just "here's what to use" but "here's what each choice costs you":

```
"Now propose the architecture. For each major decision 
(LLM provider, vector DB, agent pattern, API framework), 
give me:
- Your recommendation
- The main alternative
- What I give up by choosing your recommendation
- What constraint from our alignment makes you prefer it"
```

This format forced Claude to make its reasoning legible. I could then disagree with specific tradeoffs rather than accepting or rejecting the whole proposal.

### Stage 3: Scoped implementation prompts

Mid-build I switched to one feature per session with full context of existing modules:

```
"Build the chunker. Constraints: 
- Must work with the existing config module (attached)
- Chunk size 512 tokens, 50-token overlap
- Return chunk metadata including source doc and position
- No new dependencies beyond what's in requirements.txt"
```

Broad prompts produced over-engineered code. Scoped prompts with explicit constraints produced code that fit.

### Stage 4: System prompts as versioned code

Every system prompt (classifier, RAG generator, insight builder, agent) was versioned in git with commit messages explaining the *why* of each change. The classifier prompt has 4 revisions:

| Revision | Trigger | Change |
|---|---|---|
| v1 | Initial (`6189ce4`) | Narrow SAFE definition: "fitness questions only"; 4 refusal categories with redirects |
| v2 | Smoke test: `"hi there"` → refused as OUT_OF_SCOPE (`a1affc7`) | Enumerated SAFE into 5 sub-categories — fitness questions, greetings & small talk, meta-conversation about the assistant, clarification follow-ups, personal-data questions — so the same prompt that defines refusals also positively defines what gets through |
| v3 | Eval case `analysis_02`: `"Am I overtraining my chest vs back?"` → EATING_DISORDER (`1cc6b0d`) | One-line disambiguation clause: "training volume balance / 'overtraining a muscle group' is TRAINING LOAD, not eating — SAFE." Analysis pass rate 60% → 100% |

### Stage 5: Iterating the agent prompt for true multi-hop reasoning

The classifier prompt was about *what to refuse*. The agent SYSTEM_PROMPT in `src/agent/orchestrator.py` was harder — it had to teach a stateless LLM to plan a *sequence* of tool calls where the second call depends on what the first returned. It took four revisions, all driven by failures I observed at runtime:

| Revision | Trigger | Change |
|---|---|---|
| v1 | Initial | "Multi-part questions that need BOTH ... call both, in whichever order makes sense." |
| v2 | PDF John-bench test: agent called both tools but rag_search query was generic ("progressive overload for bench press"), rerank confidence 0.139 — retrieval landed on "Methods" instead of "Rate of Progression for intermediate" | Added explicit lifter-level heuristics (`e1RM under ~1.2x bodyweight → beginner`, `weekly ~0.5–2 kg → intermediate`) and "include derived level in the second-hop query" |
| v3 | Self-review: the heuristics were too prescriptive — they encoded one question shape ("what's my level for progression?") into the prompt. Any other multi-hop question got no useful pattern. | Generalised: dropped kg/week thresholds, replaced with the abstract pattern **observe → derive → refine → call** + a MUST rule: "the next tool's query MUST include at least one fact derived from the previous tool's result; reusing the user's original wording is a failure of the protocol" |
| v4 | Eval regression on `agent_02` (client shoulder tightness): agent skipped `rag_search` because v3 also said "stop calling tools when you have enough" — but a recommendation needs KB grounding | Added **coverage rule**: recommendation-style questions ("what should I tell my client / do next") require BOTH tools regardless of what one tool returned. Explicit override of the efficiency rule. |

The deeper learning was about **what an LLM needs to imitate versus what it can derive**. The v2 specific heuristics worked but only for the question shape I'd anchored them to. v3 was generalised — but the first attempt failed because pure abstraction ("use derived facts to refine the query") wasn't enough signal: the model defaulted back to the user's literal wording. What unlocked v3 was adding ONE concrete anti-pattern → correct-example pair inside the otherwise general prompt:

> Hop 2 (correct):  `rag_search("rate of progression for intermediate lifters")`
> Hop 2 (wrong — same wording as user): `rag_search("what does progressive overload look like for bench press")`

A single anchored exemplar was enough for the model to extend the pattern to new question shapes (volume balance, neglected muscle group, etc.) without me needing to enumerate each case. Generalisation needs **one** concrete attachment point, not zero.

After v4, the PDF John-bench question routes:

- Hop 1 → `analyze_history("Is John ready to increase bench press weight?")` — surfaces +1.28 kg/week, e1RM 104.5 kg (intermediate)
- Hop 2 → `rag_search("rate of progression for intermediate lifters")` — confidence high, lands directly on `08-progressive-overload.md / Rate of Progression`
- Final synthesis cites both side-by-side.

Committed:
- `acf344c fix(agent): explicit multi-hop reasoning in system prompt` (v2)
- `8db6859 fix(agent): generalise multi-hop protocol + coverage rule` (v3 + v4)

This iteration is the clearest example in the build of treating the system prompt as code: every revision has a commit message explaining the failure that triggered it and the test that now passes.

---

## Two Examples Where AI Output Was Wrong

### Example 1 — Classifier over-blocked greetings

**What the AI produced.**
The initial guardrail classifier defined SAFE as "a legitimate fitness/exercise/training/workout question". The agent's system prompt said: "if the user just says hi, respond directly without any tool call."

**Why it was wrong.**
Both prompts looked sensible in isolation. Together they were inconsistent — the classifier ran *before* the agent and refused the message entirely, so the agent's permissive instruction never fired. Caught on smoke test E4: sent "hi there", got the OUT_OF_SCOPE refusal template.

**How I corrected it.**
Rewrote the SAFE definition to enumerate five sub-categories explicitly: fitness questions, greetings and small talk, meta-conversation, clarification follow-ups, and personal-data questions. Re-ran with three greeting variants plus two adversarial sanity checks. All six passed.

Committed: `a1affc7 fix(guardrails): allow greetings and meta-conversation in classifier`

**Lesson:** Always specify both sides of a classifier — what triggers refusal AND what stays safe. The AI left the SAFE bucket underspecified because it was focused on the refusal categories.

---

### Example 2 — Classifier mis-classified "overtraining" as EATING_DISORDER

**What the AI produced.**
First version defined EATING_DISORDER as "extreme caloric restriction, purging, body dysmorphia content, or rapid weight-loss tactics."

**Why it was wrong.**
Eval case analysis_02: "Am I overtraining my chest compared to my back? Use specific numbers from my history." → Classifier returned EATING_DISORDER. The word "overtraining" plus body-part language triggered the loose pattern. User got a mental-health redirect instead of workout analysis. Scored 1/4 metrics.

**How I corrected it.**
Added explicit disambiguation: "questions about training volume balance, 'overtraining' a muscle group, or muscle imbalance are about TRAINING LOAD, not eating — they are SAFE, not EATING_DISORDER." One-line diff. Analysis pass rate: 60% → 100%.

Committed: `1cc6b0d fix(guardrails): disambiguate "overtraining" from EATING_DISORDER`

**Lesson:** LLM classifiers handle named categories well but fail at boundaries where fitness vocabulary overlaps with sensitive-topic vocabulary. Disambiguation must be explicit.

---

## One Example Where I Rejected an AI Suggestion Entirely

**What it suggested.**
When scaffolding the analysis module (Phase 4), Claude defaulted to an idiomatic Python OOP design for the stats engine:

```python
class StatsEngine:
    def __init__(self, history: list[WorkoutEntry]):
        self.history = history
        self._cache_per_exercise: dict | None = None

    def per_exercise(self) -> dict[str, ExerciseStats]:
        if self._cache_per_exercise is None:
            self._cache_per_exercise = self._compute_per_exercise()
        return self._cache_per_exercise

    def muscle_group_balance(self) -> dict[str, MuscleGroupStats]: ...
    def frequency(self) -> FrequencyStats: ...
```

The pitch was reasonable on its face: encapsulation, lazy computation with cache, idiomatic Python.

**Why I rejected it.**

1. **It moves the user-isolation invariant from a structural property to a code-review property.** A `StatsEngine` instance holds `self.history` as instance state. The moment that instance is reused across requests — through FastAPI's `Depends(...)`, a module-level cache, a singleton — user A's history reaches user B's analysis path. Isolation now depends on every future contributor remembering not to inject the class as a singleton. The brief explicitly flags data isolation as a critical evaluation criterion; designing in a way that requires vigilance to maintain it is the wrong default.

2. **The functional alternative makes isolation a type-signature property.**
   ```python
   def compute_per_exercise(history: list[WorkoutEntry]) -> dict[str, ExerciseStats]: ...
   def compute_muscle_group_balance(history: list[WorkoutEntry]) -> dict[str, MuscleGroupStats]: ...
   def compute_frequency(history: list[WorkoutEntry]) -> FrequencyStats: ...
   ```
   No instance state. The function physically cannot see history that wasn't passed in. The `test_user_isolation_deadlift_only_in_user_a` test in `tests/test_stats.py` passes not because the test is clever, but because the architecture makes the violation impossible to express without explicitly handing user A's history to user B's call — which never happens because every request carries its own list.

3. **The "encapsulation" benefit was illusory.** The class only bundled `history` with three functions that already shared `history` as their first argument. There was nothing else to encapsulate. The cache field was the only addition — and a per-request cache that gets thrown away after one call is just a local variable wearing a costume. If caching ever became load-bearing (it hasn't), `functools.lru_cache` on a hash of the history would add it in one line without instance state.

**What I did instead.**
Pure functions in `src/analysis/stats.py`. The module exports `compute_per_exercise`, `compute_muscle_group_balance`, `compute_frequency`, `filter_recent`. No classes, no shared mutable state, no caches.

**Why this matters more than a style preference.** Claude defaulted to OOP because that's what the bulk of its training data shows for "build a Python module with related computations." The right answer here required treating data isolation as a *design constraint that overrides idiomatic style*. That kind of judgment — "the idiom is wrong for this problem" — is exactly where AI needs a human in the loop. The Stage-1 alignment phase paid off here: because I'd already established data isolation as a hard constraint with Claude, when the OOP draft came through I could point at the constraint and Claude immediately understood the rewrite.

---

## Reflection on Guardrails: Did AI Help or Hinder?

**Both, in distinct phases — and the failure modes were exactly the two the brief asks about: too broad and too narrow.**

AI helped at the *generative* stage. Claude proposed five refusal categories that closely matched what the brief flagged (medical diagnosis, injury rehab without professional assessment, eating disorder, plus out-of-scope), wrote a calibrated JSON-mode prompt with a fail-open default to SAFE, and produced refusal templates that each named a specific professional to redirect to. That's a strong baseline — one I wouldn't have produced this cleanly in the same time from a blank slate.

AI hindered at the *calibration* stage, and it failed in both directions:

- **Too narrow (v1).** The first SAFE definition was "a legitimate fitness/exercise/training/workout question." `"hi there"` got refused as OUT_OF_SCOPE. The classifier was overfit to fitness vocabulary while the agent's own system prompt was permissive about greetings — the two were inconsistent and the user saw the stricter side.

- **Too broad (v2).** The EATING_DISORDER category was specified as "extreme caloric restriction, purging, body dysmorphia, rapid weight-loss tactics." Reasonable list — except "overtraining a muscle group" matched the loose pattern (training load + body part) and `"Am I overtraining chest vs back?"` got the dietitian redirect. The category absorbed an adjacent fitness term it shouldn't have.

Both failures came from prompts that *read sensibly in isolation* but had blind spots only visible when real inputs hit them. As a fitness-literate human I could see immediately why a coach would call the second one a false positive; the model couldn't, because "overtraining" lives near body-image terminology in its training distribution.

**The pattern I now follow:**
1. Let AI propose the schema and first-draft system prompt.
2. Run live smoke tests designed to brush each category boundary — explicitly checking both over-refusal AND under-refusal.
3. Rewrite the prompt only after the model surfaces a real miss; never edit defensively for hypothetical inputs.
4. Treat each prompt change like a code commit: version it, write the reason, pair it with the test that drove it.

Honest summary: AI gave me a 70%-correct guardrail in 10 minutes and a 100%-correct guardrail (15/15 eval pass) in 90 minutes. The 20-minute alignment phase at the start of the build meant I knew exactly *where* the blind spots were likely to be — at the boundary between fitness vocabulary and the sensitive-topic categories the brief cares about.

---

## What I Would Do Differently

- **Start eval earlier.** I trusted AI output too much in Phases 3–4 before having an eval baseline. Next time: write test cases before asking AI to code.

- **Automated prompt regression.** I caught prompt regressions manually via smoke tests. Should have wired the eval runner to run on every prompt change automatically.

- **Classifier ceiling.** Prompt engineering has a ceiling for a rule-based classifier. Given more time I'd replace it with a fine-tuned model on fitness-specific adversarial examples — the vocabulary overlap problem (overtraining, restriction, cutting) is too systematic for prompts to fully solve.

- **Alignment phase documentation.** The 11 interview questions Claude asked me in Phase A shaped the entire architecture — but I didn't save that conversation. Next time I'd commit the alignment transcript as `DECISIONS.md` so the reasoning is traceable.

---

## Commit History Evidence

The brief asks for iterative development with meaningful commit messages and evidence of reviewing AI output, not blind copy-paste. The repo's history shows ~20 commits, one per feature phase plus targeted fixes triggered by failures. Each commit message describes both *what* changed and *why* — and fixes name the failure that drove them.

Sampling of fix/refactor commits — the ones that prove I read and corrected AI output rather than accepting it:

| Commit | Type | Trigger |
|---|---|---|
| `a1affc7` | fix(guardrails) | Smoke test E4: "hi there" → refused. Rewrote SAFE to enumerate 5 sub-categories |
| `1cc6b0d` | fix(guardrails) | Eval baseline: "overtraining" → EATING_DISORDER. One-line disambiguation; analysis pass rate 60 → 100% |
| `acf344c` | fix(agent) | PDF John-bench multi-hop failed (rerank score 0.139). Added derived-fact rule for second hop |
| `8db6859` | fix(agent) | Eval regression on agent_02. Generalised multi-hop protocol + added coverage rule for recommendation questions |
| `a264abd` | refactor(analysis) | Removed LLM from `analyze_history` tool. Stats-only return cut latency ~57%, cost ~32% per analysis question |
| `9134909` | fix(ui) | Live test: user bubble stretching to max-width. Switched to inline `width: max-content` after Tailwind CDN missed dynamic classes |
| `19599a6` | config | Surfaced retrieval + LLM tunables to `.env` (top-k, threshold, temp, top_p) — initially set temp=0.1, eval regressed, reverted to 0.3 with the trade-off documented in the commit body |

Two design-level rejections also visible in the history:

- The `src/analysis/stats.py` module is pure functions, not a `StatsEngine` class — see the "rejected suggestion" section above. This was an architectural call before any code shipped, so it shows as the original commit, not as a revert.
- `src/api/routes_chat.py` has one `/chat` endpoint, not the separate `/rag` and `/analysis` endpoints Claude initially proposed.

History reads as iterative review-and-revision driven by real failures, not a single AI dump.
