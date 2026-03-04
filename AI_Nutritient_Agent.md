# Adaptive AI Nutrition Agent
## A Production-Structured, Skill-Based, Closed-Loop AI System
### FastAPI + PostgreSQL + Nginx + ElasticSearch + Telegram

---

# 1. Executive Overview

The Adaptive AI Nutrition Agent is a stateful, modular, skill-based backend system that generates and dynamically adjusts multi-week diet plans using deterministic physiological modeling combined with constrained LLM reasoning.

This system is intentionally designed to:

- Demonstrate production backend architecture
- Showcase infrastructure fundamentals (Nginx, PostgreSQL, ElasticSearch)
- Implement clean skill-based orchestration
- Separate deterministic logic from probabilistic reasoning
- Operate as a closed-loop adaptive control system
- Integrate with Telegram via secure webhook

This is NOT a chatbot wrapper.
This is a structured backend intelligence system.

---

# 2. Core Design Philosophy

## 2.1 Deterministic First, LLM Second

All physiological and safety-critical calculations are deterministic:

- TDEE
- Calorie targets
- Macro distribution
- Plateau detection
- Weight projection
- Adaptive adjustments

LLM is only used for:

- Meal plan generation
- Natural language explanations
- Coaching summaries
- Structured creative outputs

This ensures:

- Safety
- Mathematical accuracy
- Predictability
- Debuggability
- Reproducibility

---

## 2.2 Closed-Loop Feedback System

This system operates like a control loop:

1. User sets goal
2. System calculates targets
3. User follows plan
4. User logs weekly feedback
5. System evaluates performance
6. System detects plateau
7. System adjusts calories
8. System regenerates plan

This loop continues until goal is achieved.

---

# 3. High-Level Production Architecture

```
Internet
   ↓
Telegram
   ↓
Nginx (SSL + Reverse Proxy)
   ↓
FastAPI (Webhook Endpoint)
   ↓
Agent Controller
   ↓
Skill Layer
   ↓
PostgreSQL (Persistent Structured State)
   ↓
ElasticSearch (Structured Logs & Observability)
```

---

# 4. Infrastructure Stack

## 4.1 Nginx

Purpose:
- SSL termination (HTTPS)
- Reverse proxy
- Route /telegram to FastAPI
- Protect backend from direct exposure

Flow:

Telegram → https://yourdomain.com/telegram  
→ Nginx  
→ FastAPI (127.0.0.1:8000)

---

## 4.2 FastAPI

Responsibilities:

- Telegram webhook endpoint
- Input validation
- Agent orchestration
- Skill execution
- Database interaction
- Structured logging
- Error handling

FastAPI acts as the application layer.

---

## 4.3 PostgreSQL

Used for:

- User profiles
- Nutrition state
- Weekly logs
- Projections
- Adaptation history

Why PostgreSQL:

- Structured relational modeling
- Referential integrity
- Transactions
- Long-term durability
- Production-grade

---

## 4.4 ElasticSearch

Used for:

- Structured interaction logs
- Plateau detection events
- Adaptation history
- Error tracking
- Search & monitoring

Example log document:

```json
{
  "user_id": 5544314450,
  "event": "plateau_detected",
  "adjustment": -150,
  "week": 4,
  "timestamp": "2026-03-01T10:00:00Z"
}
```

---

## 4.5 systemd

Used to:

- Run FastAPI as background service
- Auto-restart on failure
- Manage service lifecycle

---

# 5. Database Schema (PostgreSQL)

## 5.1 users

- id (BIGINT PRIMARY KEY) — Telegram ID
- name
- age
- gender
- height_cm
- activity_level
- goal
- goal_intensity
- diet_type
- created_at

---

## 5.2 nutrition_state

- user_id (FK → users.id)
- current_weight
- maintenance_calories
- daily_calorie_target
- protein_target_g
- carbs_target_g
- fats_target_g
- plateau_flag
- current_week_number
- updated_at

---

## 5.3 weekly_logs

- id (SERIAL PRIMARY KEY)
- user_id (FK → users.id)
- week_number
- logged_weight
- adherence_percentage
- timestamp

---

## 5.4 projections

- user_id
- projected_week
- projected_weight

---

# 6. Skill-Based Architecture

Each skill:

