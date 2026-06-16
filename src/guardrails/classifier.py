"""Input safety + scope classifier.

Runs once per request before the Coach Agent. Calibrated to err on
SAFE — over-blocking legitimate fitness questions is a worse failure
mode than the occasional borderline case slipping through (which the
agent's grounded answers further mitigate).

Categories were chosen to mirror the PDF's three explicit refusal
triggers (medical diagnosis, injury rehab without professional
assessment, eating-disorder risk content) plus the required
out-of-scope check.
"""
import json
import logging
from dataclasses import dataclass
from enum import Enum

from src.config import get_settings
from src.llm.openai_client import get_openai_client

logger = logging.getLogger(__name__)


class Category(str, Enum):
    SAFE = "SAFE"
    MEDICAL_DIAGNOSIS = "MEDICAL_DIAGNOSIS"
    INJURY_REHAB = "INJURY_REHAB"
    EATING_DISORDER = "EATING_DISORDER"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass
class ClassificationResult:
    category: Category
    reason: str
    raw_message: str

    @property
    def is_safe(self) -> bool:
        return self.category == Category.SAFE


SYSTEM_PROMPT = """You are a safety classifier for an AI fitness coach. Classify each user message into exactly one category.

Categories:
- SAFE includes:
  (a) Any fitness/exercise/training/workout/nutrition question — technique, programming, principles, common mistakes, general injury prevention, recovery basics, supplementation basics, eating habits for athletes.
  (b) Greetings and small talk — "hi", "hello", "thanks", "how are you", "good morning".
  (c) Meta-conversation about the assistant — "what can you help with?", "who are you?", "what can you do?".
  (d) Clarification or follow-up questions in an ongoing fitness conversation.
  (e) Personal-data questions about the user's OWN training history — trends, neglected work, readiness to progress.
- MEDICAL_DIAGNOSIS: The user describes their own symptoms and asks what condition they have, or requests a medical diagnosis. (Example: "Why does my chest hurt at night?")
- INJURY_REHAB: The user describes a personal injury and asks how to treat or rehabilitate it. (Example: "I tore my rotator cuff, how do I rehab it?") Questions about how to PREVENT injuries through proper form or programming are SAFE, not INJURY_REHAB.
- EATING_DISORDER: The user mentions extreme caloric restriction (e.g. eating 500 kcal/day), purging behaviors, body dysmorphia (hating one's body / wanting to disappear), or asks for rapid weight loss tactics that signal disordered eating. IMPORTANT: questions about training volume balance, "overtraining" a muscle group, or muscle imbalance are about TRAINING LOAD, not eating — they are SAFE, not EATING_DISORDER.
- OUT_OF_SCOPE: The question has nothing to do with fitness, training, nutrition, OR being a normal conversational interaction. Examples: "What's the weather today?", "Write me a Python script", "Tell me a joke about cars".

Output strict JSON only: {"category": "<CATEGORY>", "reason": "<one-sentence reason>"}

Be calibrated. Do NOT block legitimate fitness questions or normal conversational exchanges. When uncertain, return SAFE."""


async def classify(message: str) -> ClassificationResult:
    settings = get_settings()
    client = get_openai_client()

    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
        max_tokens=120,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()

    try:
        data = json.loads(raw)
        category = Category(data["category"])
        reason = data.get("reason", "")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        # Fail-open: defaulting to SAFE on classifier failure beats over-blocking real questions
        logger.warning("Classifier returned unparseable response: %r (%s)", raw, exc)
        category = Category.SAFE
        reason = "Classifier failure — defaulting to SAFE"

    return ClassificationResult(category=category, reason=reason, raw_message=message)
