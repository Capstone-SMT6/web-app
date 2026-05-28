from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from routers import users, chatbot, admin, trends

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)
app.add_exception_handler(admin.ExceptionRequiresRedirect, admin.redirect_handler)

import os

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5000,http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(users.router)
app.include_router(chatbot.router)
app.include_router(admin.router)
app.include_router(trends.router)


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