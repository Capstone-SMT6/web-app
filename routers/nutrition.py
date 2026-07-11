from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from datetime import datetime, date, timezone, timedelta
from typing import List, Optional

from database import get_session
from models import User, UserFitnessProfile, FoodItem, FoodLog, NutritionSummary, GoalEnum
from schemas import FoodLogCreate
from routers.users import get_current_user

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


# Helpers

def recalculate_summary(session: Session, user_id: str, log_date: date):
    # Query all logs for user and date
    logs = session.exec(
        select(FoodLog).where(FoodLog.user_id == user_id, FoodLog.date == log_date)
    ).all()
    
    summary = session.exec(
        select(NutritionSummary).where(NutritionSummary.user_id == user_id, NutritionSummary.date == log_date)
    ).first()
    
    if not logs:
        if summary:
            session.delete(summary)
            session.commit()
        return
        
    total_kcal = sum(log.calories_kcal for log in logs)
    total_protein = sum(log.protein_g for log in logs)
    total_carbs = sum(log.carbs_g for log in logs)
    total_fat = sum(log.fat_g for log in logs)
    entry_count = len(logs)
    
    if not summary:
        summary = NutritionSummary(
            user_id=user_id,
            date=log_date,
            total_kcal=total_kcal,
            total_protein_g=total_protein,
            total_carbs_g=total_carbs,
            total_fat_g=total_fat,
            entry_count=entry_count
        )
    else:
        summary.total_kcal = total_kcal
        summary.total_protein_g = total_protein
        summary.total_carbs_g = total_carbs
        summary.total_fat_g = total_fat
        summary.entry_count = entry_count
        summary.updatedAt = datetime.now(timezone.utc)
        
    session.add(summary)
    session.commit()


# Public Endpoints

@router.get("/foods", response_model=List[FoodItem])
def get_foods(
    q: Optional[str] = None,
    category: Optional[str] = None,
    session: Session = Depends(get_session)
):
    query = select(FoodItem).where(FoodItem.isActive == True)  # noqa: E712
    if q:
        query = query.where(FoodItem.name.ilike(f"%{q}%"))
    if category:
        query = query.where(FoodItem.category == category)
        
    return session.exec(query).all()


@router.get("/foods/{food_id}", response_model=FoodItem)
def get_food_item(
    food_id: str,
    session: Session = Depends(get_session)
):
    food = session.get(FoodItem, food_id)
    if not food or not food.isActive:
        raise HTTPException(status_code=404, detail="Food item not found")
    return food


# User Logging Endpoints

from fastapi import BackgroundTasks
from routers.users import _generate_and_save_insight

