"""
app/telegram_bot.py

Telegram long-polling integration for FastAPI.
Runs as a background async task inside the FastAPI lifespan.

Architecture:
    Telegram API → long-poll → handler → NutritionController → Skills → PostgreSQL
                                       ↓
                                  ElasticLogger

Polling features:
    - Offset-based duplicate protection (handled by PTB automatically)
    - Graceful start/stop tied to FastAPI lifespan
    - Network interruption retry handled by PTB internals
    - Errors caught and logged per-update — never crash the loop

Telegram commands handled:
    /start          — onboard new user (interactive conversation TODO)
    /log <w> <adh>  — submit weekly weight + adherence
    /plan           — request current plan summary
    /status         — show current nutrition state
    anything else   — echo help message
"""
import logging
import os

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

from db.session import SessionLocal
from app.controller import NutritionController
from elastic_logging.elastic_logger import ElasticLogger

load_dotenv()

logger = logging.getLogger(__name__)
elastic = ElasticLogger()
controller = NutritionController()

TOKEN = os.getenv("TELEGRAM_TOKEN", "")

# ---------------------------------------------------------------------------
# Keyboard helpers
# ---------------------------------------------------------------------------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main navigation menu shown on /start and /help."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 My Status",   callback_data="status"),
         InlineKeyboardButton("📅 Meal Plan",  callback_data="plan")],
        [InlineKeyboardButton("📈 Progress",   callback_data="progress"),
         InlineKeyboardButton("🤔 Coach",      callback_data="coach")],
        [InlineKeyboardButton("⚙️ Setup Plan",  callback_data="setup_prompt"),
         InlineKeyboardButton("📝 Log Weight",  callback_data="log_prompt")],
        [InlineKeyboardButton("❓ Help",          callback_data="help")],
    ])


def post_log_keyboard() -> InlineKeyboardMarkup:
    """Shown after a successful /log check-in."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Get Meal Plan", callback_data="plan"),
         InlineKeyboardButton("🤔 Ask Coach",     callback_data="coach")],
        [InlineKeyboardButton("📈 See Progress",  callback_data="progress"),
         InlineKeyboardButton("📊 Status",        callback_data="status")],
    ])


def post_setup_keyboard() -> InlineKeyboardMarkup:
    """Shown after a successful /setup."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Get Meal Plan", callback_data="plan"),
         InlineKeyboardButton("🤔 Ask Coach",     callback_data="coach")],
        [InlineKeyboardButton("📊 View Status",  callback_data="status")],
    ])

# ---------------------------------------------------------------------------
# Setup conversation states
# ---------------------------------------------------------------------------
(
    SETUP_WEIGHT, SETUP_HEIGHT, SETUP_AGE, SETUP_GENDER,
    SETUP_ACTIVITY, SETUP_GOAL, SETUP_INTENSITY, SETUP_TARGET_WEIGHT,
    SETUP_DIET, SETUP_AVOID, SETUP_CONFIRM,
) = range(11)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start — greet user and show the main inline button menu.
    """
    user = update.effective_user
    user_id = user.id
    logger.info("HANDLER=cmd_start | user_id=%s name=%s", user_id, user.first_name)
    elastic.log_event(user_id=user_id, event="cmd_start")

    await update.effective_message.reply_text(
        f"👋 *Hello {user.first_name}!*\n\n"
        "I'm your *Adaptive AI Nutrition Agent*.\n"
        "I'll build your personalised meal plan, track progress, "
        "detect plateaus, and adjust your plan automatically.\n\n"
        "Tap a button below to get started:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# Interactive setup conversation — replaces one-liner /setup command
# ---------------------------------------------------------------------------

async def setup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for the setup conversation — triggered by /setup or button."""
    query = update.callback_query
    if query:
        await query.answer()
    context.user_data.clear()
    await update.effective_message.reply_text(
        "⚙️ *Let's build your personalised plan!*\n\n"
        "*Step 1/9* — What's your current weight? *(kg)*\n"
        "Example: `80.5`",
        parse_mode="Markdown",
    )
    return SETUP_WEIGHT


async def setup_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["weight"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number, e.g. `80.5`", parse_mode="Markdown")
        return SETUP_WEIGHT
    await update.message.reply_text(
        "*Step 2/9* — Your height? *(cm)*\nExample: `175`",
        parse_mode="Markdown",
    )
    return SETUP_HEIGHT


async def setup_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["height"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number, e.g. `175`", parse_mode="Markdown")
        return SETUP_HEIGHT
    await update.message.reply_text(
        "*Step 3/9* — Your age?",
        parse_mode="Markdown",
    )
    return SETUP_AGE


async def setup_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["age"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid age, e.g. `30`", parse_mode="Markdown")
        return SETUP_AGE
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("👨 Male",   callback_data="sg_male"),
        InlineKeyboardButton("👩 Female", callback_data="sg_female"),
    ]])
    await update.message.reply_text("*Step 4/9* — Gender?", parse_mode="Markdown", reply_markup=keyboard)
    return SETUP_GENDER


async def setup_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["gender"] = query.data.replace("sg_", "")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🪑 Sedentary",  callback_data="sa_sedentary")],
        [InlineKeyboardButton("🚶 Light",       callback_data="sa_light"),
         InlineKeyboardButton("🏃 Moderate",    callback_data="sa_moderate")],
        [InlineKeyboardButton("💪 Active",      callback_data="sa_active"),
         InlineKeyboardButton("🔥 Very Active", callback_data="sa_very_active")],
    ])
    await query.message.reply_text("*Step 5/9* — Activity level?", parse_mode="Markdown", reply_markup=keyboard)
    return SETUP_ACTIVITY


