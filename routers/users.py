from typing import List
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from models import User, UserStats
from database import get_session
from schemas import UserCreate, UserUpdate, UserLogin, GoogleLoginRequest
import bcrypt
import os
from dotenv import load_dotenv
from cloudinary_storage import upload_image_to_cloudinary

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. "
        "Please add it to your .env file before starting the server."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 43200

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/login")


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)):
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
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        raise credentials_exception
    return user


router = APIRouter(
    prefix="/api/users",
    tags=["users"],
)


@router.post("/", response_model=User)
def create_user(user: UserCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == user.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")
    hashed_password = get_password_hash(user.password)
    new_user = User(
        username=user.username,
        email=user.email,
        password=hashed_password,
    )
    session.add(new_user)
    session.flush()
    session.add(UserStats(user_id=new_user.id))
    session.commit()
    session.refresh(new_user)
    return new_user


@router.post("/login")
def login_user(user: UserLogin, session: Session = Depends(get_session)):
    db_user = session.exec(select(User).where(User.email == user.email)).first()
    if not db_user or not db_user.password or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": db_user}


@router.post("/google-login")
def google_login(data: GoogleLoginRequest, session: Session = Depends(get_session)):
    db_user = session.exec(select(User).where(User.email == data.email)).first()
    if not db_user:
        db_user = User(
            username=data.username,
            email=data.email,
            authProvider="google",
            googleId=data.google_id,
            photoUrl=data.photo_url
        )
        session.add(db_user)
        session.flush()
        session.add(UserStats(user_id=db_user.id))
        session.commit()
        session.refresh(db_user)
    else:
        if not db_user.googleId or not db_user.photoUrl:
            db_user.googleId = data.google_id
            if data.photo_url and not db_user.photoUrl:
                db_user.photoUrl = data.photo_url
            db_user.updatedAt = datetime.now(timezone.utc)
            session.add(db_user)
            session.commit()
            session.refresh(db_user)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": db_user}


@router.get("/", response_model=List[User])
def read_users(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    return session.exec(select(User)).all()


@router.get("/{user_id}", response_model=User)
def read_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=User)
def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["password"] = get_password_hash(update_data["password"])

    for key, value in update_data.items():
        setattr(db_user, key, value)

    db_user.updatedAt = datetime.now(timezone.utc)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


@router.post("/{user_id}/avatar", response_model=User)
async def upload_avatar(
    user_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to update this user's avatar")
        
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    public_url = await upload_image_to_cloudinary(file, folder="smafit/avatars")
    
    db_user.photoUrl = public_url
    db_user.updatedAt = datetime.now(timezone.utc)
    
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    
    return db_user


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db_user.deletedAt = datetime.now(timezone.utc)
    db_user.updatedAt = datetime.now(timezone.utc)
    session.add(db_user)
    session.commit()
    return {"message": "User deleted successfully"}
