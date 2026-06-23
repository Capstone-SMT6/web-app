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
    return _DAYS_MAP.get(intensity, 4)


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

_DAILY_FOCUS = {
    GoalEnum.weight_loss: [
        ["kardio", "cardio", "perut", "inti", "core", "full body"], # Cardio & Core Focus
        ["dada", "chest", "bahu", "shoulders", "triceps", "punggung", "kardio", "cardio"], # Upper & Cardio
        ["kaki", "legs", "bokong", "glutes", "kardio", "cardio"], # Lower & Cardio
        ["full_body", "full body", "chest", "dada", "kaki", "legs"], # Full Body HIIT
    ],
    GoalEnum.muscle_gain: [
        ["dada", "chest", "bahu", "shoulders", "triceps", "punggung", "back", "biceps", "lengan"], # Upper Body
        ["kaki", "legs", "bokong", "glutes", "perut", "inti", "core"], # Lower Body & Core
        ["full_body", "full body", "chest", "dada", "kaki", "legs"], # Full Body Power
    ],
    GoalEnum.maintain: [
        ["dada", "chest", "bahu", "shoulders", "punggung", "perut", "inti", "core"], # Upper & Core
        ["kaki", "legs", "bokong", "glutes", "kardio", "cardio"], # Lower & Cardio
        ["full_body", "full body"], # Full Body
    ],
}


def _match_exercise_focus(exercise: Exercise, focus_groups: List[str]) -> bool:
    """Check if an exercise targets any of the desired muscle groups."""
    all_muscles = [m.lower() for m in (exercise.muscleGroups or []) + (exercise.secondaryMuscles or [])]
    
    # If the focus group requests full body, we can just allow exercises that are full body or major compound
    if "full_body" in focus_groups or "full body" in focus_groups:
        return True
        
    return any(fg.lower() in " ".join(all_muscles) for fg in focus_groups)


# ── Main generator ─────────────────────────────────────────────────────────

def generate_plan(profile: UserFitnessProfile, session: Session, selected_days: List[str] = None, applied_constraints: List[str] = None) -> ExercisePlan:
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

    # Filter by equipment
    user_equipment = set(eq.lower() for eq in (profile.equipment or []))
    if user_equipment:
        def _equip_ok(ex: Exercise) -> bool:
            req = set(r.lower() for r in (ex.equipmentRequired or []))
            # exercise is OK if it requires no equipment, or all required equipment is available
            return len(req) == 0 or req.issubset(user_equipment)
        eligible = [e for e in eligible if _equip_ok(e)]

    # Index by category for quick lookup
    by_category: Dict[str, List[Exercise]] = {}
    for ex in eligible:
        by_category.setdefault(ex.category.value, []).append(ex)

    # 6. Build days
    focus_templates = _DAILY_FOCUS.get(profile.goal, _DAILY_FOCUS[GoalEnum.maintain])
    scheme = _set_rep_scheme(profile.goal.value, profile.difficultyLevel.value)

    for dow in range(7):
        is_rest = dow in rest_indices
        plan_day = PlanDay(
            plan_id=plan.id,
            day_of_week=dow,
            is_rest_day=is_rest,
        )
        session.add(plan_day)
        session.flush()

        if is_rest:
            continue

        # Pick focus for this training day
        training_day_index = sum(1 for d in range(dow) if d not in rest_indices)
        focus = focus_templates[training_day_index % len(focus_templates)]

        # Select exercises matching focus
        candidates = [e for e in eligible if _match_exercise_focus(e, focus)]
        # Fallback: if not enough candidates, use all eligible
        if len(candidates) < 2:
            candidates = eligible

        # Pick up to 4-6 exercises for the day (varied by intensity)
        n_exercises = min(6 if profile.intensity in (IntensityEnum.medium, IntensityEnum.high) else 4, len(candidates))

        # Rotate through candidates deterministically based on day
        start_idx = dow * 2 % max(len(candidates), 1)
        selected = []
        for i in range(n_exercises):
            idx = (start_idx + i) % len(candidates)
            selected.append(candidates[idx])

        # Create PlanDayExercise entries
        for order, exercise in enumerate(selected, start=1):
            sets = scheme["sets"]
            reps = scheme["reps"]
            duration = None

            # Plank-type exercises use duration instead of reps
            if "plank" in exercise.name.lower():
                reps = None
                duration = 30 if profile.skillLevel == SkillLevelEnum.beginner else 45 if profile.skillLevel == SkillLevelEnum.intermediate else 60

            pde = PlanDayExercise(
                plan_day_id=plan_day.id,
                exercise_id=exercise.id,
                order=order,
                target_sets=sets,
                target_reps=reps,
                target_duration_seconds=duration,
            )
            session.add(pde)

    session.commit()
    session.refresh(plan)
    return plan


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
        select(PlanDay).where(PlanDay.plan_id == plan.id).order_by(PlanDay.day_of_week)
    ).all()

    # Determine default rest seconds based on difficulty
    _rest_map = {"level_1": 45, "level_2": 30, "level_3": 20}
    default_rest = _rest_map.get(plan.difficulty_level.value, 30)

    days_data = []
    for day in days:
        exercises_raw = session.exec(
            select(PlanDayExercise)
            .where(PlanDayExercise.plan_day_id == day.id)
            .order_by(PlanDayExercise.order)
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
