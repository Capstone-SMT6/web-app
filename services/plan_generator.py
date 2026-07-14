"""
Rule-based training plan generator.

Generates a weekly ExercisePlan from a UserFitnessProfile by applying:
  - Goal-based templates (weight_loss, muscle_gain, maintain)
  - Difficulty gating (beginner/intermediate/advanced)
  - Equipment filtering
  - Intensity-driven days-per-week
  - BMR/TDEE calculation
"""

import math
from datetime import date
from typing import List, Dict, Optional
from sqlmodel import Session, select
import os
import json
from google import genai
from google.genai import types

from models import (
    UserFitnessProfile,
    ExercisePlan,
    PlanDay,
    PlanDayExercise,
    Exercise,
    GoalEnum,
    SkillLevelEnum,
    IntensityEnum,
    DifficultyLevelEnum,
    ExerciseCategory,
    ExerciseDifficulty,
)


# ── Supported exercises (only those with pose detection) ───────────────────
SUPPORTED_SLUGS = {"push-up", "squat", "plank", "sit-up"}


# ── BMR / TDEE helpers ─────────────────────────────────────────────────────

def _calculate_bmr(gender: str, weight: float, height: float, age: int) -> float:
    """Mifflin-St Jeor equation."""
    if gender == "male":
        return 10 * weight + 6.25 * height - 5 * age + 5
    else:
        return 10 * weight + 6.25 * height - 5 * age - 161


def _calculate_tdee(bmr: float, intensity: str) -> float:
    multipliers = {"low": 1.375, "medium": 1.55, "high": 1.725}
    return bmr * multipliers.get(intensity, 1.55)


def _calculate_macros(goal: str, tdee: float) -> dict:
    """Return {kcal, protein_g, carbs_g, fat_g}."""
    if goal == GoalEnum.weight_loss:
        kcal = tdee - 500
    elif goal == GoalEnum.muscle_gain:
        kcal = tdee + 300
    else:
        kcal = tdee

    protein_ratio = 0.30 if goal == GoalEnum.muscle_gain else 0.25
    fat_ratio = 0.25
    carb_ratio = 1.0 - protein_ratio - fat_ratio

    return {
        "kcal": round(kcal),
        "protein_g": round(kcal * protein_ratio / 4),
        "carbs_g": round(kcal * carb_ratio / 4),
        "fat_g": round(kcal * fat_ratio / 9),
    }


# ── Intensity → days per week ──────────────────────────────────────────────

_DAYS_MAP = {
    IntensityEnum.low: 3,
    IntensityEnum.medium: 4,
    IntensityEnum.high: 5,
}


def _days_per_week(intensity: str) -> int:
    try:
        enum_val = IntensityEnum(intensity)
    except ValueError:
        enum_val = IntensityEnum.medium
    return _DAYS_MAP.get(enum_val, 4)


# ── Rest-day placement ─────────────────────────────────────────────────────

def _rest_days(days_active: int) -> List[int]:
    """Return day-of-week indices (0=Mon … 6=Sun) that should be rest days."""
    all_days = list(range(7))
    if days_active >= 7:
        return []
    # Spread rest days evenly; always include Sunday (6) as rest when possible
    n_rest = 7 - days_active
    rest = []
    step = 7 / n_rest
    for i in range(n_rest):
        d = int((6 + i * step) % 7)
        if d not in rest:
            rest.append(d)
        else:
            # fallback: pick next available
            for fallback in all_days:
                if fallback not in rest:
                    rest.append(fallback)
                    break
    return rest


# ── Goal-based set/rep schemes ──────────────────────────────────────────────

def _set_rep_scheme(goal: str, difficulty: str) -> Dict[str, int]:
    """Return (sets, reps, duration_seconds) template based on goal."""
    if goal == GoalEnum.weight_loss:
        return {"sets": 3, "reps": 15, "duration": 0}
    elif goal == GoalEnum.muscle_gain:
        return {"sets": 4, "reps": 10, "duration": 0}
    else:  # maintain
        return {"sets": 3, "reps": 12, "duration": 0}


