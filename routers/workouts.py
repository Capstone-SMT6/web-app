from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from database import get_session
from models import WorkoutSession, ExerciseLog, DailyLog, UserStats, DayTypeEnum
from routers.users import get_current_user, User

router = APIRouter(prefix="/api/workouts", tags=["workouts"])


# ─────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────

class ExerciseLogInput(BaseModel):
    exercise_name: str   # nama latihan (free text untuk sekarang)
    set_number: int
    reps_completed: int

class StartWorkoutRequest(BaseModel):
    duration_seconds: int = 0
    logs: List[ExerciseLogInput] = []


# ─────────────────────────────────────────
# Helpers — streak logic
# ─────────────────────────────────────────

def _recalculate_streak(user_id: str, session: Session) -> None:
    """
    Hitung ulang currentStreak berdasarkan DailyLog.
    Streak bertambah jika hari ini atau kemarin sudah ada workout_completed.
    """
    stats = session.exec(select(UserStats).where(UserStats.user_id == user_id)).first()
    if not stats:
        return

    today = date.today()

    # Ambil semua hari latihan, urutkan descending
    logs = session.exec(
        select(DailyLog)
        .where(DailyLog.user_id == user_id)
        .where(DailyLog.day_type == DayTypeEnum.workout_completed)
        .order_by(DailyLog.date.desc())
    ).all()

    if not logs:
        stats.currentStreak = 0
        stats.lastActiveDate = None
    else:
        streak = 0
        expected = today
        for log in logs:
            if log.date == expected:
                streak += 1
                expected = expected - timedelta(days=1)
            elif log.date == expected - timedelta(days=1):
                # Boleh mundur 1 hari (toleransi zona waktu)
                streak += 1
                expected = log.date - timedelta(days=1)
            else:
                break

        stats.currentStreak = streak
        stats.lastActiveDate = logs[0].date

        if streak > stats.longestStreak:
            stats.longestStreak = streak

    stats.updatedAt = datetime.now(timezone.utc)
    session.add(stats)
    session.commit()


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────

@router.post("/sessions", status_code=201)
def start_workout_session(
    body: StartWorkoutRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Simpan sesi latihan + log reps, lalu update DailyLog & streak.
    """
    today = date.today()

    # 1. Buat WorkoutSession
    workout_session = WorkoutSession(
        user_id=current_user.id,
        date=today,
        duration_seconds=body.duration_seconds,
    )
    session.add(workout_session)
    session.flush()  # dapatkan ID

    # 2. Simpan ExerciseLog (reps per set)
    total_reps = 0
    for log in body.logs:
        exercise_log = ExerciseLog(
            session_id=workout_session.id,
            exercise_id="00000000-0000-0000-0000-000000000000",  # placeholder UUID
            set_number=log.set_number,
            reps_completed=log.reps_completed,
            is_manual_input=True,
        )
        session.add(exercise_log)
        total_reps += log.reps_completed

    # 3. Update total reps di UserStats (sederhana: semua dianggap push up)
    stats = session.exec(select(UserStats).where(UserStats.user_id == current_user.id)).first()
    if stats:
        stats.totalPushUps += total_reps
        stats.updatedAt = datetime.now(timezone.utc)
        session.add(stats)

    # 4. Tandai hari ini sebagai workout_completed di DailyLog (UPSERT-style)
    existing_daily = session.exec(
        select(DailyLog)
        .where(DailyLog.user_id == current_user.id)
        .where(DailyLog.date == today)
    ).first()

    if not existing_daily:
        daily_log = DailyLog(
            user_id=current_user.id,
            date=today,
            day_type=DayTypeEnum.workout_completed,
        )
        session.add(daily_log)
    else:
        existing_daily.day_type = DayTypeEnum.workout_completed
        session.add(existing_daily)

    session.commit()

    # 5. Hitung ulang streak setelah commit
    _recalculate_streak(current_user.id, session)

    return {
        "message": "Workout session saved!",
        "session_id": workout_session.id,
        "total_reps": total_reps,
        "streak": stats.currentStreak if stats else 0,
    }


@router.get("/sessions", status_code=200)
def get_my_sessions(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Ambil semua sesi latihan user (untuk kalender)."""
    sessions = session.exec(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == current_user.id)
        .order_by(WorkoutSession.date.desc())
    ).all()
    return sessions
