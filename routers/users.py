from typing import List
import jwt
import random
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select
from models import User, UserStats, UserFitnessProfile, OTPVerification
from database import get_session
from schemas import UserCreate, UserUpdate, UserLogin, GoogleLoginRequest, OTPSendRequest, OTPVerifyRequest, PasswordResetRequest, ChangePasswordRequest
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

    otp_verified = session.exec(
        select(OTPVerification)
        .where(OTPVerification.email == user.email)
        .where(OTPVerification.purpose == "register")
        .where(OTPVerification.verifiedAt != None)
        .order_by(OTPVerification.verifiedAt.desc())
    ).first()

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if not otp_verified or otp_verified.verifiedAt.replace(tzinfo=None) < now_utc - timedelta(minutes=15):
        raise HTTPException(status_code=400, detail="Email is not verified via OTP")

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
async def google_login(data: GoogleLoginRequest, session: Session = Depends(get_session)):
    import httpx

    async def upload_google_photo(google_url: str) -> str | None:
        """Download Google profile photo and re-upload to Cloudinary."""
        from urllib.parse import urlparse
        parsed = urlparse(google_url)
        if not parsed.netloc.endswith("googleusercontent.com"):
            return google_url

        try:
            # Upgrade to higher resolution (s400 instead of s100)
            high_res_url = google_url.split("=s")[0] + "=s400-c"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(high_res_url, follow_redirects=True)
            if resp.status_code != 200:
                return google_url  # fallback to original if download fails
            import cloudinary.uploader
            result = cloudinary.uploader.upload(
                resp.content,
                folder="smafit/avatars",
                resource_type="image",
            )
            return result["secure_url"]
        except Exception as e:
            print(f"Failed to re-upload Google photo: {e}")
            return google_url  # fallback to original

    db_user = session.exec(select(User).where(User.email == data.email)).first()
    if not db_user:
        # New user — mirror photo to Cloudinary immediately
        cloudinary_url = None
        if data.photo_url:
            cloudinary_url = await upload_google_photo(data.photo_url)
        db_user = User(
            username=data.username,
            email=data.email,
            authProvider="google",
            googleId=data.google_id,
            photoUrl=cloudinary_url,
        )
        session.add(db_user)
        session.flush()
        session.add(UserStats(user_id=db_user.id))
        session.commit()
        session.refresh(db_user)
    else:
        needs_save = False
        if not db_user.googleId:
            db_user.googleId = data.google_id
            needs_save = True
        # Re-upload only if still pointing at Google's CDN (lh3.googleusercontent)
        if data.photo_url and (
            not db_user.photoUrl or "googleusercontent" in db_user.photoUrl
        ):
            db_user.photoUrl = await upload_google_photo(data.photo_url)
            needs_save = True
        if needs_save:
            db_user.updatedAt = datetime.now(timezone.utc)
            session.add(db_user)
            session.commit()
            session.refresh(db_user)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": db_user}


# ---------------------------------------------------------------------------
# OTP Routes
# ---------------------------------------------------------------------------

@router.post("/otp/send")
def send_otp(request: OTPSendRequest, session: Session = Depends(get_session)):
    if request.purpose == "reset_password":
        user = session.exec(select(User).where(User.email == request.email)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Email is not registered")
    elif request.purpose == "register":
        user = session.exec(select(User).where(User.email == request.email)).first()
        if user:
            raise HTTPException(status_code=400, detail="Email already registered")

    code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    otp_record = OTPVerification(
        email=request.email,
        code=code,
        purpose=request.purpose,
        expiresAt=expires_at
    )
    session.add(otp_record)
    session.commit()

    try:
        from mail_helper import send_otp_email
        send_otp_email(request.email, code, request.purpose)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "OTP sent successfully"}


@router.post("/otp/verify")
def verify_otp(request: OTPVerifyRequest, session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    otp_record = session.exec(
        select(OTPVerification)
        .where(OTPVerification.email == request.email)
        .where(OTPVerification.purpose == request.purpose)
        .where(OTPVerification.code == request.code)
        .where(OTPVerification.expiresAt > now)
        .where(OTPVerification.verifiedAt == None)
        .order_by(OTPVerification.createdAt.desc())
    ).first()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code")

    otp_record.verifiedAt = now
    session.add(otp_record)
    session.commit()
    return {"message": "OTP verified successfully"}


@router.post("/reset-password")
def reset_password(request: PasswordResetRequest, session: Session = Depends(get_session)):
    otp_verified = session.exec(
        select(OTPVerification)
        .where(OTPVerification.email == request.email)
        .where(OTPVerification.purpose == "reset_password")
        .where(OTPVerification.verifiedAt != None)
        .order_by(OTPVerification.verifiedAt.desc())
    ).first()

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if not otp_verified or otp_verified.verifiedAt.replace(tzinfo=None) < now_utc - timedelta(minutes=15):
        raise HTTPException(status_code=400, detail="OTP code has not been verified for password reset")

    user = session.exec(select(User).where(User.email == request.email)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password = get_password_hash(request.password)
    user.updatedAt = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return {"message": "Password reset successfully"}


@router.post("/change-password")
def change_password_logged_in(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not current_user.password or not verify_password(request.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Password lama salah")

    current_user.password = get_password_hash(request.new_password)
    current_user.updatedAt = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    return {"message": "Password berhasil diperbarui"}


@router.get("/me", response_model=User)
def read_user_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.get("/me/stats", response_model=UserStats)
def read_user_stats_me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    stats = session.exec(select(UserStats).where(UserStats.user_id == current_user.id)).first()
    if not stats:
        stats = UserStats(user_id=current_user.id)
        session.add(stats)
        session.commit()
        session.refresh(stats)
    return stats


@router.get("/me/fitness-profile", response_model=UserFitnessProfile)
def read_user_fitness_profile_me(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    profile = session.exec(select(UserFitnessProfile).where(UserFitnessProfile.user_id == current_user.id)).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Fitness profile not found")
    return profile


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
    if str(current_user.id) != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to access this user")

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
    if str(current_user.id) != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to update this user")

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    if "is_admin" in update_data and not current_user.is_admin:
        del update_data["is_admin"]

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
    if str(current_user.id) != str(user_id) and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to delete this user")

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db_user.deletedAt = datetime.now(timezone.utc)
    db_user.updatedAt = datetime.now(timezone.utc)
    session.add(db_user)
    session.commit()
    return {"message": "User deleted successfully"}