# ── Allowed difficulty levels based on skill ────────────────────────────────

_ALLOWED_DIFFICULTIES = {
    SkillLevelEnum.beginner: [ExerciseDifficulty.beginner],
    SkillLevelEnum.intermediate: [ExerciseDifficulty.beginner, ExerciseDifficulty.intermediate],
    SkillLevelEnum.advanced: [ExerciseDifficulty.beginner, ExerciseDifficulty.intermediate, ExerciseDifficulty.advanced],
}


# ── Muscle-group split templates ────────────────────────────────────────────
# Only references muscle groups covered by the 4 supported exercises:
#   Push Up  → dada, chest, bahu, shoulders, triceps
#   Squat    → kaki, legs, bokong, glutes
#   Plank    → inti, core, perut, abs
#   Sit Up   → perut, abs, inti, core

_DAILY_FOCUS = {
    GoalEnum.weight_loss: [
        ["dada", "chest", "kaki", "legs", "inti", "core"],       # Push Up + Squat + Plank
        ["perut", "abs", "kaki", "legs", "dada", "chest"],       # Sit Up + Squat + Push Up
        ["inti", "core", "dada", "chest", "perut", "abs"],       # Plank + Push Up + Sit Up
        ["kaki", "legs", "inti", "core", "perut", "abs"],        # Squat + Plank + Sit Up
    ],
    GoalEnum.muscle_gain: [
        ["dada", "chest", "kaki", "legs", "inti", "core"],       # Push Up + Squat + Plank
        ["perut", "abs", "kaki", "legs", "dada", "chest"],       # Sit Up + Squat + Push Up
        ["dada", "chest", "inti", "core", "perut", "abs"],       # Push Up + Plank + Sit Up
    ],
    GoalEnum.maintain: [
        ["dada", "chest", "inti", "core", "perut", "abs"],       # Push Up + Plank + Sit Up
        ["kaki", "legs", "dada", "chest", "inti", "core"],       # Squat + Push Up + Plank
        ["kaki", "legs", "perut", "abs", "dada", "chest"],       # Squat + Sit Up + Push Up
    ],
}


def _match_exercise_focus(exercise: Exercise, focus_groups: List[str]) -> bool:
    """Check if an exercise targets any of the desired muscle groups."""
    all_muscles = [m.lower() for m in (exercise.muscleGroups or []) + (exercise.secondaryMuscles or [])]
    
    # If the focus group requests full body, we can just allow exercises that are full body or major compound
    if "full_body" in focus_groups or "full body" in focus_groups:
        return True
        
    return any(fg.lower() in " ".join(all_muscles) for fg in focus_groups)


def _generate_plan_rule_based(profile: UserFitnessProfile, active_days: int, eligible: List[Exercise], rest_indices: set) -> list:
    import random
    days_data = []
    
    focus_list = _DAILY_FOCUS.get(profile.goal, _DAILY_FOCUS[GoalEnum.maintain])
    
    focus_idx = 0
    for day_of_week in range(7):
        if day_of_week in rest_indices:
            days_data.append({
                "day_of_week": day_of_week,
                "is_rest_day": True,
                "exercises": []
            })
            continue
            
        current_focus = focus_list[focus_idx % len(focus_list)]
        focus_idx += 1
        
        shuffled = eligible.copy()
        random.shuffle(shuffled)
        
        selected_exs = []
        for muscle in current_focus:
            for ex in shuffled:
                if _match_exercise_focus(ex, [muscle]) and ex not in selected_exs:
                    selected_exs.append(ex)
                    break
            if len(selected_exs) >= 4:
                break
                
        if len(selected_exs) < 3:
            for ex in shuffled:
                if ex not in selected_exs:
                    selected_exs.append(ex)
                if len(selected_exs) >= 3:
                    break
                    
        ex_list = []
        for ex in selected_exs:
            if ex.category == "Repetisi":
                ex_list.append({
                    "slug": ex.slug,
                    "target_sets": 3,
                    "target_reps": 10 if profile.difficultyLevel == "pemula" else 15
                })
            else:
                ex_list.append({
                    "slug": ex.slug,
                    "target_sets": 3,
                    "target_duration_seconds": 30 if profile.difficultyLevel == "pemula" else 60
                })
                
        days_data.append({
            "day_of_week": day_of_week,
            "is_rest_day": False,
            "exercises": ex_list
        })
        
    return days_data

