from typing import List
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from prisma.models import User
from database import db
from schemas import UserCreate, UserUpdate, UserLogin, GoogleLoginRequest
import bcrypt
import os
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Please add it to your .env file before starting the server."
    )

ALGORITHM = "HS256"
# Set to 30 days (43200 mins) to prevent frequent logouts during prototype
ACCESS_TOKEN_EXPIRE_MINUTES = 43200 

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception
    user = await db.user.find_unique(where={"email": email})
    if user is None:
        raise credentials_exception
    return user

router = APIRouter(
    prefix="/api/users",
    tags=["users"]
)

@router.post("/", response_model=User)
async def create_user(user: UserCreate):
    try:
        hashed_password = get_password_hash(user.password)
        new_user = await db.user.create(
            data={
                "username": user.username,
                "email": user.email,
                "password": hashed_password,
            }
        )
        return new_user
    except Exception as e:
        raise HTTPException(status_code=400, detail="Email already exists or error occurred")

@router.post("/login")
async def login_user(user: UserLogin):
    db_user = await db.user.find_unique(where={"email": user.email})
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": db_user}

@router.post("/google-login")
async def google_login(data: GoogleLoginRequest):
    # Check if user already exists
    db_user = await db.user.find_unique(where={"email": data.email})
    if not db_user:
        # Create brand new google user
        db_user = await db.user.create(
            data={
                "username": data.username,
                "email": data.email,
                "authProvider": "google",
                "googleId": data.google_id
            }
        )
    else:
        # User exists via local or previous google connection, link their account just in case
        if not db_user.googleId:
            db_user = await db.user.update(
                where={"email": data.email},
                data={"googleId": data.google_id}
            )
            
    # Issue the same token as local login!
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": db_user}

@router.get("/", response_model=List[User])
async def read_users(current_user: User = Depends(get_current_user)):
    return await db.user.find_many()

@router.get("/{user_id}", response_model=User)
async def read_user(user_id: int, current_user: User = Depends(get_current_user)):
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/{user_id}", response_model=User)
async def update_user(user_id: int, user_update: UserUpdate, current_user: User = Depends(get_current_user)):
    update_data = user_update.model_dump(exclude_unset=True)
    if not update_data:
        user = await db.user.find_unique(where={"id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    
    try:
        user = await db.user.update(
            where={"id": user_id},
            data=update_data
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except Exception:
        raise HTTPException(status_code=404, detail="User not found or error occurred")

@router.delete("/{user_id}")
async def delete_user(user_id: int, current_user: User = Depends(get_current_user)):
    try:
        await db.user.delete(where={"id": user_id})
        return {"message": "User deleted successfully"}
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")
