"""
app/controller.py
NutritionController — Agent orchestration layer.

SEPARATION OF CONCERNS:
  - Controller owns all DB reads and writes.
  - Skills receive only plain data (dicts / scalars). No DB sessions inside skills.
  - LLM skills are called only after deterministic calculations are complete.

Flows documented in Section 9 of AI_Nutritient_Agent.md.
"""
from datetime import datetime
from sqlalchemy.orm import Session

from skills.nutrition.tdee_skill import TDEESkill
from skills.nutrition.calorie_target_skill import CalorieTargetSkill
from skills.nutrition.macro_distribution_skill import MacroDistributionSkill
from skills.projection.weight_projection_skill import WeightProjectionSkill
from skills.adaptation.plateau_detection_skill import PlateauDetectionSkill
from skills.adaptation.adaptive_adjustment_skill import AdaptiveAdjustmentSkill

from db.models import User, NutritionState, WeeklyLog, Projection

# LLM skills are imported lazily inside methods to preserve deterministic-first architecture
# They are only called after all deterministic steps succeed.


class NutritionController:
    """
    Orchestrates skill execution for two primary user flows:
        handle_new_user()       — Section 9.1
        handle_returning_user() — Section 9.2

    Does NOT contain any business logic beyond calling skills in order.
    Does NOT call LLM directly — delegates to LLM skills.
    """

    def __init__(self):
        self._tdee = TDEESkill()
        self._calorie = CalorieTargetSkill()
        self._macro = MacroDistributionSkill()
        self._projection = WeightProjectionSkill()
        self._plateau = PlateauDetectionSkill()
        self._adjustment = AdaptiveAdjustmentSkill()

    # ------------------------------------------------------------------
    # 9.1 NEW USER FLOW
    # ------------------------------------------------------------------

    def handle_new_user(
        self,
        user_data: dict,
        db: Session,
        plan_weeks: int = 8,
    ) -> dict:
        """
        Section 9.1 — New user onboarding flow.

        Steps:
            1. Persist User to DB
            2. TDEESkill
            3. CalorieTargetSkill
            4. MacroDistributionSkill
            5. WeightProjectionSkill
            6. MultiWeekPlannerSkill (LLM)
            7. Persist NutritionState + Projections
        """
        # --- 1. Persist user ---
        user = User(
            id=user_data["telegram_id"],
            name=user_data["name"],
            age=user_data["age"],
            gender=user_data["gender"],
            height_cm=user_data["height_cm"],
            activity_level=user_data["activity_level"],
            goal=user_data["goal"],
            goal_intensity=user_data["goal_intensity"],
            diet_type=user_data.get("diet_type"),
            initial_weight=user_data["current_weight"],  # baseline for progress chart
            foods_to_avoid=user_data.get("foods_to_avoid", ""),
            target_weight=user_data.get("target_weight"),
        )
        db.merge(user)   # upsert — safe for re-runs
        db.flush()

        # --- 2. TDEE ---
        tdee_result = self._tdee.execute(
            weight=user_data["current_weight"],
            height=user_data["height_cm"],
            age=user_data["age"],
            gender=user_data["gender"],
            activity_level=user_data["activity_level"],
        )

        # --- 3. Calorie target ---
        calorie_result = self._calorie.execute(
            maintenance_calories=tdee_result["maintenance_calories"],
            goal=user_data["goal"],
            goal_intensity=user_data["goal_intensity"],
        )

        # --- 4. Macro distribution ---
        macro_result = self._macro.execute(
            daily_calorie_target=calorie_result["daily_calorie_target"],
            current_weight=user_data["current_weight"],
            goal=user_data["goal"],
        )

        # --- 5. Weight projection ---
        projection_result = self._projection.execute(
            current_weight=user_data["current_weight"],
            daily_calorie_target=calorie_result["daily_calorie_target"],
            maintenance_calories=tdee_result["maintenance_calories"],
            weeks=plan_weeks,
        )

        # --- 6. Meal plan ---
        # Plans are generated on-demand via /plan (cmd_plan → WeeklyMealPlanSkill).
        # Do NOT pre-generate the full multi-week plan here — it makes signup slow
        # (1 OpenAI call per week × N weeks = very long wait for the user).
        meal_plan = {"weeks": []}


        # --- 7. Persist NutritionState ---
        state = NutritionState(
            user_id=user_data["telegram_id"],
            current_weight=user_data["current_weight"],
            maintenance_calories=tdee_result["maintenance_calories"],
            daily_calorie_target=calorie_result["daily_calorie_target"],
            protein_target_g=macro_result["protein_target_g"],
            carbs_target_g=macro_result["carbs_target_g"],
            fats_target_g=macro_result["fats_target_g"],
            plateau_flag=False,
            current_week_number=1,
            updated_at=datetime.utcnow(),
        )
        db.merge(state)

        # Persist weekly projections
        db.query(Projection).filter(Projection.user_id == user_data["telegram_id"]).delete()
        for p in projection_result["projections"]:
            db.add(Projection(
                user_id=user_data["telegram_id"],
                projected_week=p["week"],
                projected_weight=p["projected_weight"],
            ))

        db.commit()

        return {
            "tdee": tdee_result,
            "calorie": calorie_result,
            "macros": macro_result,
            "projection": projection_result,
            "meal_plan": meal_plan,
        }

    # ------------------------------------------------------------------
    # 9.2 RETURNING USER FLOW
    # ------------------------------------------------------------------

    def handle_returning_user(
        self,
        user_id: int,
        log_data: dict,
        db: Session,
    ) -> dict:
        """
        Section 9.2 — Returning user weekly check-in flow.

        Steps:
            1. Load user state from DB
            2. Persist weekly log
            3. PlateauDetectionSkill
            4. If plateau → AdaptiveAdjustmentSkill
            5. Regenerate next week's meal plan (LLM)
            6. Persist updated NutritionState
        """
        # --- 1. Load user state ---
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found.")

        state = db.query(NutritionState).filter(NutritionState.user_id == user_id).first()
        if not state:
            raise ValueError(f"NutritionState not found for user {user_id}.")

        # --- 2. Persist weekly log ---
        week = state.current_week_number
        log_entry = WeeklyLog(
            user_id=user_id,
            week_number=week,
            logged_weight=log_data["logged_weight"],
            adherence_percentage=log_data["adherence_percentage"],
            timestamp=datetime.utcnow(),
        )
        db.add(log_entry)
        db.flush()

        # --- 3. Load all logs for plateau check ---
        all_logs = db.query(WeeklyLog).filter(WeeklyLog.user_id == user_id).all()
        logs_dicts = [
            {
                "week_number": l.week_number,
                "logged_weight": l.logged_weight,
                "adherence_percentage": l.adherence_percentage,
            }
            for l in all_logs
        ]

        plateau_result = self._plateau.execute(
            goal=user.goal,
            weekly_logs=logs_dicts,
        )

        # --- 4. Adaptive adjustment if plateau ---
        adjustment_result = self._adjustment.execute(
            plateau_detected=plateau_result["plateau_detected"],
            goal=user.goal,
            daily_calorie_target=state.daily_calorie_target,
            bmr=state.maintenance_calories / self._get_activity_multiplier(user.activity_level),
        )

        new_calorie_target = adjustment_result["new_calorie_target"]

        # Recalculate macros for updated target
        macro_result = self._macro.execute(
            daily_calorie_target=new_calorie_target,
            current_weight=log_data["logged_weight"],
            goal=user.goal,
        )

        # --- 5. Regenerate next week (LLM) ---
        next_week_plan = None
        try:
            from skills.planning.weekly_meal_plan_skill import WeeklyMealPlanSkill
            planner = WeeklyMealPlanSkill()
            next_week_plan = planner.execute(
                macro_targets=macro_result,
                diet_type=user.diet_type or "omnivore",
                goal=user.goal,
                week_number=week + 1,
            )
        except Exception as llm_error:
            next_week_plan = {"error": str(llm_error)}

        # --- 6. Persist updated NutritionState ---
        state.current_weight = log_data["logged_weight"]
        state.daily_calorie_target = new_calorie_target
        state.protein_target_g = macro_result["protein_target_g"]
        state.carbs_target_g = macro_result["carbs_target_g"]
        state.fats_target_g = macro_result["fats_target_g"]
        state.plateau_flag = plateau_result["plateau_detected"]
        state.current_week_number = week + 1
        state.updated_at = datetime.utcnow()

        # --- 7. Rolling projection recalculation ---
        # Recalculate remaining weeks from the user's ACTUAL logged weight,
        # using the updated calorie target (may have changed due to plateau).
        remaining_weeks = max(1, 8 - week)
        try:
            new_projection = self._projection.execute(
                current_weight=log_data["logged_weight"],
                daily_calorie_target=new_calorie_target,
                maintenance_calories=state.maintenance_calories,
                weeks=remaining_weeks,
            )
            # Delete only future projections — keep past weeks as history
            db.query(Projection).filter(
                Projection.user_id == user_id,
                Projection.projected_week > week,
            ).delete()
            for p in new_projection["projections"]:
                db.add(Projection(
                    user_id=user_id,
                    projected_week=week + p["week"],
                    projected_weight=p["projected_weight"],
                ))
        except Exception:
            pass  # projection failure must never block the log commit

        db.commit()


        return {
            "week": week,
            "plateau": plateau_result,
            "adjustment": adjustment_result,
            "macros": macro_result,
            "next_week_plan": next_week_plan,
        }

    @staticmethod
    def _get_activity_multiplier(activity_level: str) -> float:
        """Helper to recover BMR from TDEE for the safety floor calculation."""
        return {
            "sedentary":   1.2,
            "light":       1.375,
            "moderate":    1.55,
            "active":      1.725,
            "very_active": 1.9,
        }.get(activity_level.lower(), 1.55)
