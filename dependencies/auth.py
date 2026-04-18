from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from utils.security import SECRET_KEY, ALGORITHM
from database import get_database
from models.user import UserOut
from bson import ObjectId

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

async def get_current_user_logic(token: str):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    db = get_database()
    user = await db["users"].find_one({"email": email})
    if user is None:
        raise credentials_exception
        
    return UserOut(
        id=str(user["_id"]),
        email=user["email"],
        role=user["role"],
        full_name=user.get("full_name")
    )

async def get_current_user(token: str = Depends(oauth2_scheme)):
    return await get_current_user_logic(token)

async def get_current_user_optional(token: str = Depends(oauth2_scheme_optional)):
    if not token:
        return None
    try:
        return await get_current_user_logic(token)
    except HTTPException:
        return None

def require_role(allowed_roles: list[str]):
    async def role_checker(current_user: UserOut = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker
