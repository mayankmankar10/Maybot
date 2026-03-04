"""
skills/nutrition/calorie_target_skill.py

CalorieTargetSkill — Applies goal + intensity offset to maintenance calories.
Pure deterministic function. No DB. No LLM.

Input schema:
    maintenance_calories (float)
    goal                 (str) — cut | bulk | maintain
    goal_intensity       (str) — conservative | balanced | aggressive

Output schema:
    daily_calorie_target (float)
    calorie_adjustment   (int)   — signed offset applied
    goal                 (str)
    goal_intensity       (str)
"""
from skills.base_skill import BaseSkill

# Calorie adjustments derived from chosen weekly rate:
# kcal/day = rate_kg_week × 7700 kcal/kg ÷ 7 days
#
# CUT rates shown in setup:  0.25 | 0.50 | 1.00 kg/week
# BULK rates shown in setup:  0.10 | 0.25 | 0.50 kg/week
GOAL_OFFSETS = {
    "cut": {
        "conservative": -275,   # 0.25 kg/week × 7700 ÷ 7 ≈ 275
        "balanced":     -550,   # 0.50 kg/week × 7700 ÷ 7 ≈ 550
        "aggressive":   -1000,  # 1.00 kg/week (safety-capped at -1000)
    },
    "bulk": {
        "conservative": +110,   # 0.10 kg/week lean bulk
        "balanced":     +275,   # 0.25 kg/week moderate bulk
        "aggressive":   +550,   # 0.50 kg/week aggressive bulk
    },
    "maintain": {
        "conservative": 0,
        "balanced":     0,
        "aggressive":   0,
    },
}


class CalorieTargetSkill(BaseSkill):
    """
    Calculates the daily calorie target from maintenance calories,
    applying the appropriate offset for the user's goal and intensity.
    Section 7.2 of the architecture document.
    """

    def execute(
        self,
        maintenance_calories: float,
        goal: str,
        goal_intensity: str,
        **_,
    ) -> dict:
        goal = goal.lower()
        goal_intensity = goal_intensity.lower()

        if goal not in GOAL_OFFSETS:
            raise ValueError(f"goal must be one of {list(GOAL_OFFSETS)}, got: {goal!r}")
        if goal_intensity not in GOAL_OFFSETS[goal]:
            raise ValueError(
                f"goal_intensity must be one of {list(GOAL_OFFSETS[goal])}, got: {goal_intensity!r}"
            )
        if maintenance_calories <= 0:
            raise ValueError("maintenance_calories must be a positive number.")

        offset = GOAL_OFFSETS[goal][goal_intensity]
        target = round(maintenance_calories + offset, 2)

        return {
            "daily_calorie_target": target,
            "calorie_adjustment": offset,
            "goal": goal,
            "goal_intensity": goal_intensity,
        }
