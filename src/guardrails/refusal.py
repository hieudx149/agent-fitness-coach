"""Refusal templates — one per blocked category, each with a professional redirect.

We deliberately do NOT just say "I can't help with that". Each refusal:
  1. Names what we won't do and why,
  2. Points to the right kind of professional, and
  3. Offers an adjacent topic we CAN help with — so the user is not stuck.
"""
from src.guardrails.classifier import Category

_TEMPLATES: dict[Category, str] = {
    Category.MEDICAL_DIAGNOSIS: (
        "I can't diagnose medical conditions. If you're experiencing concerning symptoms, please "
        "consult a licensed physician — they can properly evaluate you and rule out serious causes. "
        "Once you have medical clearance, I'm happy to discuss training principles, exercise "
        "technique, or programming."
    ),
    Category.INJURY_REHAB: (
        "I can't recommend a personalized rehab plan — recovering from an injury requires hands-on "
        "assessment from a licensed physiotherapist, athletic trainer, or sports medicine doctor. "
        "They can determine the right exercises, dosage, and progression for your specific situation. "
        "I can help with injury prevention (form cues, warm-ups, programming) if that's useful."
    ),
    Category.EATING_DISORDER: (
        "What you're describing sounds like it could benefit from professional support. A registered "
        "dietitian or a mental health professional specializing in eating concerns can help you build "
        "a sustainable approach. If you're in crisis, please reach out to a local helpline. I'm here "
        "to talk about training and balanced nutrition once you have that support in place."
    ),
    Category.OUT_OF_SCOPE: (
        "I'm a fitness coaching assistant — I can help with training, exercise technique, workout "
        "programming, recovery, and nutrition fundamentals. Your question seems outside that scope. "
        "Is there a fitness-related question I can help with instead?"
    ),
}


def refusal_message(category: Category) -> str:
    if category == Category.SAFE:
        raise ValueError("refusal_message() called for SAFE category — nothing to refuse")
    return _TEMPLATES[category]
