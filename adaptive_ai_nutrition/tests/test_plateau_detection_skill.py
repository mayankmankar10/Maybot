"""
tests/test_plateau_detection_skill.py
Unit tests for PlateauDetectionSkill.
"""
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.adaptation.plateau_detection_skill import PlateauDetectionSkill

skill = PlateauDetectionSkill()


def make_log(week, weight, adherence):
    return {"week_number": week, "logged_weight": weight, "adherence_percentage": adherence}


class TestPlateauDetected:
    def test_plateau_on_cut_all_conditions_met(self):
        logs = [make_log(3, 80.0, 90), make_log(4, 80.1, 85)]
        r = skill.execute(goal="cut", weekly_logs=logs)
        assert r["plateau_detected"] is True
        assert r["weight_delta_kg"] == pytest.approx(0.1, abs=0.001)

    def test_plateau_on_bulk_all_conditions_met(self):
        logs = [make_log(5, 75.0, 88), make_log(6, 75.15, 92)]
        r = skill.execute(goal="bulk", weekly_logs=logs)
        assert r["plateau_detected"] is True


class TestPlateauNotDetected:
    def test_no_plateau_sufficient_weight_change(self):
        logs = [make_log(3, 80.0, 90), make_log(4, 79.5, 85)]
        r = skill.execute(goal="cut", weekly_logs=logs)
        assert r["plateau_detected"] is False
        assert "no plateau" in r["reason"].lower()

    def test_no_plateau_low_adherence(self):
        logs = [make_log(3, 80.0, 65), make_log(4, 80.1, 70)]
        r = skill.execute(goal="cut", weekly_logs=logs)
        assert r["plateau_detected"] is False
        assert "adherence" in r["reason"].lower()

    def test_no_plateau_maintain_goal(self):
        logs = [make_log(1, 70.0, 95), make_log(2, 70.05, 90)]
        r = skill.execute(goal="maintain", weekly_logs=logs)
        assert r["plateau_detected"] is False

    def test_no_plateau_insufficient_data(self):
        logs = [make_log(1, 80.0, 90)]
        r = skill.execute(goal="cut", weekly_logs=logs)
        assert r["plateau_detected"] is False
        assert "insufficient" in r["reason"].lower()

    def test_exactly_0_2_kg_change_is_not_plateau(self):
        # threshold is < 0.2; exact 0.2 should NOT be plateau
        logs = [make_log(3, 80.0, 90), make_log(4, 79.8, 85)]
        r = skill.execute(goal="cut", weekly_logs=logs)
        assert r["plateau_detected"] is False

    def test_uses_most_recent_two_weeks(self):
        # Provide 4 logs; detection should use weeks 3 & 4 (most recent)
        logs = [
            make_log(1, 82.0, 90),
            make_log(2, 81.0, 90),
            make_log(3, 80.05, 90),
            make_log(4, 80.0, 90),
        ]
        r = skill.execute(goal="cut", weekly_logs=logs)
        assert r["plateau_detected"] is True  # last 2 weeks differ by 0.05 kg


class TestPlateauValidation:
    def test_invalid_goal_raises(self):
        with pytest.raises(ValueError):
            skill.execute(goal="lose", weekly_logs=[])
