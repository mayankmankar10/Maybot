# 🥗 Adaptive AI Nutrition Agent

> A production-structured, skill-based, closed-loop AI nutrition system built on FastAPI + PostgreSQL + Elasticsearch + Telegram.

---

## Overview

The **Adaptive AI Nutrition Agent** is a stateful, modular backend system that generates and dynamically adjusts multi-week diet plans using **deterministic physiological modeling** combined with **constrained LLM reasoning** (Google Gemini).

This is **not** a simple chatbot wrapper. It is a structured adaptive control system that separates safety-critical calculations from probabilistic AI outputs, integrates with Telegram via secure webhook, and continuously adapts nutrition targets based on real weekly user feedback.

---

## ✨ Key Features

- 📊 **Deterministic-first design** — TDEE, calorie targets, macros, and plateau detection computed mathematically before any LLM call
- 🔁 **Closed-loop feedback** — adapts weekly based on logged weight and adherence
- 🧠 **Constrained LLM usage** — Gemini is used only for meal plan generation, coaching summaries, and natural language explanations
- 📦 **Skill-based architecture** — every capability is an isolated, independently testable skill
- 🗄️ **PostgreSQL persistence** — structured relational state for users, nutrition data, logs, and projections
- 🔍 **Elasticsearch observability** — all events, plateau detections, and adaptations are logged for monitoring
- 🤖 **Telegram integration** — deployed as a secure webhook-based Telegram bot

---

## 🏗️ Architecture

```
Internet
   ↓
Telegram
   ↓
Nginx (SSL Termination + Reverse Proxy)
   ↓
FastAPI (Webhook Endpoint)
   ↓
NutritionController (Agent Orchestration)
   ↓
Skill Layer (Deterministic + LLM Skills)
   ↓
PostgreSQL (Persistent State)  +  Elasticsearch (Logs & Observability)
```

---

## 📁 Project Structure

```
adaptive_ai_nutrition/
├── app/
│   ├── main.py              # FastAPI app entry point & health check
│   ├── webhook.py           # Telegram webhook endpoint
│   ├── controller.py        # NutritionController — skill orchestration
│   └── telegram_bot.py      # Telegram command handlers
├── skills/
│   ├── base_skill.py        # Abstract base class for all skills
│   ├── nutrition/           # TDEE, calorie target, macro distribution
│   ├── planning/            # WeeklyMealPlanSkill, CoachingSummarySkill
│   ├── projection/          # WeightProjectionSkill
│   └── adaptation/          # PlateauDetectionSkill, AdaptiveAdjustmentSkill
├── db/
│   ├── models.py            # SQLAlchemy ORM models
│   └── session.py           # Database session factory
├── elastic_logging/         # Elasticsearch logging utilities
├── nginx/
│   └── nginx.conf           # Nginx reverse proxy configuration
├── systemd/
│   └── ai_nutrition.service # systemd service definition
├── tests/                   # pytest test suite
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
├── Procfile                 # Process declaration for deployment
├── railway.toml             # Railway deployment configuration
└── runtime.txt              # Python version pin
```

---

## ⚙️ How It Works

### New User Flow
1. User onboards via Telegram (name, age, gender, height, weight, goal)
2. **TDEESkill** — computes maintenance calories using Mifflin-St Jeor
3. **CalorieTargetSkill** — applies goal deficit/surplus
4. **MacroDistributionSkill** — distributes protein, carbs, and fats
5. **WeightProjectionSkill** — projects week-by-week weight trajectory
6. **WeeklyMealPlanSkill (LLM)** — generates structured 7-day meal plan on demand

### Returning User Weekly Check-In
1. User logs current weight and adherence percentage
2. **PlateauDetectionSkill** — detects stalls (< 0.2 kg change over 2 weeks with ≥ 80% adherence)
3. **AdaptiveAdjustmentSkill** — adjusts calorie target if plateau detected
4. **WeeklyMealPlanSkill (LLM)** — regenerates the next week's plan
5. Updated state persisted to PostgreSQL; event logged to Elasticsearch

---

## 🧮 Deterministic Formulas

| Skill | Formula |
|---|---|
| **TDEE (Male)** | `(10 × kg) + (6.25 × cm) − (5 × age) + 5` × activity factor |
| **TDEE (Female)** | `(10 × kg) + (6.25 × cm) − (5 × age) − 161` × activity factor |
| **Weight change** | `weekly_calorie_deficit / 7700` kg/week |
| **Plateau** | `Δweight < 0.2 kg` over 2 weeks AND adherence ≥ 80% |
| **Adjustment (cut)** | `−150 kcal` (never below BMR) |
| **Adjustment (bulk)** | `+100 kcal` (within safe surplus) |

---

## 🗄️ Database Schema

| Table | Key Columns |
|---|---|
| `users` | `id` (Telegram ID), name, age, gender, height, activity_level, goal, diet_type |
| `nutrition_state` | calorie_target, macros, plateau_flag, current_week_number |
| `weekly_logs` | logged_weight, adherence_percentage, week_number |
| `projections` | projected_week, projected_weight |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL
- Elasticsearch 8.x
- A Telegram Bot token ([@BotFather](https://t.me/BotFather))
- Google Gemini API key

### 1. Clone & Install

```bash
git clone https://github.com/your-username/DietPlanner.git
cd DietPlanner/adaptive_ai_nutrition
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `TELEGRAM_TOKEN` | Telegram Bot API token |
| `TELEGRAM_WEBHOOK_SECRET` | Webhook secret for security |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Model name (e.g. `gemini-2.0-flash`) |
| `ELASTIC_HOST` | Elasticsearch host URL |
| `ELASTIC_INDEX` | Elasticsearch index name |

### 3. Run Locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run Tests

```bash
pytest tests/
```

---

## ☁️ Deployment

### Railway

The project includes `railway.toml` for one-click deployment on [Railway](https://railway.app):

```toml
[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
restartPolicyType = "on_failure"
```

Add a PostgreSQL service in Railway and set all environment variables in the Railway dashboard.

### Self-Hosted (Nginx + systemd)

1. Configure `nginx/nginx.conf` with your domain and SSL certificates
2. Copy `systemd/ai_nutrition.service` to `/etc/systemd/system/`
3. Run:
   ```bash
   sudo systemctl enable ai_nutrition
   sudo systemctl start ai_nutrition
   ```

---

## 🧪 Tech Stack

| Layer | Technology |
|---|---|
| Web Framework | FastAPI |
| ASGI Server | Uvicorn |
| Database | PostgreSQL + SQLAlchemy |
| Observability | Elasticsearch 8 |
| LLM | Google Gemini (via OpenAI-compatible API) |
| Bot Integration | python-telegram-bot 21 |
| Reverse Proxy | Nginx |
| Process Manager | systemd |
| Testing | pytest + httpx |

---

## 📄 Detailed Documentation

See [`AI_Nutritient_Agent.md`](./AI_Nutritient_Agent.md) for the full system design document including all skill specifications, mathematical models, database schema, and architectural philosophy.

---

## 📜 License

This project is for demonstration and portfolio purposes.