async def setup_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["activity"] = query.data.replace("sa_", "")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Cut (lose fat)",       callback_data="so_cut")],
        [InlineKeyboardButton("💪 Bulk (gain muscle)",   callback_data="so_bulk")],
        [InlineKeyboardButton("⚖️ Maintain weight",      callback_data="so_maintain")],
    ])
    await query.message.reply_text("*Step 6/9* — What's your goal?", parse_mode="Markdown", reply_markup=keyboard)
    return SETUP_GOAL


async def setup_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    goal = query.data.replace("so_", "")
    context.user_data["goal"] = goal

    # Maintain → no rate needed, skip straight to diet
    if goal == "maintain":
        context.user_data["intensity"] = "balanced"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🥩 Omnivore",   callback_data="sd_omnivore"),
             InlineKeyboardButton("🥗 Vegetarian", callback_data="sd_vegetarian")],
            [InlineKeyboardButton("🌱 Vegan",       callback_data="sd_vegan"),
             InlineKeyboardButton("🥑 Keto",        callback_data="sd_keto")],
        ])
        await query.message.reply_text(
            "*Step 7/8* — Diet preference?", parse_mode="Markdown", reply_markup=keyboard
        )
        return SETUP_DIET

    # Infer recommended rate from activity level
    activity = context.user_data.get("activity", "moderate")
    _activity_map = {
        "sedentary":   ("conservative", "0.25 kg/week", "gentle & sustainable"),
        "light":       ("conservative", "0.25 kg/week", "gentle & sustainable"),
        "moderate":    ("balanced",     "0.50 kg/week", "standard pace"),
        "active":      ("balanced",     "0.50 kg/week", "standard pace"),
        "very_active": ("aggressive",   "1.00 kg/week", "intensive"),
    }
    rec_intensity, rec_rate, rec_label = _activity_map.get(activity, ("balanced", "0.50 kg/week", "standard pace"))
    context.user_data["recommended_intensity"] = rec_intensity

    verb  = "lose weight" if goal == "cut" else "gain muscle"
    emoji = "🔥" if goal == "cut" else "💪"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Yes, {rec_rate} sounds good!", callback_data="sr_confirm")],
        [InlineKeyboardButton("🔄 Let me choose",                  callback_data="sr_change")],
    ])
    await query.message.reply_text(
        f"*Step 7/9* {emoji} Based on your activity level, we recommend\n"
        f"**{rec_rate}** ({rec_label}) to {verb}.\n\n"
        f"Sounds right for you?",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return SETUP_INTENSITY


async def setup_rate_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles sr_confirm (accept AI recommendation) or sr_change (show manual options)."""
    query = update.callback_query
    await query.answer()

    if query.data == "sr_confirm":
        # Accept the recommendation
        context.user_data["intensity"] = context.user_data.get("recommended_intensity", "balanced")
        goal = context.user_data.get("goal", "cut")
        verb = "lose weight to" if goal == "cut" else "reach"
        await query.message.reply_text(
            f"*Step 8/9* — What's your target weight? *(kg)*\n"
            f"This is the weight you want to {verb}.\nExample: `72`",
            parse_mode="Markdown",
        )
        return SETUP_TARGET_WEIGHT

    # sr_change — show manual options
    goal = context.user_data.get("goal", "cut")
    if goal == "cut":
        question = "🎯 *Choose your pace:*"
        options = [
            ("🐌 0.25 kg/week — gentle, sustainable", "si_conservative"),
            ("� 0.50 kg/week — standard pace",        "si_balanced"),
            ("🏃 1.00 kg/week — intensive",            "si_aggressive"),
        ]
    else:  # bulk
        question = "🎯 *Choose your pace:*"
        options = [
            ("🐌 0.10 kg/week — lean bulk",    "si_conservative"),
            ("� 0.25 kg/week — moderate bulk", "si_balanced"),
            ("🏃 0.50 kg/week — aggressive",     "si_aggressive"),
        ]
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)] for label, cb in options])
    await query.message.reply_text(question, parse_mode="Markdown", reply_markup=keyboard)
    return SETUP_INTENSITY  # stays in same state to receive si_ button


async def setup_intensity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["intensity"] = query.data.replace("si_", "")
    goal = context.user_data.get("goal", "cut")

    # Maintain → already has intensity set, skip to diet
    if goal == "maintain":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🥩 Omnivore",   callback_data="sd_omnivore"),
             InlineKeyboardButton("🥗 Vegetarian", callback_data="sd_vegetarian")],
            [InlineKeyboardButton("🌱 Vegan",       callback_data="sd_vegan"),
             InlineKeyboardButton("🥑 Keto",        callback_data="sd_keto")],
        ])
        await query.message.reply_text("*Step 7/8* — Diet preference?", parse_mode="Markdown", reply_markup=keyboard)
        return SETUP_DIET

    # Ask target weight
    verb = "lose weight to" if goal == "cut" else "reach"
    await query.message.reply_text(
        f"*Step 8/9* — What's your target weight? *(kg)*\n"
        f"This is the weight you want to {verb}.\nExample: `72`",
        parse_mode="Markdown",
    )
    return SETUP_TARGET_WEIGHT


async def setup_target_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        tw = float(update.message.text.strip())
        cw = context.user_data.get("weight", tw)
        goal = context.user_data.get("goal", "cut")
        # Validate direction
        if goal == "cut" and tw >= cw:
            await update.message.reply_text(
                "⚠️ Target weight should be *less* than your current weight for a cut.\nTry again:",
                parse_mode="Markdown",
            )
            return SETUP_TARGET_WEIGHT
        if goal == "bulk" and tw <= cw:
            await update.message.reply_text(
                "⚠️ Target weight should be *more* than your current weight for a bulk.\nTry again:",
                parse_mode="Markdown",
            )
            return SETUP_TARGET_WEIGHT
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number, e.g. `72`", parse_mode="Markdown")
        return SETUP_TARGET_WEIGHT

    context.user_data["target_weight"] = tw
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🥩 Omnivore",   callback_data="sd_omnivore"),
         InlineKeyboardButton("🥗 Vegetarian", callback_data="sd_vegetarian")],
        [InlineKeyboardButton("🌱 Vegan",       callback_data="sd_vegan"),
         InlineKeyboardButton("🥑 Keto",        callback_data="sd_keto")],
    ])
    await update.message.reply_text("*Step 9/9* — Diet preference?", parse_mode="Markdown", reply_markup=keyboard)
    return SETUP_DIET


async def setup_diet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["diet"] = query.data.replace("sd_", "")
    await query.message.reply_text(
        "*Step 9/9* — Any foods to *avoid*? 🚫\n\n"
        "Type them separated by commas, or type `none`.\n"
        "Examples: `nuts, dairy, shellfish` or `none`",
        parse_mode="Markdown",
    )
    return SETUP_AVOID


async def setup_avoid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    avoid_text = update.message.text.strip()
    context.user_data["avoid"] = "" if avoid_text.lower() == "none" else avoid_text

    ud = context.user_data
    avoid_display = ud["avoid"] or "Nothing"
    
    # Clean up variables to prevent Markdown parsing errors (especially underscores like in 'very_active')
    activity_disp = str(ud['activity']).replace("_", " ").title()
    gender_disp = str(ud['gender']).title()
    goal_disp = str(ud['goal']).title()
    intensity_disp = str(ud['intensity']).title()
    diet_disp = str(ud['diet']).title()
    avoid_clean = avoid_display.replace("_", " ").replace("*", "").replace("`", "")

    summary = (
        f"📋 *Your Plan Summary*\n\n"
        f"⚖️ Weight:    {ud['weight']} kg\n"
        f"📏 Height:    {ud['height']} cm\n"
        f"🎂 Age:       {ud['age']}\n"
        f"👤 Gender:    {gender_disp}\n"
        f"🏃 Activity:  {activity_disp}\n"
        f"🎯 Goal:      {goal_disp}\n"
        f"⚡ Intensity: {intensity_disp}\n"
        f"🥗 Diet:      {diet_disp}\n"
        f"🚫 Avoid:     {avoid_clean}\n\n"
        f"Everything look right?"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Create My Plan!", callback_data="sc_confirm"),
        InlineKeyboardButton("❌ Cancel",           callback_data="sc_cancel"),
    ]])
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=keyboard)
    return SETUP_CONFIRM


async def setup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "sc_cancel":
        await query.message.reply_text(
            "❌ Setup cancelled. Tap *⚙️ Setup Plan* to start again.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    ud       = context.user_data
    user_id  = query.from_user.id

    # Rate maps must match what was shown to user in setup AND the GOAL_OFFSETS in calorie_target_skill
    _rate_maps = {
        "cut":      {"conservative": 0.25, "balanced": 0.50, "aggressive": 1.00},
        "bulk":     {"conservative": 0.10, "balanced": 0.25, "aggressive": 0.50},
        "maintain": {"conservative": 0.0,  "balanced": 0.0,  "aggressive": 0.0},
    }
    goal        = ud.get("goal", "cut")
    intensity   = ud.get("intensity", "balanced")
    weekly_rate = _rate_maps.get(goal, _rate_maps["cut"]).get(intensity, 0.5)
    target_weight  = ud.get("target_weight")
    current_weight = ud["weight"]
    if target_weight and weekly_rate > 0:
        raw_weeks = abs(current_weight - target_weight) / weekly_rate
        plan_weeks = max(4, min(52, round(raw_weeks)))   # clamp 4–52 weeks
    else:
        plan_weeks = 12  # sensible default for Maintain

    user_data = {
        "telegram_id":    user_id,
        "name":           query.from_user.first_name or "User",
        "current_weight": current_weight,
        "height_cm":      ud["height"],
        "age":            ud["age"],
        "gender":         ud["gender"],
        "activity_level": ud["activity"],
        "goal":           ud["goal"],
        "goal_intensity": ud["intensity"],
        "diet_type":      ud["diet"],
        "foods_to_avoid": ud.get("avoid", ""),
        "target_weight":  target_weight,
    }

    await query.message.reply_text("⏳ *Building your personalised plan…* (this may take a few seconds)", parse_mode="Markdown")

    db = SessionLocal()
    try:
        result = controller.handle_new_user(user_data=user_data, db=db, plan_weeks=plan_weeks)
        elastic.log_event(user_id=user_id, event="plan_generated")

        tdee = result["tdee"]
        cal  = result["calorie"]
        mac  = result["macros"]
        proj = result["projection"]
        first_proj = proj["projections"][-1] if proj["projections"] else {}

        avoid_line   = f"\n🚫 *Avoiding:* {ud['avoid']}" if ud.get("avoid") else ""
        target_line  = f"🎯 *Target:* {target_weight} kg in ~{plan_weeks} weeks\n" if target_weight else ""

        await query.message.reply_text(
            f"✅ *Your Plan is Ready!*\n\n"
            f"🔥 *Maintenance:* {tdee['maintenance_calories']:.0f} kcal/day\n"
            f"🎯 *Daily Target:* {cal['daily_calorie_target']:.0f} kcal "
            f"({int(cal['calorie_adjustment']):+d} kcal)\n"
            f"🥗 *Diet:* {ud['diet'].title()}{avoid_line}\n\n"
            f"📊 *Macros:*\n"
            f"  • Protein: {mac['protein_target_g']}g\n"
            f"  • Carbs:   {mac['carbs_target_g']}g\n"
            f"  • Fat:     {mac['fats_target_g']}g\n\n"
            f"{target_line}"
            f"📈 *{plan_weeks}-Week Projection:* {first_proj.get('projected_weight', 'N/A')} kg\n\n"
            f"What would you like to do next?",
            parse_mode="Markdown",
            reply_markup=post_setup_keyboard(),
        )
    except Exception as e:
        logger.exception("setup_confirm failed for user_id=%s: %s", user_id, e)
        await query.message.reply_text("❌ Something went wrong. Please try again.")
    finally:
        db.close()

    return ConversationHandler.END


async def setup_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fallback — /cancel during setup."""
    await update.effective_message.reply_text(
        "❌ Setup cancelled.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END



async def cmd_log(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /log <weight_kg> <adherence_percentage>
    Submits a weekly check-in and triggers plateau detection + adaptive adjustment.
    """
    user_id = update.effective_user.id
    args = context.args
    logger.info("HANDLER=cmd_log | user_id=%s | args=%s", user_id, args)

    if len(args) < 2:
        await update.effective_message.reply_text(
            "❌ Use: `/log <weight_kg> <adherence_%>`\nExample: `/log 79.5 90`",
            parse_mode="Markdown",
        )
        return

    try:
        log_data = {
            "logged_weight":        float(args[0]),
            "adherence_percentage": float(args[1]),
        }
    except ValueError as e:
        await update.effective_message.reply_text(f"❌ Parse error: {e}")
        return

    await update.effective_message.reply_text("⏳ Analysing your week…")

    db = SessionLocal()
    try:
        result = controller.handle_returning_user(
            user_id=user_id,
            log_data=log_data,
            db=db,
        )

        plateau = result["plateau"]
        adj     = result["adjustment"]
        mac     = result["macros"]

        plateau_msg = ""
        if plateau["plateau_detected"]:
            plateau_msg = (
                f"\n\n⚠️ *Plateau Detected!*\n"
                f"{plateau['reason']}\n"
                f"Calories adjusted by {adj['adjustment_applied']:+.0f} kcal."
            )
            elastic.log_event(
                user_id=user_id,
                event="plateau_detected",
                week=result["week"],
                adjustment=adj["adjustment_applied"],
            )
        else:
            elastic.log_event(user_id=user_id, event="weekly_log", week=result["week"])

        await update.effective_message.reply_text(
            f"✅ *Week {result['week']} logged!*\n\n"
            f"⚖️ Weight: {log_data['logged_weight']} kg\n"
            f"📋 Adherence: {log_data['adherence_percentage']:.0f}%"
            f"{plateau_msg}\n\n"
            f"📊 *Updated Macros:*\n"
            f"  • Protein: {mac['protein_target_g']}g\n"
            f"  • Carbs:   {mac['carbs_target_g']}g\n"
            f"  • Fat:     {mac['fats_target_g']}g\n\n"
            f"What would you like to do next?",
            parse_mode="Markdown",
            reply_markup=post_log_keyboard(),
        )
    except ValueError as e:
        await update.effective_message.reply_text(f"❌ {e}\nHave you run `/setup` first?")
    except Exception as e:
        logger.exception("handle_returning_user failed for user_id=%s: %s", user_id, e)
        elastic.log_event(user_id=user_id, event="error", metadata={"error": str(e)})
        await update.effective_message.reply_text("❌ Something went wrong. Please try again.")
    finally:
        db.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /status — shows current nutrition state from DB.
    """
    from db.models import NutritionState, User
    user_id = update.effective_user.id
    logger.info("HANDLER=cmd_status | user_id=%s", user_id)

    db = SessionLocal()
    try:
        state = db.query(NutritionState).filter(NutritionState.user_id == user_id).first()
        user  = db.query(User).filter(User.id == user_id).first()

        if not state or not user:
            await update.effective_message.reply_text(
                "❌ No plan found. Run `/setup` first.",
                parse_mode="Markdown",
            )
            return

        await update.effective_message.reply_text(
            f"📊 *Current Status — Week {state.current_week_number}*\n\n"
            f"⚖️ Weight: {state.current_weight} kg\n"
            f"🎯 Goal: {user.goal} ({user.goal_intensity})\n"
            f"🔥 Daily Target: {state.daily_calorie_target:.0f} kcal\n\n"
            f"💪 Protein: {state.protein_target_g}g\n"
            f"🍞 Carbs:   {state.carbs_target_g}g\n"
            f"🥑 Fat:     {state.fats_target_g}g\n\n"
            f"{'⚠️ Plateau flag is ON' if state.plateau_flag else '✅ No plateau detected'}",
            parse_mode="Markdown",
        )
        elastic.log_event(user_id=user_id, event="cmd_status")
    except Exception as e:
        logger.exception("cmd_status failed for user_id=%s: %s", user_id, e)
        await update.effective_message.reply_text("❌ Could not retrieve your status.")
    finally:
        db.close()


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /plan — generate this week's AI meal plan using the user's current macros.
    Reads macros from DB, calls WeeklyMealPlanSkill (Gemini), sends one message per day.
    """
    from db.models import NutritionState, User
    user_id = update.effective_user.id
    logger.info("HANDLER=cmd_plan | user_id=%s", user_id)

    db = SessionLocal()
    try:
        state = db.query(NutritionState).filter(NutritionState.user_id == user_id).first()
        user  = db.query(User).filter(User.id == user_id).first()

        if not state or not user:
            await update.effective_message.reply_text(
                "❌ No plan found. Run `/setup` first to create your nutrition profile.",
                parse_mode="Markdown",
            )
            return

        await update.effective_message.reply_text(
            f"🍽 *Generating your Week {state.current_week_number} meal plan…*\n"
            f"This may take 10-20 seconds while Gemini builds your plan.",
            parse_mode="Markdown",
        )

        macro_targets = {
            "protein_target_g": state.protein_target_g,
            "carbs_target_g":   state.carbs_target_g,
            "fats_target_g":    state.fats_target_g,
        }

        from skills.planning.weekly_meal_plan_skill import WeeklyMealPlanSkill
        planner = WeeklyMealPlanSkill()
        plan = planner.execute(
            macro_targets=macro_targets,
            diet_type=user.diet_type or "omnivore",
            goal=user.goal,
            week_number=state.current_week_number,
            foods_to_avoid=user.foods_to_avoid or "",
        )

        elastic.log_event(user_id=user_id, event="plan_requested", week=state.current_week_number)

        # Build one compact message for the whole week
        days = plan.get("days", [])
        if not days:
            await update.effective_message.reply_text("⚠️ Meal plan generated but contained no days. Try again.")
            return

        def fmt_day(day_data: dict) -> str:
            day    = day_data.get("day", "?")
            meals  = day_data.get("meals", {})
            totals = day_data.get("daily_totals", {})

            def meal_line(icon: str, key: str) -> str:
                m = meals.get(key, {})
                if not m:
                    return ""
                return (
                    f"{icon} {m.get('name', '—')} "
                    f"| {m.get('calories', 0)} kcal "
                    f"| {m.get('protein_g', 0)}P "
                    f"{m.get('carbs_g', 0)}C "
                    f"{m.get('fat_g', 0)}F\n"
                )

            return (
                f"*{day}*\n"
                + meal_line("🌅", "breakfast")
                + meal_line("☀️", "lunch")
                + meal_line("🌙", "dinner")
                + meal_line("🍎", "snacks")
                + f"📊 {totals.get('calories', 0)} kcal "
                f"| {totals.get('protein_g', 0)}P "
                f"{totals.get('carbs_g', 0)}C "
                f"{totals.get('fat_g', 0)}F\n"
            )

        # ── Macro Targets vs Actual summary header ──────────────────────────
        tgt_cal  = state.daily_calorie_target
        tgt_p    = state.protein_target_g
        tgt_c    = state.carbs_target_g
        tgt_f    = state.fats_target_g

        # Average daily macros across the generated plan
        n = max(len(days), 1)
        avg_cal = sum(d.get("daily_totals", {}).get("calories",  0) for d in days) / n
        avg_p   = sum(d.get("daily_totals", {}).get("protein_g", 0) for d in days) / n
        avg_c   = sum(d.get("daily_totals", {}).get("carbs_g",   0) for d in days) / n
        avg_f   = sum(d.get("daily_totals", {}).get("fat_g",     0) for d in days) / n

        def acc(actual: float, target: float) -> str:
            if target == 0:
                return "—"
            raw_pct = (actual / target) * 100
            # Calculate true accuracy: being 5% over is the same as being 5% under (95% accurate)
            accuracy = 100.0 - abs(100.0 - raw_pct)
            accuracy = max(0.0, accuracy)  # Don't let it go below 0%
            
            icon = "✅" if 90 <= raw_pct <= 110 else ("⚠️" if 80 <= raw_pct <= 120 else "❌")
            return f"{icon} {accuracy:.0f}%"

        acc_cal = acc(avg_cal, tgt_cal)
        acc_p   = acc(avg_p,   tgt_p)
        acc_c   = acc(avg_c,   tgt_c)
        acc_f   = acc(avg_f,   tgt_f)

        summary_header = (
            f"🍽 *Week {state.current_week_number} Meal Plan*\n\n"
            f"📊 *Macro Targets vs Plan Average*\n"
            f"```\n"
            f"{'Metric':<12} {'Target':>8} {'Actual':>8}  Accuracy\n"
            f"{'-'*42}\n"
            f"{'Calories':<12} {tgt_cal:>7.0f}  {avg_cal:>7.0f}  {acc_cal}\n"
            f"{'Protein':<12} {tgt_p:>6.0f}g  {avg_p:>6.0f}g  {acc_p}\n"
            f"{'Carbs':<12} {tgt_c:>6.0f}g  {avg_c:>6.0f}g  {acc_c}\n"
            f"{'Fat':<12} {tgt_f:>6.0f}g  {avg_f:>6.0f}g  {acc_f}\n"
            f"```\n\n"
        )

        body = "\n".join(fmt_day(d) for d in days)
        full = summary_header + body

        # Telegram limit is 4096 chars — split into 2 if needed (rare)
        if len(full) <= 4096:
            await update.effective_message.reply_text(full, parse_mode="Markdown")
        else:
            mid = len(days) // 2
            await update.effective_message.reply_text(
                summary_header + "\n".join(fmt_day(d) for d in days[:mid]), parse_mode="Markdown"
            )
            await update.effective_message.reply_text(
                "\n".join(fmt_day(d) for d in days[mid:]), parse_mode="Markdown"
            )

    except Exception as e:
        err_str = str(e)
        logger.exception("cmd_plan failed for user_id=%s: %s", user_id, e)
        elastic.log_event(user_id=user_id, event="error", metadata={"error": err_str})

        if "429" in err_str or "Resource exhausted" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            await update.effective_message.reply_text(
                "⏳ *Gemini API rate limit hit.*\n\n"
                "The free tier allows 15 requests/minute. "
                "Please wait **1-2 minutes** and tap 📅 Meal Plan again.",
                parse_mode="Markdown",
            )
        else:
            await update.effective_message.reply_text(
                f"❌ Meal plan failed: `{type(e).__name__}: {err_str[:200]}`\n\n"
                f"Check that `GEMINI_API_KEY` is valid in `.env`.",
                parse_mode="Markdown",
        )
    finally:
        db.close()


async def cmd_coach(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /coach — generates a personalised coaching message from Gemini based on
    the user's latest weekly log, plateau status, and goal.
    """
    from db.models import NutritionState, User, WeeklyLog
    user_id = update.effective_user.id
    logger.info("HANDLER=cmd_coach | user_id=%s", user_id)

    db = SessionLocal()
    try:
        state = db.query(NutritionState).filter(NutritionState.user_id == user_id).first()
        user  = db.query(User).filter(User.id == user_id).first()

        if not state or not user:
            await update.effective_message.reply_text(
                "❌ No plan found. Run `/setup` first.",
                parse_mode="Markdown",
            )
            return

        # Get the two most recent logs to compute weight delta
        logs = (
            db.query(WeeklyLog)
            .filter(WeeklyLog.user_id == user_id)
            .order_by(WeeklyLog.week_number.desc())
            .limit(2)
            .all()
        )

        weight_delta: float | None = None
        if len(logs) >= 2:
            weight_delta = logs[0].logged_weight - logs[1].logged_weight

        await update.effective_message.reply_text("🧠 Asking your AI coach for feedback… (5-10 seconds)")

        from skills.planning.coaching_summary_skill import CoachingSummarySkill
        coach = CoachingSummarySkill()
        result = coach.execute(
            user_name=user.name,
            goal=user.goal,
            current_week=state.current_week_number,
            plateau_detected=state.plateau_flag,
            weight_delta_kg=weight_delta,
            adjustment_applied=0.0,  # adjustment already applied in /log flow
        )

        elastic.log_event(user_id=user_id, event="cmd_coach", week=state.current_week_number)

        await update.effective_message.reply_text(
            f"🤔 *AI Coach — Week {state.current_week_number}*\n\n"
            f"{result['coaching_message']}",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.exception("cmd_coach failed for user_id=%s: %s", user_id, e)
        await update.effective_message.reply_text(
            "❌ Could not generate coaching message. Make sure `GEMINI_API_KEY` is set in `.env`."
        )
    finally:
        db.close()


async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /progress — shows a text-based weight trend chart from the user's weekly logs.
    """
    from db.models import WeeklyLog, NutritionState, User
    user_id = update.effective_user.id
    logger.info("HANDLER=cmd_progress | user_id=%s", user_id)

    db = SessionLocal()
    try:
        user  = db.query(User).filter(User.id == user_id).first()
        state = db.query(NutritionState).filter(NutritionState.user_id == user_id).first()

        if not user or not state:
            await update.effective_message.reply_text(
                "❌ No plan found. Run `/setup` first.",
                parse_mode="Markdown",
            )
            return

        logs = (
            db.query(WeeklyLog)
            .filter(WeeklyLog.user_id == user_id)
            .order_by(WeeklyLog.week_number.asc())
            .all()
        )

        if not logs:
            await update.effective_message.reply_text(
                "📊 No weekly logs yet.\n\n"
                "Use `/log <weight_kg> <adherence_%>` after each week to track progress.",
                parse_mode="Markdown",
            )
            return

        # Build weights list from logs first
        weights   = [l.logged_weight for l in logs]

        # Include Week 0 (setup weight) as baseline if available
        initial_w   = user.initial_weight if user.initial_weight else weights[0]
        all_weights = [initial_w] + weights
        min_w     = min(all_weights)
        max_w     = max(all_weights)
        w_range   = max_w - min_w if max_w != min_w else 1.0
        bar_width = 20

        lines = [f"📊 *Progress — Week 0–{len(logs)}*\n"]

        # Week 0 — setup baseline
        bar_len = int((initial_w - min_w) / w_range * bar_width)
        bar = "█" * bar_len + "░" * (bar_width - bar_len)
        lines.append(f"Wk 0: {bar} {initial_w:.1f}kg  (setup)")

        for log in logs:
            bar_len  = int((log.logged_weight - min_w) / w_range * bar_width)
            bar      = "█" * bar_len + "░" * (bar_width - bar_len)
            adherence_icon = "✅" if log.adherence_percentage >= 80 else ("⚠️" if log.adherence_percentage >= 50 else "❌")
            lines.append(
                f"Wk{log.week_number:>2}: {bar} {log.logged_weight:.1f}kg "
                f"{adherence_icon}{log.adherence_percentage:.0f}%"
            )

        # Summary — compare from setup weight to now
        total_change = weights[-1] - initial_w
        if total_change < 0:
            summary = f"*Total:* ⬇️ lost {abs(total_change):.2f} kg over {len(logs)} week(s)"
        elif total_change > 0:
            summary = f"*Total:* ⬆️ gained {abs(total_change):.2f} kg over {len(logs)} week(s)"
        else:
            summary = f"*Total:* ↔️ weight unchanged over {len(logs)} week(s)"

        lines.append(
            f"\n{summary}\n"
            f"*Start:* {initial_w:.1f} kg  →  *Now:* {weights[-1]:.1f} kg"
        )

        elastic.log_event(user_id=user_id, event="cmd_progress")
        await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.exception("cmd_progress failed for user_id=%s: %s", user_id, e)
        await update.effective_message.reply_text("❌ Could not load progress data.")
    finally:
        db.close()


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Explicitly called by /help command — shows full command list + menu buttons."""
    user_id = update.effective_user.id
    logger.info("HANDLER=cmd_help | user_id=%s", user_id)
    await update.effective_message.reply_text(
        "🤖 *Adaptive AI Nutrition Agent*\n\n"
        "Tap a button or use commands:\n"
        "`/setup`    — Create your nutrition plan\n"
        "`/plan`     — AI meal plan (7 days)\n"
        "`/log`      — Weekly check-in\n"
        "`/status`   — Current macros + target\n"
        "`/progress` — Weight trend chart\n"
        "`/coach`    — AI coaching feedback\n"
        "`/help`     — Show this message",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Routes all InlineKeyboard button presses to the correct handler.
    Uses CallbackQuery.answer() to dismiss the loading spinner on the button.
    """
    query = update.callback_query
    await query.answer()  # clears the loading spinner on the button instantly

    data = query.data
    logger.info("CALLBACK | user_id=%s | data=%s", query.from_user.id, data)

    # Show typing indicator immediately for visual responsiveness
    if data in ("status", "plan", "progress", "coach"):
        await query.message.chat.send_action("typing")

    # Simulate a normal Update with message so existing handlers work unchanged
    # We reuse the same handler functions directly.
    if data == "status":
        await cmd_status(update, context)
    elif data == "plan":
        await cmd_plan(update, context)
    elif data == "progress":
        await cmd_progress(update, context)
    elif data == "coach":
        await cmd_coach(update, context)
    elif data == "help":
        await query.message.reply_text(
            "🤖 *Adaptive AI Nutrition Agent*\n\n"
            "Tap a button or type a command:\n"
            "`/setup`    — Create your nutrition plan\n"
            "`/plan`     — AI meal plan (7 days)\n"
            "`/log`      — Weekly check-in\n"
            "`/status`   — Current macros + target\n"
            "`/progress` — Weight trend chart\n"
            "`/coach`    — AI coaching feedback",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
    elif data == "setup_prompt":
        # Delegate to setup conversation entry point
        await setup_start(update, context)
    elif data == "log_prompt":
        await query.message.reply_text(
            "📝 *Log Your Week*\n\n"
            "Send your weight and adherence:\n"
            "`/log <weight_kg> <adherence_%>`\n\n"
            "*Example:* `/log 79.5 90`\n\n"
            "Adherence = how closely you followed the plan (0–100%)",
            parse_mode="Markdown",
        )
    else:
        await query.message.reply_text("Unknown button. Use /help to see available options.")


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches any unrecognised /command."""
    user_id = update.effective_user.id
    text = update.message.text or ""
    logger.info("HANDLER=cmd_unknown | user_id=%s | text=%r", user_id, text[:60])
    await update.effective_message.reply_text(
        f"❓ Unknown command. Use /help to see available commands."
    )


async def cmd_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Catches plain text messages (non-commands).

    Important: Telegram only sends the bot_command entity (triggering CommandHandler)
    when the user TYPES a command via keyboard autocomplete. When a command is
    COPY-PASTED, Telegram sends it as plain text — it looks like '/setup 80 175 ...'
    but has no entity, so CommandHandler never sees it.

    This handler detects that pattern and manually dispatches to the correct handler.
    """
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    logger.info("HANDLER=cmd_text | user_id=%s | text=%r", user_id, text[:80])

    # Detect copy-pasted /commands and route them manually
    if text.startswith("/"):
        parts = text.split()
        cmd = parts[0].lstrip("/").lower().split("@")[0]  # strip /  and @botname
        context.args = parts[1:]  # inject args so handlers can read them

        _dispatch = {
            "start":    cmd_start,
            "setup":    cmd_setup,
            "log":      cmd_log,
            "status":   cmd_status,
            "plan":     cmd_plan,
            "coach":    cmd_coach,
            "progress": cmd_progress,
            "help":     cmd_help,
        }
        if cmd in _dispatch:
            logger.info("cmd_text: routing copy-pasted /%s to %s", cmd, _dispatch[cmd].__name__)
            await _dispatch[cmd](update, context)
            return
        else:
            await update.effective_message.reply_text("❓ Unknown command. Use /help to see available commands.")
            return
    await update.effective_message.reply_text(
        "💬 Use /help to see available commands."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global PTB error handler — logs and continues. Never crashes the loop."""
    logger.error("PTB error: %s", context.error, exc_info=context.error)


# ---------------------------------------------------------------------------
# Bot lifecycle — called from FastAPI lifespan
# ---------------------------------------------------------------------------

_ptb_app: Application | None = None


def build_application() -> Application:
    """Build and configure the PTB Application (call once)."""
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN is not set in .env")

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(15)
        .read_timeout(30)
        .write_timeout(15)
        .build()
    )

    # Register handlers — ORDER MATTERS in PTB: specific before catch-all
    # Setup conversation — must be registered FIRST (takes priority)
    setup_conv = ConversationHandler(
        entry_points=[
            CommandHandler("setup", setup_start),
            CallbackQueryHandler(setup_start, pattern="^setup_prompt$"),
        ],
        states={
            SETUP_WEIGHT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_weight)],
            SETUP_HEIGHT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_height)],
            SETUP_AGE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_age)],
            SETUP_GENDER:    [CallbackQueryHandler(setup_gender,    pattern="^sg_")],
            SETUP_ACTIVITY:  [CallbackQueryHandler(setup_activity,  pattern="^sa_")],
            SETUP_GOAL:      [CallbackQueryHandler(setup_goal,      pattern="^so_")],
            SETUP_INTENSITY:     [
                CallbackQueryHandler(setup_rate_confirm, pattern="^sr_"),
                CallbackQueryHandler(setup_intensity,    pattern="^si_"),
            ],
            SETUP_TARGET_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_target_weight)],
            SETUP_DIET:          [CallbackQueryHandler(setup_diet,            pattern="^sd_")],
            SETUP_AVOID:         [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_avoid)],
            SETUP_CONFIRM:       [CallbackQueryHandler(setup_confirm,         pattern="^sc_")],
        },
        fallbacks=[CommandHandler("cancel", setup_cancel)],
        allow_reentry=True,
    )
    application.add_handler(setup_conv)  # First — highest priority

    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("start",    cmd_start))
    application.add_handler(CommandHandler("log",      cmd_log))
    application.add_handler(CommandHandler("status",   cmd_status))
    application.add_handler(CommandHandler("plan",     cmd_plan))
    application.add_handler(CommandHandler("coach",    cmd_coach))
    application.add_handler(CommandHandler("progress", cmd_progress))
    application.add_handler(CommandHandler("help",     cmd_help))
    # Catch-all: unknown /commands
    application.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))
    # Catch-all: plain text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_text))
    application.add_error_handler(error_handler)

    return application


