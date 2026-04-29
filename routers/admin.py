from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from pydantic import BaseModel
import jwt
from datetime import timedelta, timezone
from collections import defaultdict
from routers.users import verify_password, create_access_token, SECRET_KEY, ALGORITHM
from database import get_session
from models import User, UserStats, WorkoutSession, ChatSession

class AdminLoginRequest(BaseModel):
    email: str
    password: str

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

class ExceptionRequiresRedirect(Exception):
    pass

async def redirect_handler(request: Request, exc: ExceptionRequiresRedirect):
    return RedirectResponse(url="/admin/login", status_code=303)

def get_admin_user(request: Request, session: Session = Depends(get_session)):
    """For Jinja2 template routes — reads admin_session cookie."""
    token = request.cookies.get("admin_session")
    if not token:
        raise ExceptionRequiresRedirect()
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise ExceptionRequiresRedirect()
        user = session.exec(select(User).where(User.email == email)).first()
        if not user or not user.is_admin:
            raise ExceptionRequiresRedirect()
        return user
    except jwt.InvalidTokenError:
        raise ExceptionRequiresRedirect()

def get_admin_user_api(request: Request, session: Session = Depends(get_session)):
    """For JSON API routes — reads Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = session.exec(select(User).where(User.email == email)).first()
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access only")
        return user
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ── Jinja2 template routes ─────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin/login.html")

@router.post("/login", response_class=HTMLResponse)
def login_submit(
    response: Response,
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not user.password or not verify_password(password, user.password):
        return templates.TemplateResponse(request=request, name="admin/login.html", context={"error": "Invalid email or password"})

    if not user.is_admin:
        return templates.TemplateResponse(request=request, name="admin/login.html", context={"error": "Unauthorized. Admin access only."})

    access_token = create_access_token(data={"sub": user.email}, expires_delta=timedelta(days=1))

    redirect = RedirectResponse(url="/admin/dashboard", status_code=302)
    redirect.set_cookie(
        key="admin_session",
        value=access_token,
        httponly=True,
        secure=False,
        max_age=86400,
        samesite="lax"
    )
    return redirect

@router.get("/logout")
def logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("admin_session")
    return response

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, admin: User = Depends(get_admin_user), session: Session = Depends(get_session)):
    users_count = len(session.exec(select(User)).all())
    return templates.TemplateResponse(request=request, name="admin/dashboard.html", context={
        "admin": admin,
        "users_count": users_count
    })

# ── JSON API endpoints for the Next.js admin panel ────────────────────────────

@router.post("/api/login")
def admin_api_login(
    body: AdminLoginRequest,
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.email == body.email)).first()
    if not user or not user.password or not verify_password(body.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access only")
    access_token = create_access_token(data={"sub": user.email}, expires_delta=timedelta(days=1))
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "username": user.username}
    }

@router.get("/api/me")
def admin_api_me(admin: User = Depends(get_admin_user_api)):
    return {"id": admin.id, "email": admin.email, "username": admin.username}

@router.get("/api/stats")
def admin_api_stats(
    admin: User = Depends(get_admin_user_api),
    session: Session = Depends(get_session)
):
    all_users = session.exec(select(User)).all()
    total_users = len(all_users)
    active_users = sum(1 for u in all_users if u.deletedAt is None)
    total_workouts = len(session.exec(select(WorkoutSession)).all())
    total_chats = len(session.exec(select(ChatSession)).all())
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_workouts": total_workouts,
        "total_chats": total_chats,
    }

@router.get("/api/users")
def admin_api_users(
    admin: User = Depends(get_admin_user_api),
    session: Session = Depends(get_session)
):
    users = session.exec(select(User)).all()
    result = []
    for user in users:
        stats = session.exec(select(UserStats).where(UserStats.user_id == user.id)).first()
        result.append({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_admin": user.is_admin,
            "authProvider": user.authProvider,
            "deletedAt": user.deletedAt.isoformat() if user.deletedAt else None,
            "createdAt": user.createdAt.isoformat(),
            "totalPushUps": stats.totalPushUps if stats else 0,
            "totalSitUps": stats.totalSitUps if stats else 0,
            "currentStreak": stats.currentStreak if stats else 0,
            "longestStreak": stats.longestStreak if stats else 0,
        })
    return result

@router.get("/api/chart/registrations")
def admin_api_chart_registrations(
    admin: User = Depends(get_admin_user_api),
    session: Session = Depends(get_session)
):
    users = session.exec(select(User)).all()
    counts: dict[str, int] = defaultdict(int)
    for user in users:
        date_str = user.createdAt.strftime("%Y-%m-%d")
        counts[date_str] += 1
    return [{"date": k, "users": v} for k, v in sorted(counts.items())]
