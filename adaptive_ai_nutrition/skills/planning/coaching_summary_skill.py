"""
skills/planning/coaching_summary_skill.py

CoachingSummarySkill — Generates motivational coaching text via OpenAI GPT-4o mini.
"""
import os
from openai import OpenAI
from skills.base_skill import BaseSkill

_client   = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

COACHING_SYSTEM_PROMPT = """
You are a supportive, science-backed AI nutrition coach.
Be concise (under 150 words), warm, and data-driven.
Do not give medical advice. Do not encourage extreme restriction.
"""


class CoachingSummarySkill(BaseSkill):
    """
    Generates a natural-language coaching message from structured context.
    Section 8.3 of the architecture document.
    """

    def execute(
        self,
        user_name: str,
        goal: str,
        current_week: int,
        plateau_detected: bool,
        weight_delta_kg: float | None,
        adjustment_applied: float,
        **_,
    ) -> dict:
        plateau_text = ""
        if plateau_detected:
            plateau_text = (
                f"A plateau was detected (weight barely changed this week). "
                f"Calories were adjusted by {adjustment_applied:+.0f} kcal to break through it."
            )

        prompt = (
            f"User: {user_name}\n"
            f"Goal: {goal}\n"
            f"Current Week: {week_label(current_week)}\n"
            f"Weight change this week: {fmt_delta(weight_delta_kg)}\n"
            f"{plateau_text}\n\n"
            f"Write a brief, encouraging coaching message for this user."
        )

        response = _client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": COACHING_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.8,
            max_tokens=200,
        )
        return {"coaching_message": response.choices[0].message.content.strip()}


def week_label(week: int) -> str:
    return f"Week {week}"


def fmt_delta(delta: float | None) -> str:
    if delta is None:
        return "N/A"
    return f"{delta:+.2f} kg"