# ── Main generator ─────────────────────────────────────────────────────────

def generate_plan(profile: UserFitnessProfile, session: Session, selected_days: Optional[List[str]] = None, applied_constraints: Optional[List[str]] = None) -> ExercisePlan:
    """
    Generate a complete weekly ExercisePlan for the given profile.
    Persists ExercisePlan, PlanDay, and PlanDayExercise rows.
    Returns the created ExercisePlan.
    """

    # 1. Calculate & persist metabolic stats
    bmr = _calculate_bmr(profile.gender.value, profile.weight, profile.height, profile.age)
    tdee = _calculate_tdee(bmr, profile.intensity.value)
    macros = _calculate_macros(profile.goal.value, tdee)

    profile.bmr = round(bmr, 1)
    profile.tdee = round(tdee, 1)
    profile.target_daily_kcal = macros["kcal"]
    profile.macros_json = macros
    session.add(profile)

    # 2. Deactivate previous plans
    old_plans = session.exec(
        select(ExercisePlan).where(
            ExercisePlan.user_id == profile.user_id,
            ExercisePlan.is_active == True,
        )
    ).all()
    for op in old_plans:
        op.is_active = False
        session.add(op)

    # 3. Create plan header
    DAY_INDEX = {
        "senin": 0,
        "selasa": 1,
        "rabu": 2,
        "kamis": 3,
        "jumat": 4,
        "sabtu": 5,
        "minggu": 6,
    }
    if selected_days:
        day_indices = {DAY_INDEX[d] for d in selected_days if d in DAY_INDEX}
        rest_indices = {i for i in range(7) if i not in day_indices}
        active_days = len(day_indices)
    else:
        active_days = _days_per_week(profile.intensity.value)
        rest_indices = set(_rest_days(active_days))

    plan = ExercisePlan(
        user_id=profile.user_id,
        fitness_profile_id=profile.id,
        is_active=True,
        goal=profile.goal,
        days_per_week=active_days,
        start_date=date.today(),
        difficulty_level=profile.difficultyLevel,
        applied_constraints=applied_constraints if applied_constraints is not None else (profile.equipment or []),
    )
    session.add(plan)
    session.flush()  # get plan.id

    # 5. Load eligible exercises
    allowed_diff = _ALLOWED_DIFFICULTIES.get(profile.skillLevel, [ExerciseDifficulty.beginner])
    all_exercises = session.exec(
        select(Exercise).where(Exercise.isActive == True)
    ).all()

    # Filter by difficulty
    eligible = [e for e in all_exercises if e.difficulty in allowed_diff]

    # Filter to only supported exercises (those with pose detection)
    eligible = [e for e in eligible if e.slug in SUPPORTED_SLUGS]

    # Generate JSON structure via Gemini
    try:
        gemini_days = _generate_plan_via_gemini(profile, active_days, eligible, rest_indices)
        
        # Additional safety check in case Gemini returns empty list
        if not gemini_days:
            print("Gemini returned empty plan, falling back to rule-based generation")
            gemini_days = _generate_plan_rule_based(profile, active_days, eligible, rest_indices)
            
    except Exception as e:
        print(f"Failed to generate plan via Gemini: {e}")
        gemini_days = _generate_plan_rule_based(profile, active_days, eligible, rest_indices)

    # 6. Build days and exercises from Gemini JSON
    # Build a lookup for exercise by slug
    ex_by_slug = {e.slug: e for e in eligible}

    for day_data in gemini_days:
        dow = int(day_data.get("day_of_week", 0))
        is_rest = bool(day_data.get("is_rest_day", False))
        
        plan_day = PlanDay(
            plan_id=plan.id,
            day_of_week=dow,
            is_rest_day=is_rest,
        )
        session.add(plan_day)
        session.flush()

        if is_rest:
            continue
            
        exercises_list = day_data.get("exercises", [])
        for order, ex_data in enumerate(exercises_list, start=1):
            slug = ex_data.get("slug")
            if slug not in ex_by_slug:
                continue
                
            exercise = ex_by_slug[slug]
            pde = PlanDayExercise(
                plan_day_id=plan_day.id,
                exercise_id=exercise.id,
                order=order,
                target_sets=ex_data.get("target_sets", 3),
                target_reps=ex_data.get("target_reps"),
                target_duration_seconds=ex_data.get("target_duration_seconds"),
            )
            session.add(pde)

    session.commit()
    session.refresh(plan)
    return plan

