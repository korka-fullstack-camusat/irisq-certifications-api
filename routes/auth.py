from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Body
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta, datetime
from database import get_database
from models.user import UserCreate, UserInDB, Token, UserOut
from utils.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from dependencies.auth import get_current_user, require_role
from bson import ObjectId
from pydantic import BaseModel, EmailStr
import secrets
import httpx
from email_service import notify_admin_password_reset, BREVO_API_KEY, BREVO_API_URL, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME

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

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce compte a été désactivé. Contactez l'évaluateur.",
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


# ── Endpoint de diagnostic email (admin uniquement) ───────────────────────────

class TestEmailPayload(BaseModel):
    to_email: str

@router.post("/admin/test-email", tags=["Admin"])
async def send_test_email(
    payload: TestEmailPayload,
    current_user: UserOut = Depends(require_role(["RH", "EVALUATEUR"])),
):
    """
    Envoie un email de test via Brevo pour vérifier la configuration.
    Retourne le statut détaillé de l'envoi.
    """
    if not BREVO_API_KEY:
        raise HTTPException(status_code=500, detail="BREVO_API_KEY n'est pas configuré sur ce serveur.")
    if not BREVO_SENDER_EMAIL:
        raise HTTPException(status_code=500, detail="BREVO_SENDER_EMAIL n'est pas configuré sur ce serveur.")

    test_body = {
        "sender": {"name": BREVO_SENDER_NAME or "IRISQ Certification", "email": BREVO_SENDER_EMAIL},
        "to": [{"email": payload.to_email}],
        "subject": "[TEST] Vérification email IRISQ",
        "htmlContent": f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:32px;background:#f4f6f9;border-radius:12px;">
            <h2 style="color:#1a237e;">Test de configuration email</h2>
            <p style="color:#475569;">Cet email confirme que la configuration Brevo d'IRISQ fonctionne correctement.</p>
            <p style="color:#64748b;font-size:13px;">Expéditeur : <strong>{BREVO_SENDER_EMAIL}</strong></p>
            <p style="color:#64748b;font-size:13px;">Destinataire : <strong>{payload.to_email}</strong></p>
        </div>
        """,
    }
    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        resp = httpx.post(BREVO_API_URL, json=test_body, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            return {
                "success": True,
                "message": f"Email de test envoyé avec succès à {payload.to_email}",
                "sender": BREVO_SENDER_EMAIL,
                "brevo_status": resp.status_code,
            }
        else:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "Brevo a refusé l'envoi",
                    "brevo_status": resp.status_code,
                    "brevo_response": resp.text,
                    "sender": BREVO_SENDER_EMAIL,
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Timeout lors de la connexion à l'API Brevo.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur inattendue : {exc}")
