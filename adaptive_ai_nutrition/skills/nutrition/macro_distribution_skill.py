"""
skills/nutrition/macro_distribution_skill.py

MacroDistributionSkill — Calculates protein, fat, carbs from calorie target.
Pure deterministic function. No DB. No LLM.

Rules (Section 7.3):
    Protein: 2.0 g/kg bodyweight for cut/bulk, 1.6 g/kg for maintain
    Fat:     25% of total daily calories (9 kcal/g)
    Carbs:   remaining calories after protein + fat (4 kcal/g)

Input schema:
    daily_calorie_target (float) — kcal/day
    current_weight       (float) — kg
    goal                 (str)   — cut | bulk | maintain

Output schema:
    protein_target_g (float)
    fats_target_g    (float)
    carbs_target_g   (float)
    protein_kcal     (float)
    fat_kcal         (float)
    carb_kcal        (float)
"""
from skills.base_skill import BaseSkill

PROTEIN_RATIO = {
    "cut":      2.0,
    "bulk":     2.0,
    "maintain": 1.6,
}


class MacroDistributionSkill(BaseSkill):
    """
    Distributes daily calories into protein, fat, and carbs.
    Section 7.3 of the architecture document.
    """

    def execute(
        self,
        daily_calorie_target: float,
        current_weight: float,
        goal: str,
        **_,
    ) -> dict:
        goal = goal.lower()

        if goal not in PROTEIN_RATIO:
            raise ValueError(f"goal must be one of {list(PROTEIN_RATIO)}, got: {goal!r}")
        if daily_calorie_target <= 0:
            raise ValueError("daily_calorie_target must be positive.")
        if current_weight <= 0:
            raise ValueError("current_weight must be positive.")

        # Protein
        protein_g = round(PROTEIN_RATIO[goal] * current_weight, 1)
        protein_kcal = round(protein_g * 4, 1)

        # Fat: 25% of total calories
        fat_kcal = round(daily_calorie_target * 0.25, 1)
        fat_g = round(fat_kcal / 9, 1)

        # Carbs: remainder
        carb_kcal = round(daily_calorie_target - protein_kcal - fat_kcal, 1)
        carb_g = round(carb_kcal / 4, 1)

        if carb_g < 0:
            raise ValueError(
                "Carbohydrate target is negative — calorie target is too low "
                "to accommodate protein and fat requirements."
            )

        return {
            "protein_target_g": protein_g,
            "fats_target_g": fat_g,
            "carbs_target_g": carb_g,
            "protein_kcal": protein_kcal,
            "fat_kcal": fat_kcal,
            "carb_kcal": carb_kcal,
        }