def _generate_plan_via_gemini(profile: UserFitnessProfile, active_days: int, eligible: List[Exercise], rest_indices: set) -> list:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set.")
    client = genai.Client(api_key=api_key)
    
    exercise_slugs = [e.slug for e in eligible]
    prompt = f"""
You are an expert AI Personal Trainer. Generate a 7-day weekly exercise plan for a user.
User profile:
- Age: {profile.age}
- Gender: {profile.gender.value if profile.gender else 'any'}
- Goal: {profile.goal.value if profile.goal else 'maintain'}
- Skill Level: {profile.skillLevel.value if profile.skillLevel else 'beginner'}
- Training days per week: {active_days}

You must ONLY use the following exercises (identified by their slugs): {", ".join(exercise_slugs)}.
For 'plank', specify 'target_duration_seconds' and set 'target_sets' to 3-5, but 'target_reps' to null.
For others, specify 'target_sets' and 'target_reps', but 'target_duration_seconds' to null.

Return ONLY a JSON array of 7 objects (representing Monday to Sunday). 
Each object must have:
- "day_of_week": int (0 to 6)
- "is_rest_day": boolean
- "exercises": array of objects (empty if is_rest_day=true)
  - "slug": string (from the allowed list)
  - "target_sets": int
  - "target_reps": int or null
  - "target_duration_seconds": int or null

Make sure there are exactly {active_days} days where is_rest_day=false.
The days of the week are 0 (Monday) to 6 (Sunday).
The following days MUST be rest days (is_rest_day=true) and have an empty exercises array: {list(rest_indices)}.
All other days MUST be active days (is_rest_day=false) and contain exercises.
"""
    models_to_try = ["gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-flash-latest"]
    response = None
    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            break
        except Exception as e:
            last_error = e
            print(f"Model {model_name} failed in plan generation: {e}. Trying next...")
            
    if response is not None and response.text:
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        return json.loads(raw_text.strip())

    # Fallback to Groq
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            print("Trying Groq fallback in plan generation...")
            import httpx
            response_json = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                },
                timeout=30.0
            )
            if response_json.status_code == 200:
                raw_text = response_json.json()["choices"][0]["message"]["content"].strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                elif raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                return json.loads(raw_text.strip())
        except Exception as groq_err:
            print(f"Groq plan generation failed: {groq_err}")

    # Fallback to OpenAI
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            print("Trying OpenAI fallback in plan generation...")
            import httpx
            response_json = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                },
                timeout=30.0
            )
            if response_json.status_code == 200:
                raw_text = response_json.json()["choices"][0]["message"]["content"].strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                elif raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                return json.loads(raw_text.strip())
        except Exception as openai_err:
            print(f"OpenAI plan generation failed: {openai_err}")

    if last_error:
        raise last_error
    raise RuntimeError("Plan generation failed across all primary and fallback endpoints.")




