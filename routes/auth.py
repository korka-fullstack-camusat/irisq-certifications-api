from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta, datetime
from database import get_database
from models.user import UserCreate, UserInDB, Token, UserOut
from utils.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from dependencies.auth import get_current_user
from bson import ObjectId
from pydantic import BaseModel, EmailStr
import secrets
from email_service import notify_admin_password_reset

router = APIRouter()

@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    db = get_database()
    # Normalize email to lowercase
    email = form_data.username.lower().strip()
    user = await db["users"].find_one({"email": email})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"], "role": user["role"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", response_model=UserOut)
async def register(user: UserCreate):
    db = get_database()
    email = user.email.lower().strip()
    
    # Check if user already exists
    if await db["users"].find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed_password = get_password_hash(user.password)
    user_dict = user.model_dump()
    user_dict["email"] = email
    user_dict.pop("password")
    
    new_user = UserInDB(
        **user_dict,
        hashed_password=hashed_password,
        created_at=datetime.utcnow()
    )
    
    result = await db["users"].insert_one(new_user.model_dump())
    
    return UserOut(
        id=str(result.inserted_id),
        email=new_user.email,
        role=new_user.role,
        full_name=new_user.full_name
    )

@router.get("/me", response_model=UserOut)
async def read_users_me(current_user: UserOut = Depends(get_current_user)):
    return current_user


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
):
    db = get_database()
    email = payload.email.lower().strip()
    user = await db["users"].find_one({"email": email})

    # Always return success to avoid email enumeration
    if not user:
        return {"message": "Si cet email est enregistré, un mot de passe provisoire vient d'être envoyé."}

    new_password = secrets.token_urlsafe(10)[:12]
    hashed = get_password_hash(new_password)
    await db["users"].update_one(
        {"_id": user["_id"]},
        {"$set": {"hashed_password": hashed}}
    )

    background_tasks.add_task(
        notify_admin_password_reset,
        email, user.get("full_name") or email, new_password,
    )

    return {"message": "Si cet email est enregistré, un mot de passe provisoire vient d'être envoyé."}