async def init_webhook() -> None:
    """
    Initialize PTB for webhook mode.
    Called from FastAPI lifespan startup.
    """
    global _ptb_app

    if not TOKEN:
        logger.warning("TELEGRAM_TOKEN not set — bot disabled.")
        return

    _ptb_app = build_application()

    await _ptb_app.initialize()
    await _ptb_app.start()
    logger.info("Telegram PTB initialized for webhooks.")


async def process_webhook_update(update_json: dict) -> None:
    """Feed an incoming webhook update from FastAPI to PTB."""
    if _ptb_app is None:
        return
    update = Update.de_json(data=update_json, bot=_ptb_app.bot)
    await _ptb_app.update_queue.put(update)


async def stop_webhook() -> None:
    """
    Gracefully stop PTB.
    Called from FastAPI lifespan shutdown.
    """
    global _ptb_app
    if _ptb_app is None:
        return

    logger.info("Stopping Telegram PTB…")
    await _ptb_app.stop()
    await _ptb_app.shutdown()
    logger.info("Telegram PTB stopped.")


async def start_polling() -> None:
    """
    Initialize PTB and start long polling.
    Called from FastAPI lifespan startup.
    Polling runs in the background — this function returns immediately.
    """
    global _ptb_app

    if not TOKEN:
        logger.warning("TELEGRAM_TOKEN not set — polling disabled.")
        return

    _ptb_app = build_application()

    await _ptb_app.initialize()
    await _ptb_app.start()

    # start_polling is non-blocking in PTB v21 — it starts a background task
    await _ptb_app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,      # ignore updates queued while we were offline
    )

    logger.info("Telegram polling started — bot is listening.")


async def stop_polling() -> None:
    """
    Gracefully stop PTB polling.
    Called from FastAPI lifespan shutdown.
    """
    global _ptb_app
    if _ptb_app is None:
        return

    logger.info("Stopping Telegram polling…")
    await _ptb_app.updater.stop()
    await _ptb_app.stop()
    await _ptb_app.shutdown()
    logger.info("Telegram polling stopped.")
