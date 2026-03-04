"""
skills/projection/weight_projection_skill.py

WeightProjectionSkill — Projects weekly weight over the plan tenure.
Pure deterministic function. No DB. No LLM.

Formula (Section 7.4):
    1 kg fat ≈ 7700 kcal
    weekly_deficit = daily_calorie_target - maintenance_calories
    weekly_weight_change_kg = weekly_deficit / 7700

Input schema:
    current_weight       (float) — kg
    daily_calorie_target (float) — kcal/day
    maintenance_calories (float) — kcal/day
    weeks                (int)   — plan duration

Output schema:
    weekly_weight_change_kg (float)
    projections             (list[dict]) — [{week: int, projected_weight: float}]
"""
from skills.base_skill import BaseSkill

KCAL_PER_KG_FAT = 7700.0


class WeightProjectionSkill(BaseSkill):
    """
    Projects user weight week-by-week over the plan duration.
    Section 7.4 of the architecture document.
    """

    def execute(
        self,
        current_weight: float,
        daily_calorie_target: float,
        maintenance_calories: float,
        weeks: int = 8,
        **_,
    ) -> dict:
        if current_weight <= 0:
            raise ValueError("current_weight must be positive.")
        if weeks <= 0:
            raise ValueError("weeks must be a positive integer.")

        # Positive = surplus (bulk), Negative = deficit (cut)
        weekly_calorie_balance = (daily_calorie_target - maintenance_calories) * 7
        weekly_weight_change_kg = round(weekly_calorie_balance / KCAL_PER_KG_FAT, 3)

        projections = []
        weight = current_weight
        for week in range(1, weeks + 1):
            weight = round(weight + weekly_weight_change_kg, 2)
            projections.append({"week": week, "projected_weight": weight})

        return {
            "weekly_weight_change_kg": weekly_weight_change_kg,
            "projections": projections,
        }
