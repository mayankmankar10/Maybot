"""
skills/nutrition/usda_lookup.py

USDA FoodData Central integration — improved version.
Key fixes over v1:
  - Includes "Survey (FNDDS)" data type which has composite meals
  - Cleans query to key food terms before searching
  - Validates match relevance (shared keywords)
  - Falls back to next result if first match is irrelevant

Free API — https://fdc.nal.usda.gov/api-guide.html
"""
import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

USDA_API_KEY = os.getenv("USDA_API_KEY", "")
USDA_BASE    = "https://api.nal.usda.gov/fdc/v1"

# Survey (FNDDS) = composite meals (chicken salad, scrambled eggs, etc.)
# Foundation / SR Legacy = raw ingredients (fallback)
_DATA_TYPES = ["Survey (FNDDS)", "Foundation", "SR Legacy", "Branded"]

# USDA nutrient IDs
_NUTRIENT_IDS = {
    "calories":  1008,   # Energy (kcal)
    "protein_g": 1003,   # Protein
    "carbs_g":   1005,   # Carbohydrate, by difference
    "fat_g":     1004,   # Total lipid (fat)
}

# Meal calorie distribution
MEAL_SPLITS = {
    "breakfast": 0.25,
    "lunch":     0.30,
    "dinner":    0.35,
    "snacks":    0.10,
}

# Cooking/prep adjectives to strip before USDA search
_STRIP_WORDS = {
    "baked", "grilled", "roasted", "steamed", "fried", "sautéed", "sauteed",
    "boiled", "raw", "cooked", "fresh", "mixed", "homemade", "stuffed",
    "sliced", "diced", "chopped", "whole", "organic", "lean", "low-fat",
    "high-protein", "with", "and", "on", "over", "topped", "drizzled",
    "a", "an", "the", "side", "of", "in",
}


def _clean_query(meal_name: str) -> str:
    """
    Convert a descriptive meal name to a cleaner USDA search term.
    E.g. "Baked Salmon with Roasted Asparagus and Quinoa" → "salmon asparagus quinoa"
    Takes up to the first 4 meaningful words.
    """
    words = re.sub(r"[^\w\s]", "", meal_name.lower()).split()
    key_words = [w for w in words if w not in _STRIP_WORDS]
    return " ".join(key_words[:4]).strip() or meal_name


def _relevance_score(query: str, food_name: str) -> int:
    """Count how many query keywords appear in the USDA food name."""
    qwords = set(re.sub(r"[^\w\s]", "", query.lower()).split())
    fname  = re.sub(r"[^\w\s]", "", food_name.lower())
    return sum(1 for w in qwords if w in fname and len(w) > 2)


def _extract_macros_per_100g(food: dict) -> dict:
    """Pull macros per 100 g from a USDA food search result."""
    idx = {
        n.get("nutrientId"): n.get("value", 0)
        for n in food.get("foodNutrients", [])
    }
    return {key: float(idx.get(nid, 0)) for key, nid in _NUTRIENT_IDS.items()}


def lookup_meal(meal_name: str, target_calories: float) -> dict:
    """
    Search USDA for the meal, pick the most relevant result,
    and scale the portion to `target_calories`.
    """
    query = _clean_query(meal_name)
    foods = []
    try:
        resp = requests.get(
            f"{USDA_BASE}/foods/search",
            params={
                "query":    query,
                "api_key":  USDA_API_KEY,
                "pageSize": 10,
                "dataType": _DATA_TYPES,
            },
            timeout=7,
        )
        resp.raise_for_status()
        foods = resp.json().get("foods", [])
    except Exception as exc:
        logger.warning("USDA search failed for %r (query=%r): %s", meal_name, query, exc)

    # Pick the most relevant food (highest keyword overlap)
    best_food = None
    best_score = -1
    for food in foods:
        score = _relevance_score(query, food.get("description", ""))
        if score > best_score:
            best_score = score
            best_food  = food

    if not best_food or best_score == 0:
        logger.info("USDA: no relevant match for %r (query=%r) — using fallback", meal_name, query)
        return _fallback(meal_name, target_calories)

    per100 = _extract_macros_per_100g(best_food)
    cal100 = per100["calories"]
    if cal100 <= 0:
        return _fallback(meal_name, target_calories)

    scale = target_calories / cal100
    return {
        "name":      best_food.get("description", meal_name).title(),
        "calories":  round(target_calories),
        "protein_g": round(max(per100["protein_g"] * scale, 0), 1),
        "carbs_g":   round(max(per100["carbs_g"]   * scale, 0), 1),
        "fat_g":     round(max(per100["fat_g"]      * scale, 0), 1),
    }


def _fallback(meal_name: str, target_calories: float) -> dict:
    """Proportional macro estimate when USDA match is unavailable."""
    return {
        "name":      meal_name,
        "calories":  round(target_calories),
        "protein_g": round(target_calories * 0.25 / 4, 1),
        "carbs_g":   round(target_calories * 0.45 / 4, 1),
        "fat_g":     round(target_calories * 0.30 / 9, 1),
    }


def enrich_plan_with_usda(days: list[dict], daily_cal: float) -> list[dict]:
    """
    Given a Gemini names-only plan, concurrently fetch USDA macros for every
    meal and return a fully-populated plan with accurate per-meal and daily totals.
    """
    tasks = []
    for di, day_data in enumerate(days):
        for meal_key, frac in MEAL_SPLITS.items():
            name = day_data.get("meals", {}).get(meal_key, "")
            if name and isinstance(name, str):
                tasks.append((di, meal_key, name, daily_cal * frac))

    results: dict[tuple, dict] = {}
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="usda") as pool:
        futures = {
            pool.submit(lookup_meal, name, tgt): (di, meal_key)
            for di, meal_key, name, tgt in tasks
        }
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception as exc:
                di, meal_key = key
                logger.error("USDA enrich failed (%s, %s): %s", di, meal_key, exc)

    enriched = []
    for di, day_data in enumerate(days):
        new_meals: dict = {}
        total_cal = total_p = total_c = total_f = 0.0

        for meal_key in MEAL_SPLITS:
            macro = results.get((di, meal_key))
            if macro:
                new_meals[meal_key] = macro
                total_cal += macro["calories"]
                total_p   += macro["protein_g"]
                total_c   += macro["carbs_g"]
                total_f   += macro["fat_g"]
            else:
                new_meals[meal_key] = {
                    "name":      day_data.get("meals", {}).get(meal_key, "—"),
                    "calories":  0, "protein_g": 0, "carbs_g": 0, "fat_g": 0,
                }

        enriched.append({
            "day":   day_data.get("day", f"Day {di + 1}"),
            "meals": new_meals,
            "daily_totals": {
                "calories":  round(total_cal),
                "protein_g": round(total_p, 1),
                "carbs_g":   round(total_c, 1),
                "fat_g":     round(total_f, 1),
            },
        })

    return enriched
