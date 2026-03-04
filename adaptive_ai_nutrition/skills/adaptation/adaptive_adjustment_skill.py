"""
skills/adaptation/adaptive_adjustment_skill.py

AdaptiveAdjustmentSkill — Adjusts calorie target when a plateau is detected.
Pure deterministic function. No DB. No LLM.

Rules (Section 7.6):
    If plateau:
        cut      → -150 kcal
        bulk     → +100 kcal
        maintain → minimal (0) adjustment

    Safety constraints:
        - new target must NEVER go below BMR
        - new target must NEVER exceed BMR × 1.9 (very_active TDEE as safe ceiling)

Input schema:
    plateau_detected     (bool)
    goal                 (str)   — cut | bulk | maintain
    daily_calorie_target (float) — current target kcal/day
    bmr                  (float) — from TDEESkill output (safety floor)

Output schema:
    new_calorie_target  (float)
    adjustment_applied  (int)   — signed kcal change
    safety_clipped      (bool)  — True if safety floor/ceiling was enforced
    reason              (str)
"""
from skills.base_skill import BaseSkill

PLATEAU_ADJUSTMENTS = {
    "cut":      -150,
    "bulk":     +100,
    "maintain":    0,
}

SAFE_SURPLUS_MULTIPLIER = 1.9   # very_active TDEE ceiling


class AdaptiveAdjustmentSkill(BaseSkill):
    """
    Applies a calorie adjustment when a plateau is detected.
    Safety rules ensure we never go below BMR or exceed a safe surplus.
    Section 7.6 of the architecture document.
    """

    def execute(
        self,
        plateau_detected: bool,
        goal: str,
        daily_calorie_target: float,
        bmr: float,
        **_,
    ) -> dict:
        goal = goal.lower()

        if goal not in PLATEAU_ADJUSTMENTS:
            raise ValueError(f"goal must be one of {list(PLATEAU_ADJUSTMENTS)}, got: {goal!r}")
        if bmr <= 0:
            raise ValueError("bmr must be a positive number.")
        if daily_calorie_target <= 0:
            raise ValueError("daily_calorie_target must be a positive number.")

        if not plateau_detected:
            return {
                "new_calorie_target": daily_calorie_target,
                "adjustment_applied": 0,
                "safety_clipped": False,
                "reason": "No plateau detected — calorie target unchanged.",
            }

        adjustment = PLATEAU_ADJUSTMENTS[goal]
        proposed = daily_calorie_target + adjustment
        safety_clipped = False

        # Safety floor: never go below BMR
        if proposed < bmr:
            proposed = bmr
            safety_clipped = True

        # Safety ceiling: never exceed very_active TDEE
        safe_ceiling = round(bmr * SAFE_SURPLUS_MULTIPLIER, 2)
        if proposed > safe_ceiling:
            proposed = safe_ceiling
            safety_clipped = True

        proposed = round(proposed, 2)
        actual_adjustment = round(proposed - daily_calorie_target, 2)

        reason = (
            f"Plateau detected for goal='{goal}'. "
            f"Applied {adjustment:+d} kcal adjustment."
        )
        if safety_clipped:
            reason += " Safety constraint enforced (BMR floor or surplus ceiling)."

        return {
            "new_calorie_target": proposed,
            "adjustment_applied": actual_adjustment,
            "safety_clipped": safety_clipped,
            "reason": reason,
        }
