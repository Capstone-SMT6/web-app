from fastapi import APIRouter, Request, Depends, HTTPException, status, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
import jwt
from datetime import timedelta
from routers.users import verify_password, create_access_token, SECRET_KEY, ALGORITHM
from database import get_session
from models import User

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

class ExceptionRequiresRedirect(Exception):
    pass

async def redirect_handler(request: Request, exc: ExceptionRequiresRedirect):
    return RedirectResponse(url="/admin/login", status_code=303)

def get_admin_user(request: Request, session: Session = Depends(get_session)):
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