def get_active_plan(user_id: str, session: Session) -> Optional[dict]:
    """
    Return the user's active plan as a flat dict matching the mobile app's
    ActiveExercisePlan.fromJson() format:
    {
        "id": str,
        "goal": str,
        "days_per_week": int,
        "difficulty_level": str,
        "days": [ { "day_of_week": int, "is_rest_day": bool, "exercises": [...] } ]
    }
    """
    plan = session.exec(
        select(ExercisePlan).where(
            ExercisePlan.user_id == user_id,
            ExercisePlan.is_active == True,
        )
    ).first()

    if not plan:
        return None

    days = session.exec(
        select(PlanDay).where(PlanDay.plan_id == plan.id).order_by(PlanDay.day_of_week)  # type: ignore
    ).all()

    # Determine default rest seconds based on difficulty
    _rest_map = {"level_1": 45, "level_2": 30, "level_3": 20}
    default_rest = _rest_map.get(plan.difficulty_level.value, 30)

    days_data = []
    for day in days:
        exercises_raw = session.exec(
            select(PlanDayExercise)
            .where(PlanDayExercise.plan_day_id == day.id)
            .order_by(PlanDayExercise.order)  # type: ignore
        ).all()

        exercises = []
        for pde in exercises_raw:
            ex = session.get(Exercise, pde.exercise_id)
            exercises.append({
                "id": str(pde.exercise_id),
                "name": ex.name if ex else "Unknown",
                "description": ex.description if ex else "",
                "category": ex.category.value if ex else "strength",
                "muscleGroups": ex.muscleGroups if ex else [],
                "order": pde.order,
                # Field names matching Flutter ExerciseTarget.fromJson()
                "sets": pde.target_sets,
                "reps": pde.target_reps,
                "target_duration_seconds": pde.target_duration_seconds,
                "rest_seconds": default_rest,
                # Legacy field names (backward compat with workouts.py)
                "target_sets": pde.target_sets,
                "target_reps": pde.target_reps,
                "exerciseType": _exercise_type_from_name(ex.name if ex else ""),
                "poseAngle": _pose_angle_from_name(ex.name if ex else ""),
            })

        days_data.append({
            "day_of_week": day.day_of_week,
            "is_rest_day": day.is_rest_day,
            "exercises": exercises,
        })

    profile = session.get(UserFitnessProfile, plan.fitness_profile_id)

    # Flat structure matching Flutter ActiveExercisePlan.fromJson()
    return {
        "id": plan.id,
        "goal": plan.goal.value,
        "days_per_week": plan.days_per_week,
        "start_date": plan.start_date.isoformat(),
        "difficulty_level": plan.difficulty_level.value,
        "nutrition": {
            "bmr": profile.bmr if profile else 0.0,
            "tdee": profile.tdee if profile else 0.0,
            "target_daily_kcal": profile.target_daily_kcal if profile else 0.0,
            "macros": profile.macros_json if profile else {},
        },
        "days": days_data,
    }


def _exercise_type_from_name(name: str) -> str:
    """Map exercise name to mobile-app exerciseType string."""
    lower = name.lower()
    if "push" in lower and "up" in lower:
        return "pushup"
    elif "sit" in lower and "up" in lower:
        return "situp"
    elif "squat" in lower:
        return "squat"
    elif "plank" in lower:
        return "plank"
    elif "lunge" in lower:
        return "lunge"
    elif "burpee" in lower:
        return "burpee"
    elif "climb" in lower or "mountain" in lower:
        return "mountain_climber"
    return "other"


def _pose_angle_from_name(name: str) -> str:
    """Determine recommended camera angle from exercise name."""
    lower = name.lower()
    if any(w in lower for w in ["push", "squat", "lunge", "plank", "burpee", "climb"]):
        return "side"
    if any(w in lower for w in ["sit", "crunch"]):
        return "side"
    return "front"
