"""
tests/test_calorie_target_skill.py
Unit tests for CalorieTargetSkill — goal/intensity offsets.
"""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.nutrition.calorie_target_skill import CalorieTargetSkill

skill = CalorieTargetSkill()
MAINTENANCE = 2500.0


class TestCutGoal:
    def test_cut_conservative(self):
        r = skill.execute(maintenance_calories=MAINTENANCE, goal="cut", goal_intensity="conservative")
        assert r["daily_calorie_target"] == pytest.approx(2200.0)
        assert r["calorie_adjustment"] == -300

    def test_cut_balanced(self):
        r = skill.execute(maintenance_calories=MAINTENANCE, goal="cut", goal_intensity="balanced")
        assert r["daily_calorie_target"] == pytest.approx(2000.0)
        assert r["calorie_adjustment"] == -500

    def test_cut_aggressive(self):
        r = skill.execute(maintenance_calories=MAINTENANCE, goal="cut", goal_intensity="aggressive")
        assert r["daily_calorie_target"] == pytest.approx(1800.0)
        assert r["calorie_adjustment"] == -700


class TestBulkGoal:
    def test_bulk_conservative(self):
        r = skill.execute(maintenance_calories=MAINTENANCE, goal="bulk", goal_intensity="conservative")
        assert r["daily_calorie_target"] == pytest.approx(2700.0)
        assert r["calorie_adjustment"] == +200

    def test_bulk_balanced(self):
        r = skill.execute(maintenance_calories=MAINTENANCE, goal="bulk", goal_intensity="balanced")
        assert r["daily_calorie_target"] == pytest.approx(2850.0)
        assert r["calorie_adjustment"] == +350

    def test_bulk_aggressive(self):
        r = skill.execute(maintenance_calories=MAINTENANCE, goal="bulk", goal_intensity="aggressive")
        assert r["daily_calorie_target"] == pytest.approx(3000.0)
        assert r["calorie_adjustment"] == +500


class TestMaintainGoal:
    def test_maintain_all_intensities_equal_maintenance(self):
        for intensity in ("conservative", "balanced", "aggressive"):
            r = skill.execute(maintenance_calories=MAINTENANCE, goal="maintain", goal_intensity=intensity)
            assert r["daily_calorie_target"] == pytest.approx(MAINTENANCE)
            assert r["calorie_adjustment"] == 0


class TestCalorieTargetValidation:
    def test_invalid_goal_raises(self):
        with pytest.raises(ValueError, match="goal"):
            skill.execute(maintenance_calories=MAINTENANCE, goal="lose", goal_intensity="balanced")

    def test_invalid_intensity_raises(self):
        with pytest.raises(ValueError, match="goal_intensity"):
            skill.execute(maintenance_calories=MAINTENANCE, goal="cut", goal_intensity="extreme")

    def test_zero_maintenance_raises(self):
        with pytest.raises(ValueError):
            skill.execute(maintenance_calories=0, goal="cut", goal_intensity="balanced")

    def test_case_insensitive_goal(self):
        r = skill.execute(maintenance_calories=MAINTENANCE, goal="Cut", goal_intensity="Balanced")
        assert r["daily_calorie_target"] == pytest.approx(2000.0)
