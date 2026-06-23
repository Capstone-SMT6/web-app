import sys
from sqlmodel import Session, select
from database import engine
from models import ExercisePlan, UserFitnessProfile, PlanDay, PlanDayExercise
from services.plan_generator import generate_plan

def main():
    with Session(engine) as session:
        # Get all users with active plans
        active_plans = session.exec(select(ExercisePlan).where(ExercisePlan.is_active == True)).all()
        for plan in active_plans:
            profile = session.get(UserFitnessProfile, plan.fitness_profile_id)
            if not profile:
                continue
            
            # Find the selected training days of the user's active plan
            days = session.exec(select(PlanDay).where(PlanDay.plan_id == plan.id)).all()
            # Map index to day names
            day_map = {0: 'senin', 1: 'selasa', 2: 'rabu', 3: 'kamis', 4: 'jumat', 5: 'sabtu', 6: 'minggu'}
            selected_days = [day_map[d.day_of_week] for d in days if not d.is_rest_day]
            
            print(f"User {profile.user_id}: regenerating plan for days {selected_days}...")
            
            # generate_plan will deactivate the old plan and create a new one
            generate_plan(profile, session, selected_days, applied_constraints=plan.applied_constraints)
        
        session.commit()
        print("Plans regenerated successfully!")

if __name__ == '__main__':
    main()