- Has single responsibility
- Has strict input schema
- Has strict output schema
- Is independently testable
- Does not mix DB logic unless explicitly persistence-related

---

# 7. Deterministic Skills

## 7.1 TDEESkill

Uses Mifflin-St Jeor Equation.

For males:
BMR = (10 × weight) + (6.25 × height) - (5 × age) + 5

For females:
BMR = (10 × weight) + (6.25 × height) - (5 × age) - 161

maintenance_calories = BMR × activity_multiplier

---

## 7.2 CalorieTargetSkill

Adjusts calories based on goal and intensity.

Cut:
- Conservative → -300 kcal
- Balanced → -500 kcal
- Aggressive → -700 kcal

Bulk:
- Conservative → +200 kcal
- Balanced → +350 kcal
- Aggressive → +500 kcal

Maintain:
- maintenance_calories

---

## 7.3 MacroDistributionSkill

Rules:

- Protein based on bodyweight
- Fat ≈ 25% of total calories
- Carbs = remaining calories

---

## 7.4 WeightProjectionSkill

Uses:

1 kg fat ≈ 7700 kcal

Projected weekly change:
weekly_calorie_difference / 7700

---

## 7.5 PlateauDetectionSkill

Plateau if:

- Last 2 weeks weight change < 0.2 kg
- Adherence ≥ 80%
- Goal = cut or bulk

If true:
plateau_flag = True

---

## 7.6 AdaptiveAdjustmentSkill

If plateau:

Cut → -150 kcal  
Bulk → +100 kcal  
Maintain → minimal adjustment  

Safety rules:

- Never go below BMR
- Never exceed safe surplus

---

# 8. LLM-Based Skills

LLM is constrained and used only for:

## 8.1 WeeklyMealPlanSkill

Generates structured 7-day plan.

Input:
- Macro targets
- Diet type
- Dislikes

Output:
Strict JSON format only.

---

## 8.2 MultiWeekPlannerSkill

Loops weekly generation across tenure.

---

## 8.3 CoachingSummarySkill

Generates:

- Motivation
- Explanations
- Plateau reasoning

---

# 9. Agent Controller

## 9.1 New User Flow

1. LoadUserState
2. TDEESkill
3. CalorieTargetSkill
4. MacroDistributionSkill
5. WeightProjectionSkill
6. MultiWeekPlannerSkill
7. SavePlan

---

## 9.2 Returning User Flow

1. LoadUserState
2. PlateauDetectionSkill
3. If plateau → AdaptiveAdjustmentSkill
4. Regenerate next week
5. SavePlan

---

# 10. Closed-Loop Adaptive Behavior

Weekly:

User logs:
- Weight
- Adherence

System:
- Evaluates delta
- Detects plateau
- Adjusts calories
- Updates projection
- Logs event in ElasticSearch
- Regenerates structured plan

This creates adaptive evolution.

---

# 11. Directory Structure

```
adaptive_ai_nutrition/
├── app/
│   ├── main.py
│   ├── webhook.py
│   └── controller.py
├── skills/
│   ├── base_skill.py
│   ├── nutrition/
│   ├── planning/
│   ├── projection/
│   ├── adaptation/
│   └── persistence/
├── db/
│   ├── models.py
│   └── session.py
├── logging/
├── nginx/
│   └── nginx.conf
└── systemd/
    └── ai_nutrition.service
```

---

# 12. Model Strategy

Recommended:

Primary Model:
Gemini 3.1 Pro (High) — planning & reasoning

Optional Later:
Gemini Flash — classification & lightweight tasks

Deterministic logic remains outside LLM.

---

# 13. What This Project Demonstrates

- Production-style architecture
- Infrastructure awareness
- Deterministic AI system design
- Hybrid reasoning model
- Structured state modeling
- Closed-loop adaptation
- Separation of concerns
- Observability practices
- Backend engineering maturity

---

# 14. Final Definition

The Adaptive AI Nutrition Agent is a production-structured, modular, stateful, skill-based backend system that implements deterministic physiological modeling combined with constrained LLM reasoning, deployed using Nginx, PostgreSQL, and ElasticSearch, and integrated with Telegram via webhook.

It is:

- Not a prompt wrapper
- Not a stateless chatbot
- Not a simple meal generator

It is a structured adaptive control system built to demonstrate real backend engineering competence.
