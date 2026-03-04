"""
tests/test_adaptive_adjustment_skill.py
Unit tests for AdaptiveAdjustmentSkill.
"""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.adaptation.adaptive_adjustment_skill import AdaptiveAdjustmentSkill

skill = AdaptiveAdjustmentSkill()

BASE_BMR = 1750.0
BASE_TARGET = 2250.0


class TestNoAdjustmentWhenNoPlateau:
    def test_no_plateau_returns_unchanged_target(self):
        r = skill.execute(plateau_detected=False, goal="cut", daily_calorie_target=BASE_TARGET, bmr=BASE_BMR)
        assert r["new_calorie_target"] == pytest.approx(BASE_TARGET)
        assert r["adjustment_applied"] == 0
        assert r["safety_clipped"] is False


class TestAdjustmentPerGoal:
    def test_cut_reduces_150_kcal(self):
        r = skill.execute(plateau_detected=True, goal="cut", daily_calorie_target=BASE_TARGET, bmr=BASE_BMR)
        assert r["new_calorie_target"] == pytest.approx(BASE_TARGET - 150, rel=1e-3)
        assert r["safety_clipped"] is False

    def test_bulk_increases_100_kcal(self):
        r = skill.execute(plateau_detected=True, goal="bulk", daily_calorie_target=BASE_TARGET, bmr=BASE_BMR)
        assert r["new_calorie_target"] == pytest.approx(BASE_TARGET + 100, rel=1e-3)
        assert r["safety_clipped"] is False

    def test_maintain_no_meaningful_change(self):
        r = skill.execute(plateau_detected=True, goal="maintain", daily_calorie_target=BASE_TARGET, bmr=BASE_BMR)
        assert r["adjustment_applied"] == 0


class TestSafetyFloor:
    def test_cut_cannot_go_below_bmr(self):
        # Target very close to BMR — after -150 it would drop below
        target_near_bmr = BASE_BMR + 100  # 1850, after -150 → 1700 < BMR
        r = skill.execute(plateau_detected=True, goal="cut", daily_calorie_target=target_near_bmr, bmr=BASE_BMR)
        assert r["new_calorie_target"] >= BASE_BMR
        assert r["safety_clipped"] is True

    def test_target_exactly_bmr_stays_at_bmr(self):
        r = skill.execute(plateau_detected=True, goal="cut", daily_calorie_target=BASE_BMR, bmr=BASE_BMR)
        assert r["new_calorie_target"] == pytest.approx(BASE_BMR)
        assert r["safety_clipped"] is True


class TestSafetyCeiling:
    def test_bulk_cannot_exceed_bmr_times_1_9(self):
        # Target near ceiling
        ceiling = BASE_BMR * 1.9   # 3325
        target_near_ceiling = ceiling - 50   # 3275, after +100 → 3375 > ceiling
        r = skill.execute(plateau_detected=True, goal="bulk", daily_calorie_target=target_near_ceiling, bmr=BASE_BMR)
        assert r["new_calorie_target"] <= ceiling + 0.01
        assert r["safety_clipped"] is True


class TestAdaptiveValidation:
    def test_invalid_goal_raises(self):
        with pytest.raises(ValueError, match="goal"):
            skill.execute(plateau_detected=True, goal="lose", daily_calorie_target=2000, bmr=1500)

    def test_zero_bmr_raises(self):
        with pytest.raises(ValueError):
            skill.execute(plateau_detected=True, goal="cut", daily_calorie_target=2000, bmr=0)

    def test_zero_target_raises(self):
        with pytest.raises(ValueError):
            skill.execute(plateau_detected=True, goal="cut", daily_calorie_target=0, bmr=1500)
