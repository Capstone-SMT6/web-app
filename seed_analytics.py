import argparse
import random
from datetime import date, timedelta
from sqlmodel import Session, select
from database import engine
from models import User, FoodLog, WorkoutSession, DailyLog, NutritionSummary, UserStats, FoodItem, DayTypeEnum, ExercisePlan, PlanDay
from routers.nutrition import recalculate_summary
from routers.users import _generate_and_save_insight
import asyncio

def seed_data_for_user(email: str):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        if not user:
            print(f"User with email {email} not found.")
            return

        print(f"Seeding data for user {user.username} ({user.email})...")

        today = date.today()
        
        # Get a random food item to use for logging
        food_items = session.exec(select(FoodItem).where(FoodItem.isActive == True).limit(5)).all()
        if not food_items:
            print("No food items found in the database. Please ingest food data first.")
            return
            
        print(f"Using {len(food_items)} food items for seeding.")

        stats = session.exec(select(UserStats).where(UserStats.user_id == user.id)).first()
        if not stats:
            stats = UserStats(user_id=user.id)
            session.add(stats)
            session.commit()
            session.refresh(stats)

        total_pushups_added = 0
        total_situps_added = 0
        last_active = None
        streak = 0

        for i in range(29, -1, -1):
            log_date = today - timedelta(days=i)
            print(f"Seeding date: {log_date}")

            # 1. Clean existing logs for this date
            existing_foods = session.exec(select(FoodLog).where(FoodLog.user_id == user.id, FoodLog.date == log_date)).all()
            for f in existing_foods:
                session.delete(f)
                
            existing_workouts = session.exec(select(WorkoutSession).where(WorkoutSession.user_id == user.id, WorkoutSession.date == log_date)).all()
            for w in existing_workouts:
                from models import ExerciseLog
                existing_elogs = session.exec(select(ExerciseLog).where(ExerciseLog.session_id == w.id)).all()
                for el in existing_elogs:
                    session.delete(el)
                session.delete(w)
                
            existing_dailies = session.exec(select(DailyLog).where(DailyLog.user_id == user.id, DailyLog.date == log_date)).all()
            for d in existing_dailies:
                session.delete(d)
                
            session.commit()

            # 2. Add Fake Food Logs (randomly 2 to 4 meals)
            daily_kcal = 0
            for meal in ["sarapan", "makan siang", "makan malam", "snack"]:
                if random.random() > 0.3: # 70% chance to log this meal
                    food = random.choice(food_items)
                    qty = random.uniform(1.0, 2.5)
                    
                    log = FoodLog(
                        user_id=user.id,
                        date=log_date,
                        meal_type=meal,
                        food_item_id=food.id,
                        quantity=qty,
                        calories_kcal=food.calories_per_serving * qty,
                        protein_g=food.protein_per_serving * qty,
                        carbs_g=food.carbs_per_serving * qty,
                        fat_g=food.fat_per_serving * qty,
                    )
                    session.add(log)
            session.commit()
            
            # Recalculate nutrition summary for this day
            recalculate_summary(session, user.id, log_date)

            # 3. Add Fake Workout Logs based on Plan
            active_plan = session.exec(
                select(ExercisePlan).where(ExercisePlan.user_id == user.id, ExercisePlan.is_active == True)
            ).first()
            
            is_planned_rest_day = False
            if active_plan:
                weekday = log_date.weekday() # 0 = Monday, 6 = Sunday
                plan_day = session.exec(
                    select(PlanDay).where(PlanDay.plan_id == active_plan.id, PlanDay.day_of_week == weekday)
                ).first()
                if plan_day and plan_day.is_rest_day:
                    is_planned_rest_day = True
            
            # If it's a planned rest day, we don't work out.
            # If it's not a rest day, we have a 90% chance of working out (to simulate following the plan mostly).
            if not is_planned_rest_day and random.random() > 0.1:
                # Workout Session
                duration = random.randint(900, 3600) # 15 to 60 minutes
                calories = random.uniform(150, 500)
                
                w_session = WorkoutSession(
                    user_id=user.id,
                    date=log_date,
                    duration_seconds=duration,
                    calories_burned=calories
                )
                session.add(w_session)
                session.flush() # To get w_session.id
                
                # Create Exercise Logs
                from models import Exercise, ExerciseLog
                all_exercises = session.exec(select(Exercise)).all()
                exercises_did = random.sample(all_exercises, random.randint(2, 4))
                
                for ex in exercises_did:
                    name = ex.name.lower()
                    reps = random.randint(10, 30) if 'plank' not in name else 0
                    dur = random.randint(30, 120)
                    
                    fake_mistakes = {}
                    if random.random() > 0.5: # 50% chance to have mistakes
                        if 'push' in name:
                            fake_mistakes["Punggung tidak lurus"] = random.randint(1, 3)
                        elif 'sit' in name:
                            fake_mistakes["Tidak naik penuh"] = random.randint(1, 3)
                        elif 'squat' in name:
                            fake_mistakes["Kedalaman squat kurang"] = random.randint(1, 3)
                        elif 'plank' in name:
                            fake_mistakes["Pinggul terlalu turun"] = random.randint(1, 3)
                    
                    e_log = ExerciseLog(
                        session_id=w_session.id,
                        exercise_id=ex.id,
                        set_number=random.randint(2, 4),
                        reps_completed=reps,
                        duration_seconds=dur,
                        is_manual_input=False,
                        form_mistakes=fake_mistakes
                    )
                    session.add(e_log)
                    
                    if 'push' in name:
                        total_pushups_added += (reps * e_log.set_number)
                    if 'sit' in name:
                        total_situps_added += (reps * e_log.set_number)
                
                # Daily Log
                d_log = DailyLog(
                    user_id=user.id,
                    date=log_date,
                    day_type=DayTypeEnum.workout_completed
                )
                session.add(d_log)
                
                last_active = log_date
                streak += 1
            else:
                # Missed a day or it's a rest day
                if not is_planned_rest_day:
                    streak = 0 # reset streak if missed
                    d_log = DailyLog(
                        user_id=user.id,
                        date=log_date,
                        day_type=DayTypeEnum.missed
                    )
                else:
                    d_log = DailyLog(
                        user_id=user.id,
                        date=log_date,
                        day_type=DayTypeEnum.rest_day
                    )
                session.add(d_log)
                
            session.commit()

        # 4. Update Stats
        if last_active:
            stats.lastActiveDate = last_active
        stats.currentStreak = streak
        if streak > stats.longestStreak:
            stats.longestStreak = streak
        session.commit()
        
        print("Data seeded successfully!")
        print("Generating AI Insight...")
        
        # 5. Run Insight Generation
        _generate_and_save_insight(user.id)
        
        # Reload stats to show insight
        session.refresh(stats)
        print("\n=== GENERATED INSIGHT ===")
        print(stats.latest_insight)
        print("=========================")
        
        print("\nSeed script finished successfully! You can now check the BerandaView in the app.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed dummy data for AI analysis testing.")
    parser.add_argument("email", help="The email of the user to seed data for")
    args = parser.parse_args()
    seed_data_for_user(args.email)
