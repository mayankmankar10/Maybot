"""
tests/test_macro_distribution_skill.py
Unit tests for MacroDistributionSkill.
"""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.nutrition.macro_distribution_skill import MacroDistributionSkill

skill = MacroDistributionSkill()


class TestMacroProtein:
    def test_cut_uses_2g_per_kg(self):
        r = skill.execute(daily_calorie_target=2000, current_weight=80, goal="cut")
        assert r["protein_target_g"] == pytest.approx(160.0)   # 2.0 * 80

    def test_bulk_uses_2g_per_kg(self):
        r = skill.execute(daily_calorie_target=2800, current_weight=75, goal="bulk")
        assert r["protein_target_g"] == pytest.approx(150.0)   # 2.0 * 75

    def test_maintain_uses_1_6g_per_kg(self):
        r = skill.execute(daily_calorie_target=2500, current_weight=70, goal="maintain")
        assert r["protein_target_g"] == pytest.approx(112.0)   # 1.6 * 70


class TestMacroFat:
    def test_fat_is_25_percent_of_calories(self):
        r = skill.execute(daily_calorie_target=2000, current_weight=80, goal="cut")
        # 25% of 2000 = 500 kcal / 9 = 55.6g
        assert r["fat_kcal"] == pytest.approx(500.0)
        assert r["fats_target_g"] == pytest.approx(55.6, abs=0.1)


class TestMacroCarbs:
    def test_carbs_are_remainder(self):
        r = skill.execute(daily_calorie_target=2000, current_weight=80, goal="cut")
        total_accounted = r["protein_kcal"] + r["fat_kcal"] + r["carb_kcal"]
        assert total_accounted == pytest.approx(2000.0, abs=1.0)

    def test_negative_carbs_raises(self):
        # Very low calories with heavy person → negative carbs
        with pytest.raises(ValueError, match="negative"):
            skill.execute(daily_calorie_target=800, current_weight=120, goal="cut")


class TestMacroValidation:
    def test_invalid_goal_raises(self):
        with pytest.raises(ValueError, match="goal"):
            skill.execute(daily_calorie_target=2000, current_weight=80, goal="lose")

    def test_zero_weight_raises(self):
        with pytest.raises(ValueError):
            skill.execute(daily_calorie_target=2000, current_weight=0, goal="cut")

    def test_output_keys_present(self):
        r = skill.execute(daily_calorie_target=2200, current_weight=75, goal="cut")
        for key in ("protein_target_g", "fats_target_g", "carbs_target_g", "protein_kcal", "fat_kcal", "carb_kcal"):
            assert key in r
