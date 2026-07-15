from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from routers import users, chatbot, admin, trends, nutrition, workouts

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' https://cdn.jsdelivr.net; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://cdn.jsdelivr.net;"
    )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from limiter import limiter
from fastapi.responses import JSONResponse
import time

async def custom_rate_limit_handler(request: Request, exc: Exception):
    current_limit = getattr(request.state, "view_rate_limit", None)
    detail = getattr(exc, "detail", "Too many requests")
    
    response = JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later.", "error": detail}
    )
    
    if current_limit and hasattr(request.app.state, "limiter"):
        limiter_obj = request.app.state.limiter
        try:
            window_stats = limiter_obj.limiter.get_window_stats(current_limit[0], *current_limit[1])
            reset_in = 1 + window_stats[0]
            retry_after_secs = max(1, int(reset_in - time.time()))
            response.headers["Retry-After"] = str(retry_after_secs)
            response.headers["X-RateLimit-Limit"] = str(current_limit[0].amount)
            response.headers["X-RateLimit-Remaining"] = "0"
            response.headers["X-RateLimit-Reset"] = str(int(reset_in))
        except Exception as e:
            response.headers["Retry-After"] = "60"
    else:
        response.headers["Retry-After"] = "60"
        
    return response

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_exception_handler(admin.ExceptionRequiresRedirect, admin.redirect_handler)

import os

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5000,http://127.0.0.1:5000,http://localhost:5001,http://127.0.0.1:5001,http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(users.router)
app.include_router(chatbot.router)
app.include_router(admin.router)
app.include_router(trends.router)
app.include_router(nutrition.router)
app.include_router(workouts.router)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.get("/health")
async def health_check():
    try:
        from database import engine
        from sqlmodel import text
        import cloudinary_storage  # This runs the configuration
        import cloudinary.api
        
        status_dict = {"status": "healthy"}
        
        # Test Database
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status_dict["database"] = "connected"
        
        # Test Cloudinary
        cloudinary_response = cloudinary.api.ping()
        if "status" in cloudinary_response and cloudinary_response["status"] == "ok":
            status_dict["cloudinary"] = "connected"
        else:
            status_dict["cloudinary"] = "failed"
            
        return status_dict
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service connection error: {str(e)}")


@app.get("/items/{item_id}")
async def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}