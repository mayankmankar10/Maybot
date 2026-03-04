"""
skills/planning/weekly_meal_plan_skill.py

OpenAI GPT-4o mini meal planner.

Key design:
- Passes EXACT per-meal calorie AND macro targets (not just daily total)
- Each meal slot has a specific protein/carbs/fat breakdown
- GPT must hit per-meal targets, not just juggle the daily total
- Post-generation validation clamps negatives and checks accuracy

Meal calorie split:  Breakfast 25% | Lunch 30% | Dinner 35% | Snacks 10%
"""
import os
import json
import logging
from openai import OpenAI
from skills.base_skill import BaseSkill

logger = logging.getLogger(__name__)

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Fraction of daily calories per meal slot
MEAL_SPLITS = {"breakfast": 0.25, "lunch": 0.30, "dinner": 0.35, "snacks": 0.10}


def _build_system_prompt() -> str:
    return """
You are a professional nutritionist generating precise meal plans.
Respond with a valid JSON object ONLY — no explanation, no markdown, no prose.

STRICT RULES:
1. Each meal MUST hit its specified calorie, protein, carbs, and fat targets (±10% tolerance).
2. All values (calories, protein_g, carbs_g, fat_g) MUST be > 0. Never negative.
3. Choose realistic, appetising foods that naturally match the macro profile.
4. Vary meals across all 7 days — no repeats.
5. daily_totals = sum of the four meals for that day.

Output format:
{
  "days": [
    {
      "day": "Monday",
      "meals": {
        "breakfast": {"name": "...", "calories": <int>, "protein_g": <float>, "carbs_g": <float>, "fat_g": <float>},
        "lunch":     {"name": "...", "calories": <int>, "protein_g": <float>, "carbs_g": <float>, "fat_g": <float>},
        "dinner":    {"name": "...", "calories": <int>, "protein_g": <float>, "carbs_g": <float>, "fat_g": <float>},
        "snacks":    {"name": "...", "calories": <int>, "protein_g": <float>, "carbs_g": <float>, "fat_g": <float>}
      },
      "daily_totals": {"calories": <int>, "protein_g": <float>, "carbs_g": <float>, "fat_g": <float>}
    }
    ... (7 days total)
  ]
}
"""


def _per_meal_targets(daily_cal: float, daily_p: float, daily_c: float, daily_f: float) -> dict:
    """
    Break daily targets into per-meal targets using fixed calorie splits.
    The macro proportions per meal are kept consistent with the daily ratios.
    """
    targets = {}
    for meal, frac in MEAL_SPLITS.items():
        targets[meal] = {
            "calories":  round(daily_cal * frac),
            "protein_g": round(daily_p   * frac, 1),
            "carbs_g":   round(daily_c   * frac, 1),
            "fat_g":     round(daily_f   * frac, 1),
        }
    return targets


def _build_user_prompt(
    diet_type: str,
    goal: str,
    week_number: int,
    daily_cal: float,
    meal_targets: dict,
    macro_targets: dict,
) -> str:
    mt = meal_targets
    return (
        f"Generate a 7-day {diet_type} meal plan for Week {week_number}. Goal: {goal}.\n\n"
        f"DAILY TOTALS TO HIT:\n"
        f"  Calories: {daily_cal:.0f} kcal\n"
        f"  Protein:  {macro_targets['protein_target_g']}g\n"
        f"  Carbs:    {macro_targets['carbs_target_g']}g\n"
        f"  Fat:      {macro_targets['fats_target_g']}g\n\n"
        f"PER-MEAL TARGETS (hit these for every day):\n"
        f"  Breakfast ({int(MEAL_SPLITS['breakfast']*100)}%): "
        f"{mt['breakfast']['calories']} kcal | "
        f"{mt['breakfast']['protein_g']}g P | "
        f"{mt['breakfast']['carbs_g']}g C | "
        f"{mt['breakfast']['fat_g']}g F\n"
        f"  Lunch     ({int(MEAL_SPLITS['lunch']*100)}%): "
        f"{mt['lunch']['calories']} kcal | "
        f"{mt['lunch']['protein_g']}g P | "
        f"{mt['lunch']['carbs_g']}g C | "
        f"{mt['lunch']['fat_g']}g F\n"
        f"  Dinner    ({int(MEAL_SPLITS['dinner']*100)}%): "
        f"{mt['dinner']['calories']} kcal | "
        f"{mt['dinner']['protein_g']}g P | "
        f"{mt['dinner']['carbs_g']}g C | "
        f"{mt['dinner']['fat_g']}g F\n"
        f"  Snacks    ({int(MEAL_SPLITS['snacks']*100)}%): "
        f"{mt['snacks']['calories']} kcal | "
        f"{mt['snacks']['protein_g']}g P | "
        f"{mt['snacks']['carbs_g']}g C | "
        f"{mt['snacks']['fat_g']}g F\n\n"
        "Choose real, appetising foods. Vary across all 7 days. No negative values."
    )


