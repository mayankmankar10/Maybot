"""
skills/adaptation/plateau_detection_skill.py

PlateauDetectionSkill — Detects weight plateau based on recent weekly logs.
Pure deterministic function. No DB. No LLM.

Rules (Section 7.5):
    Plateau if ALL of:
      1. Last 2 weeks weight change < 0.2 kg (absolute)
      2. Adherence ≥ 80% in both weeks
      3. Goal is 'cut' or 'bulk'

Input schema:
    goal         (str)       — cut | bulk | maintain
    weekly_logs  (list[dict]) — last N weekly logs, each:
                               { week_number, logged_weight, adherence_percentage }

Output schema:
    plateau_detected (bool)
    reason           (str)   — human-readable explanation
    weight_delta_kg  (float | None) — absolute change between last 2 weights
"""
from skills.base_skill import BaseSkill

PLATEAU_WEIGHT_THRESHOLD_KG = 0.2
PLATEAU_ADHERENCE_THRESHOLD = 80.0
PLATEAU_ELIGIBLE_GOALS = {"cut", "bulk"}


class PlateauDetectionSkill(BaseSkill):
    """
    Detects a physiological plateau from recent weekly log data.
    Section 7.5 of the architecture document.
    """

    def execute(
        self,
        goal: str,
        weekly_logs: list,
        **_,
    ) -> dict:
        goal = goal.lower()

        if goal not in PLATEAU_ELIGIBLE_GOALS | {"maintain"}:
            raise ValueError(f"goal must be one of cut | bulk | maintain, got: {goal!r}")

        # Maintain goal never plateaus by definition
        if goal == "maintain":
            return {
                "plateau_detected": False,
                "reason": "Plateau detection not applicable for 'maintain' goal.",
                "weight_delta_kg": None,
            }

        if len(weekly_logs) < 2:
            return {
                "plateau_detected": False,
                "reason": "Insufficient data: need at least 2 weeks of logs.",
                "weight_delta_kg": None,
            }

        # Sort by week number descending, take last 2
        sorted_logs = sorted(weekly_logs, key=lambda x: x["week_number"], reverse=True)
        recent = sorted_logs[:2]   # [most_recent, one_before]

        w1 = float(recent[0]["logged_weight"])
        w2 = float(recent[1]["logged_weight"])
        a1 = float(recent[0]["adherence_percentage"])
        a2 = float(recent[1]["adherence_percentage"])

        weight_delta = abs(w1 - w2)
        low_adherence = a1 < PLATEAU_ADHERENCE_THRESHOLD or a2 < PLATEAU_ADHERENCE_THRESHOLD

        if weight_delta >= PLATEAU_WEIGHT_THRESHOLD_KG:
            return {
                "plateau_detected": False,
                "reason": f"Weight changed by {weight_delta:.2f} kg — no plateau.",
                "weight_delta_kg": round(weight_delta, 3),
            }

        if low_adherence:
            return {
                "plateau_detected": False,
                "reason": (
                    f"Weight stalled but adherence is below 80% "
                    f"(week {recent[0]['week_number']}: {a1}%, "
                    f"week {recent[1]['week_number']}: {a2}%). "
                    "Not a true plateau."
                ),
                "weight_delta_kg": round(weight_delta, 3),
            }

        return {
            "plateau_detected": True,
            "reason": (
                f"Plateau confirmed: weight change {weight_delta:.2f} kg < {PLATEAU_WEIGHT_THRESHOLD_KG} kg "
                f"with adherence {a1}% and {a2}% (both ≥ 80%)."
            ),
            "weight_delta_kg": round(weight_delta, 3),
        }
