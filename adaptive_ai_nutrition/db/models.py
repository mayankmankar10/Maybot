"""
db/models.py
SQLAlchemy ORM models exactly matching the schema in AI_Nutritient_Agent.md.
Tables: users, nutrition_state, weekly_logs, projections.
No business logic. Pure data model.
"""
from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float,
    ForeignKey, Integer, String, Text,
)
from db.session import Base


class User(Base):
    """
    Section 5.1 — users table.
    Primary key is the Telegram user ID (BIGINT).
    """
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)   # Telegram ID
    name = Column(String(120), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(10), nullable=False)              # 'male' | 'female'
    height_cm = Column(Float, nullable=False)
    activity_level = Column(String(30), nullable=False)     # sedentary / light / moderate / active / very_active
    goal = Column(String(20), nullable=False)               # cut | bulk | maintain
    goal_intensity = Column(String(20), nullable=False)     # conservative | balanced | aggressive
    diet_type = Column(String(30), nullable=True)           # vegetarian / vegan / omnivore / etc.
    initial_weight = Column(Float, nullable=True)           # weight at setup — baseline for progress chart
    foods_to_avoid = Column(Text, nullable=True, default="")  # comma-separated, e.g. "nuts, dairy, shellfish"
    target_weight  = Column(Float, nullable=True)              # user's goal weight in kg
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NutritionState(Base):
    """
    Section 5.2 — nutrition_state table.
    Holds the live macro targets and plateau flag for a user.
    """
    __tablename__ = "nutrition_state"

    user_id = Column(BigInteger, ForeignKey("users.id"), primary_key=True)
    current_weight = Column(Float, nullable=False)
    maintenance_calories = Column(Float, nullable=False)
    daily_calorie_target = Column(Float, nullable=False)
    protein_target_g = Column(Float, nullable=False)
    carbs_target_g = Column(Float, nullable=False)
    fats_target_g = Column(Float, nullable=False)
    plateau_flag = Column(Boolean, default=False, nullable=False)
    current_week_number = Column(Integer, default=1, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class WeeklyLog(Base):
    """
    Section 5.3 — weekly_logs table.
    User's self-reported weight and adherence each week.
    """
    __tablename__ = "weekly_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    week_number = Column(Integer, nullable=False)
    logged_weight = Column(Float, nullable=False)
    adherence_percentage = Column(Float, nullable=False)    # 0–100
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)


class Projection(Base):
    """
    Section 5.4 — projections table.
    Weekly weight projection entries for a user's plan.
    """
    __tablename__ = "projections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    projected_week = Column(Integer, nullable=False)
    projected_weight = Column(Float, nullable=False)
