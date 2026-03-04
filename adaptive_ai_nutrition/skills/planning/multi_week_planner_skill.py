"""
skills/planning/multi_week_planner_skill.py

MultiWeekPlannerSkill — Loops WeeklyMealPlanSkill across the full plan tenure.
Section 8.2 — Architecture document.
"""
from skills.base_skill import BaseSkill
from skills.planning.weekly_meal_plan_skill import WeeklyMealPlanSkill


class MultiWeekPlannerSkill(BaseSkill):
    """
    Generates a complete multi-week meal plan by looping WeeklyMealPlanSkill.
    Section 8.2 of the architecture document.
    """

    def __init__(self):
        self._weekly_skill = WeeklyMealPlanSkill()

    def execute(
        self,
        macro_targets: dict,
        diet_type: str = "omnivore",
        goal: str = "cut",
        weeks: int = 8,
        **_,
    ) -> dict:
        all_weeks = []
        for week_num in range(1, weeks + 1):
            week_plan = self._weekly_skill.execute(
                macro_targets=macro_targets,
                diet_type=diet_type,
                goal=goal,
                week_number=week_num,
            )
            all_weeks.append(week_plan)

        return {
            "total_weeks": weeks,
            "goal": goal,
            "diet_type": diet_type,
            "weeks": all_weeks,
        }