@router.post("/log")
def create_log_entry(
    payload: FoodLogCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    food_item = session.get(FoodItem, payload.food_item_id)
    if not food_item or not food_item.isActive:
        raise HTTPException(status_code=404, detail="Food item not found or inactive")
        
    log_date = payload.date if payload.date else date.today()
    
    # Calculate computed macros
    calories = payload.quantity * food_item.calories_per_serving
    protein = payload.quantity * food_item.protein_per_serving
    carbs = payload.quantity * food_item.carbs_per_serving
    fat = payload.quantity * food_item.fat_per_serving
    
    log = FoodLog(
        user_id=current_user.id,
        date=log_date,
        meal_type=payload.meal_type,
        food_item_id=food_item.id,
        quantity=payload.quantity,
        calories_kcal=calories,
        protein_g=protein,
        carbs_g=carbs,
        fat_g=fat,
        notes=payload.notes
    )
    
    session.add(log)
    session.commit()
    session.refresh(log)
    
    # Recalculate summary
    recalculate_summary(session, current_user.id, log_date)
    
    # Trigger insight generation
    background_tasks.add_task(_generate_and_save_insight, current_user.id)
    
    return {
        "id": log.id,
        "date": log.date.isoformat(),
        "meal_type": log.meal_type,
        "quantity": log.quantity,
        "calories_kcal": log.calories_kcal,
        "protein_g": log.protein_g,
        "carbs_g": log.carbs_g,
        "fat_g": log.fat_g,
        "notes": log.notes,
        "createdAt": log.createdAt.isoformat(),
        "food_item": {
            "id": food_item.id,
            "name": food_item.name,
            "category": food_item.category,
            "calories_per_serving": food_item.calories_per_serving,
            "protein_per_serving": food_item.protein_per_serving,
            "carbs_per_serving": food_item.carbs_per_serving,
            "fat_per_serving": food_item.fat_per_serving,
            "serving_unit": food_item.serving_unit,
            "serving_size_g": food_item.serving_size_g,
            "imageUrl": food_item.imageUrl
        }
    }


@router.get("/log/{date_val}")
def get_logs_for_date(
    date_val: date,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    query = (
        select(FoodLog, FoodItem)
        .join(FoodItem, FoodLog.food_item_id == FoodItem.id)
        .where(FoodLog.user_id == current_user.id, FoodLog.date == date_val)
        .order_by(FoodLog.createdAt.desc())
    )
    results = session.exec(query).all()
    
    response = []
    for log, item in results:
        response.append({
            "id": log.id,
            "date": log.date.isoformat(),
            "meal_type": log.meal_type,
            "quantity": log.quantity,
            "calories_kcal": log.calories_kcal,
            "protein_g": log.protein_g,
            "carbs_g": log.carbs_g,
            "fat_g": log.fat_g,
            "notes": log.notes,
            "createdAt": log.createdAt.isoformat(),
            "food_item": {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "calories_per_serving": item.calories_per_serving,
                "protein_per_serving": item.protein_per_serving,
                "carbs_per_serving": item.carbs_per_serving,
                "fat_per_serving": item.fat_per_serving,
                "serving_unit": item.serving_unit,
                "serving_size_g": item.serving_size_g,
                "imageUrl": item.imageUrl
            }
        })
    return response


@router.get("/log/today")
def get_today_logs(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    return get_logs_for_date(date_val=date.today(), current_user=current_user, session=session)


@router.delete("/log/{entry_id}")
def delete_log_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    log = session.get(FoodLog, entry_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
        
    if log.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this log entry")
        
    log_date = log.date
    session.delete(log)
    session.commit()
    
    # Recalculate summary
    recalculate_summary(session, current_user.id, log_date)
    
    return {"message": "Log entry deleted successfully"}


# Summary Endpoints

@router.get("/summary/day/{date_val}")
def get_day_summary(
    date_val: date,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    profile = session.exec(
        select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)
    ).first()
    
    summary = session.exec(
        select(NutritionSummary).where(NutritionSummary.user_id == current_user.id, NutritionSummary.date == date_val)
    ).first()
    
    target_kcal = profile.target_daily_kcal if profile else 2000.0
    target_protein = profile.macros_json.get("protein_g", 130.0) if (profile and profile.macros_json) else 130.0
    target_carbs = profile.macros_json.get("carbs_g", 220.0) if (profile and profile.macros_json) else 220.0
    target_fat = profile.macros_json.get("fat_g", 65.0) if (profile and profile.macros_json) else 65.0
    
    actual_kcal = summary.total_kcal if summary else 0.0
    actual_protein = summary.total_protein_g if summary else 0.0
    actual_carbs = summary.total_carbs_g if summary else 0.0
    actual_fat = summary.total_fat_g if summary else 0.0
    
    return {
        "date": date_val,
        "actual": {
            "calories": actual_kcal,
            "protein": actual_protein,
            "carbs": actual_carbs,
            "fat": actual_fat
        },
        "target": {
            "calories": target_kcal,
            "protein": target_protein,
            "carbs": target_carbs,
            "fat": target_fat
        }
    }


@router.get("/summary/week")
def get_week_summary(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    today_val = date.today()
    start_date = today_val - timedelta(days=6)
    
    profile = session.exec(
        select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)
    ).first()
    
    target_kcal = profile.target_daily_kcal if profile else 2000.0
    
    # Query summaries
    summaries = session.exec(
        select(NutritionSummary)
        .where(NutritionSummary.user_id == current_user.id)
        .where(NutritionSummary.date >= start_date)
        .where(NutritionSummary.date <= today_val)
    ).all()
    
    summary_map = {s.date: s for s in summaries}
    
    result = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        summary = summary_map.get(day)
        
        result.append({
            "date": day.isoformat(),
            "calories": summary.total_kcal if summary else 0.0,
            "protein": summary.total_protein_g if summary else 0.0,
            "carbs": summary.total_carbs_g if summary else 0.0,
            "fat": summary.total_fat_g if summary else 0.0,
            "target_calories": target_kcal
        })
        
    return result


@router.get("/summary/month")
def get_month_summary(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    today_val = date.today()
    start_date = today_val - timedelta(days=29)
    
    profile = session.exec(
        select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)
    ).first()
    
    target_kcal = profile.target_daily_kcal if profile else 2000.0
    
    summaries = session.exec(
        select(NutritionSummary)
        .where(NutritionSummary.user_id == current_user.id)
        .where(NutritionSummary.date >= start_date)
        .where(NutritionSummary.date <= today_val)
    ).all()
    
    summary_map = {s.date: s for s in summaries}
    
    result = []
    for i in range(30):
        day = start_date + timedelta(days=i)
        summary = summary_map.get(day)
        
        result.append({
            "date": day.isoformat(),
            "calories": summary.total_kcal if summary else 0.0,
            "protein": summary.total_protein_g if summary else 0.0,
            "carbs": summary.total_carbs_g if summary else 0.0,
            "fat": summary.total_fat_g if summary else 0.0,
            "target_calories": target_kcal
        })
        
    return result


# Feedback Endpoints

@router.get("/feedback/day/{date_val}")
def get_day_feedback(
    date_val: date,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    profile = session.exec(
        select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)
    ).first()
    
    summary = session.exec(
        select(NutritionSummary).where(NutritionSummary.user_id == current_user.id, NutritionSummary.date == date_val)
    ).first()
    
    target_kcal = profile.target_daily_kcal if profile else 2000.0
    target_protein = profile.macros_json.get("protein_g", 130.0) if (profile and profile.macros_json) else 130.0
    target_carbs = profile.macros_json.get("carbs_g", 220.0) if (profile and profile.macros_json) else 220.0
    target_fat = profile.macros_json.get("fat_g", 65.0) if (profile and profile.macros_json) else 65.0
    
    actual_kcal = summary.total_kcal if summary else 0.0
    actual_protein = summary.total_protein_g if summary else 0.0
    actual_carbs = summary.total_carbs_g if summary else 0.0
    actual_fat = summary.total_fat_g if summary else 0.0
    
    # Kcal Status
    kcal_gap = actual_kcal - target_kcal
    if kcal_gap < -100:
        kcal_status = "deficit"
    elif kcal_gap > 100:
        kcal_status = "surplus"
    else:
        kcal_status = "on_target"
        
    def get_macro_status(actual, target):
        if actual < target * 0.85:
            return "low"
        elif actual > target * 1.15:
            return "high"
        return "on_target"
        
    protein_status = get_macro_status(actual_protein, target_protein)
    carbs_status = get_macro_status(actual_carbs, target_carbs)
    fat_status = get_macro_status(actual_fat, target_fat)
    
    recommendations = []
    
    if kcal_status == "deficit":
        recommendations.append(f"Kalori kamu masih kurang {abs(round(kcal_gap))} kcal dari target hari ini.")
        if profile and profile.goal in [GoalEnum.menaikkan_berat_badan, GoalEnum.membentuk_otot, GoalEnum.menaikkan_berat_badan.value, GoalEnum.membentuk_otot.value]:
            recommendations.append("Untuk menambah berat badan/otot, pastikan target kalori harian terpenuhi.")
    elif kcal_status == "surplus":
        recommendations.append(f"Kalori kamu surplus {round(kcal_gap)} kcal dari target hari ini.")
        if profile and profile.goal in [GoalEnum.menurunkan_berat_badan, GoalEnum.menurunkan_berat_badan.value]:
            recommendations.append("Untuk menurunkan berat badan, cobalah membatasi makanan tinggi kalori.")
    else:
        recommendations.append("Bagus! Asupan kalori kamu sudah sesuai dengan target hari ini.")
        
    if protein_status == "low":
        recommendations.append("Tingkatkan asupan protein — coba tambah dada ayam, telur, tempe, atau tahu.")
    elif protein_status == "high":
        recommendations.append("Asupan protein kamu sudah tinggi. Pastikan minum air putih yang cukup.")
        
    if carbs_status == "low":
        recommendations.append("Karbohidrat masih kurang — tambahkan nasi, roti gandum, atau ubi jalar.")
    elif carbs_status == "high":
        recommendations.append("Asupan karbohidrat berlebih — coba kurangi camilan manis atau makanan olahan tepung.")
        
    if fat_status == "low":
        recommendations.append("Lemak sehat kurang — coba tambahkan alpukat, kacang-kacangan, atau minyak zaitun.")
    elif fat_status == "high":
        recommendations.append("Asupan lemak melebihi target — batasi konsumsi gorengan atau masakan bersantan.")
        
    return {
        "kcal_status": kcal_status,
        "kcal_gap": round(kcal_gap),
        "macros": {
            "protein": { "status": protein_status, "actual": round(actual_protein, 1), "target": round(target_protein, 1) },
            "carbs": { "status": carbs_status, "actual": round(actual_carbs, 1), "target": round(target_carbs, 1) },
            "fat": { "status": fat_status, "actual": round(actual_fat, 1), "target": round(target_fat, 1) }
        },
        "recommendations": recommendations
    }
