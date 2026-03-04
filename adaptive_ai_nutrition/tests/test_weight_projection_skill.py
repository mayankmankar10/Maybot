"""
tests/test_weight_projection_skill.py
Unit tests for WeightProjectionSkill.
"""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.projection.weight_projection_skill import WeightProjectionSkill

skill = WeightProjectionSkill()


class TestProjectionLength:
    def test_8_week_default_produces_8_entries(self):
        r = skill.execute(current_weight=80, daily_calorie_target=2000, maintenance_calories=2500, weeks=8)
        assert len(r["projections"]) == 8

    def test_custom_weeks(self):
        r = skill.execute(current_weight=80, daily_calorie_target=2000, maintenance_calories=2500, weeks=12)
        assert len(r["projections"]) == 12

    def test_week_numbers_sequential(self):
        r = skill.execute(current_weight=80, daily_calorie_target=2000, maintenance_calories=2500, weeks=4)
        weeks = [p["week"] for p in r["projections"]]
        assert weeks == [1, 2, 3, 4]


class TestProjectionMath:
    def test_deficit_causes_weight_loss(self):
        # 500 kcal/day deficit → 3500 kcal/week → 3500/7700 ≈ 0.455 kg/week loss
        r = skill.execute(current_weight=80.0, daily_calorie_target=2000, maintenance_calories=2500, weeks=1)
        expected_change = (2000 - 2500) * 7 / 7700   # negative ≈ -0.4545
        # Skill rounds to 3 dp → -0.455; use abs tolerance to accommodate
        assert r["weekly_weight_change_kg"] == pytest.approx(expected_change, abs=0.001)
        assert r["projections"][0]["projected_weight"] < 80.0

    def test_surplus_causes_weight_gain(self):
        r = skill.execute(current_weight=70.0, daily_calorie_target=2800, maintenance_calories=2500, weeks=1)
        assert r["projections"][0]["projected_weight"] > 70.0

    def test_maintenance_no_change(self):
        r = skill.execute(current_weight=75.0, daily_calorie_target=2500, maintenance_calories=2500, weeks=4)
        assert r["weekly_weight_change_kg"] == pytest.approx(0.0, abs=0.001)
        for p in r["projections"]:
            assert p["projected_weight"] == pytest.approx(75.0, abs=0.01)

    def test_cumulative_weight_decreases_over_weeks(self):
        r = skill.execute(current_weight=90.0, daily_calorie_target=2000, maintenance_calories=2500, weeks=8)
        weights = [p["projected_weight"] for p in r["projections"]]
        assert weights == sorted(weights, reverse=True), "Weights should decrease week over week on a cut"


class TestProjectionValidation:
    def test_zero_weight_raises(self):
        with pytest.raises(ValueError):
            skill.execute(current_weight=0, daily_calorie_target=2000, maintenance_calories=2500, weeks=8)

    def test_zero_weeks_raises(self):
        with pytest.raises(ValueError):
            skill.execute(current_weight=80, daily_calorie_target=2000, maintenance_calories=2500, weeks=0)