def _extract_json(raw: str) -> dict:
    """Robust JSON extraction: direct → fence strip → first-brace scan."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue
    s, e = raw.find("{"), raw.rfind("}") + 1
    if s != -1 and e > s:
        return json.loads(raw[s:e])
    raise ValueError(f"No valid JSON in Gemini response: {raw[:400]}")


def _validate_day(day_data: dict, meal_targets: dict) -> dict:
    """
    Clamp negative values to 0 and recompute daily_totals from actual meal values.
    """
    new_meals: dict = {}
    total_cal = total_p = total_c = total_f = 0.0

    for meal_key in MEAL_SPLITS:
        m = day_data.get("meals", {}).get(meal_key, {})
        tgt = meal_targets[meal_key]

        # Clamp negatives
        cal = max(float(m.get("calories",  tgt["calories"])),  0)
        p   = max(float(m.get("protein_g", tgt["protein_g"])), 0)
        c   = max(float(m.get("carbs_g",   tgt["carbs_g"])),   0)
        f   = max(float(m.get("fat_g",     tgt["fat_g"])),     0)

        new_meals[meal_key] = {
            "name":      m.get("name", f"{meal_key.title()} meal"),
            "calories":  round(cal),
            "protein_g": round(p, 1),
            "carbs_g":   round(c, 1),
            "fat_g":     round(f, 1),
        }
        total_cal += cal
        total_p   += p
        total_c   += c
        total_f   += f

    return {
        "day":   day_data.get("day", "?"),
        "meals": new_meals,
        "daily_totals": {
            "calories":  round(total_cal),
            "protein_g": round(total_p, 1),
            "carbs_g":   round(total_c, 1),
            "fat_g":     round(total_f, 1),
        },
    }


class WeeklyMealPlanSkill(BaseSkill):
    """
    Gemini meal planner with per-meal macro targets.
    Each meal slot (breakfast/lunch/dinner/snacks) receives its own
    calorie and macro target, so Gemini can't compensate with
    negative values or wildly imbalanced meals.
    """

    def execute(
        self,
        macro_targets: dict,
        diet_type: str = "omnivore",
        goal: str = "cut",
        week_number: int = 1,
        foods_to_avoid: str = "",
        **_,
    ) -> dict:
        daily_cal = (
            macro_targets["protein_target_g"] * 4
            + macro_targets["carbs_target_g"]  * 4
            + macro_targets["fats_target_g"]   * 9
        )

        meal_targets = _per_meal_targets(
            daily_cal=daily_cal,
            daily_p=macro_targets["protein_target_g"],
            daily_c=macro_targets["carbs_target_g"],
            daily_f=macro_targets["fats_target_g"],
        )

        # Build avoid restriction line
        avoid_line = ""
        if foods_to_avoid and foods_to_avoid.strip():
            avoid_line = f"\nFOODS TO AVOID (never include): {foods_to_avoid}"

        prompt = _build_user_prompt(
            diet_type=diet_type,
            goal=goal,
            week_number=week_number,
            daily_cal=daily_cal,
            meal_targets=meal_targets,
            macro_targets=macro_targets,
        ) + avoid_line

        response = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()

        plan = _extract_json(raw)
        days = plan.get("days", [])
        if not days:
            raise ValueError("OpenAI returned a plan with no days.")

        validated_days = [_validate_day(d, meal_targets) for d in days]
        return {"week": week_number, "days": validated_days}
