"""
tests/test_tdee_skill.py
Unit tests for TDEESkill — Mifflin-St Jeor equation.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.nutrition.tdee_skill import TDEESkill

skill = TDEESkill()


class TestTDEESkillMale:
    def test_male_moderate_activity(self):
        result = skill.execute(weight=80, height=175, age=30, gender="male", activity_level="moderate")
        # BMR = (10*80) + (6.25*175) - (5*30) + 5 = 800+1093.75-150+5 = 1748.75
        # TDEE = 1748.75 * 1.55 = 2710.5625
        assert result["bmr"] == pytest.approx(1748.75, rel=1e-3)
        assert result["maintenance_calories"] == pytest.approx(2710.56, rel=1e-2)
        assert result["activity_level"] == "moderate"

    def test_male_sedentary(self):
        result = skill.execute(weight=70, height=170, age=25, gender="male", activity_level="sedentary")
        # BMR = 700+1062.5-125+5 = 1642.5
        # TDEE = 1642.5 * 1.2 = 1971.0
        assert result["bmr"] == pytest.approx(1642.5, rel=1e-3)
        assert result["maintenance_calories"] == pytest.approx(1971.0, rel=1e-2)

    def test_male_very_active(self):
        result = skill.execute(weight=90, height=180, age=28, gender="male", activity_level="very_active")
        # BMR = 900+1125-140+5 = 1890
        # TDEE = 1890 * 1.9 = 3591.0
        assert result["bmr"] == pytest.approx(1890.0, rel=1e-3)
        assert result["maintenance_calories"] == pytest.approx(3591.0, rel=1e-2)


class TestTDEESkillFemale:
    def test_female_light_activity(self):
        result = skill.execute(weight=60, height=165, age=28, gender="female", activity_level="light")
        # BMR = 600+1031.25-140-161 = 1330.25
        # TDEE = 1330.25 * 1.375 = 1829.09...
        assert result["bmr"] == pytest.approx(1330.25, rel=1e-3)
        assert result["maintenance_calories"] == pytest.approx(1829.09, rel=1e-2)

    def test_female_active(self):
        result = skill.execute(weight=65, height=160, age=35, gender="female", activity_level="active")
        # BMR = 650+1000-175-161 = 1314.0
        # TDEE = 1314 * 1.725 = 2266.65
        assert result["bmr"] == pytest.approx(1314.0, rel=1e-3)
        assert result["maintenance_calories"] == pytest.approx(2266.65, rel=1e-2)

    def test_case_insensitive_gender(self):
        result = skill.execute(weight=60, height=165, age=28, gender="Female", activity_level="moderate")
        assert result["bmr"] > 0

    def test_case_insensitive_activity(self):
        result = skill.execute(weight=60, height=165, age=28, gender="female", activity_level="Moderate")
        assert result["maintenance_calories"] > 0


class TestTDEESkillValidation:
    def test_invalid_gender_raises(self):
        with pytest.raises(ValueError, match="gender"):
            skill.execute(weight=80, height=175, age=30, gender="other", activity_level="moderate")

    def test_invalid_activity_raises(self):
        with pytest.raises(ValueError, match="activity_level"):
            skill.execute(weight=80, height=175, age=30, gender="male", activity_level="extreme")

    def test_zero_weight_raises(self):
        with pytest.raises(ValueError):
            skill.execute(weight=0, height=175, age=30, gender="male", activity_level="moderate")

    def test_negative_age_raises(self):
        with pytest.raises(ValueError):
            skill.execute(weight=80, height=175, age=-5, gender="male", activity_level="moderate")

    def test_all_activity_levels_produce_increasing_tdee(self):
        levels = ["sedentary", "light", "moderate", "active", "very_active"]
        values = [
            skill.execute(weight=80, height=175, age=30, gender="male", activity_level=l)["maintenance_calories"]
            for l in levels
        ]
        assert values == sorted(values), "TDEE should increase with activity level"
