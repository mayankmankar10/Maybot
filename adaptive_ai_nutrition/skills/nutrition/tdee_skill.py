"""
skills/nutrition/tdee_skill.py

TDEESkill — Mifflin-St Jeor Equation.
Pure deterministic function. No DB. No LLM.

Input schema:
    weight     (float) — kg
    height     (float) — cm
    age        (int)
    gender     (str)   — 'male' | 'female'
    activity_level (str) — sedentary | light | moderate | active | very_active

Output schema:
    bmr                  (float) — Base Metabolic Rate kcal/day
    maintenance_calories (float) — TDEE kcal/day
    activity_level       (str)
"""
from skills.base_skill import BaseSkill

ACTIVITY_MULTIPLIERS = {
    "sedentary":   1.2,
    "light":       1.375,
    "moderate":    1.55,
    "active":      1.725,
    "very_active": 1.9,
}


class TDEESkill(BaseSkill):
    """
    Calculates BMR and TDEE using the Mifflin-St Jeor equation.
    Section 7.1 of the architecture document.
    """

    def execute(
        self,
        weight: float,
        height: float,
        age: int,
        gender: str,
        activity_level: str,
        **_,
    ) -> dict:
        gender = gender.lower()
        activity_level = activity_level.lower()

        if gender not in ("male", "female"):
            raise ValueError(f"gender must be 'male' or 'female', got: {gender!r}")
        if activity_level not in ACTIVITY_MULTIPLIERS:
            raise ValueError(
                f"activity_level must be one of {list(ACTIVITY_MULTIPLIERS)}, got: {activity_level!r}"
            )
        if weight <= 0 or height <= 0 or age <= 0:
            raise ValueError("weight, height, and age must be positive numbers.")

        # Mifflin-St Jeor
        bmr = (10 * weight) + (6.25 * height) - (5 * age)
        bmr += 5 if gender == "male" else -161

        multiplier = ACTIVITY_MULTIPLIERS[activity_level]
        maintenance_calories = round(bmr * multiplier, 2)
        bmr = round(bmr, 2)

        return {
            "bmr": bmr,
            "maintenance_calories": maintenance_calories,
            "activity_level": activity_level,
        }
