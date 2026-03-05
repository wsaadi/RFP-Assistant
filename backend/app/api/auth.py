"""Authentication API routes with brute-force protection."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..security import hash_password, verify_password, create_access_token
from ..models.user import User
from ..schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from ..schemas.user import ChangePasswordRequest
from .deps import get_current_user
from ..config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger("security.auth")

# ── In-memory brute-force protection ──
_login_attempts: dict[str, dict] = {}
_MAX_ATTEMPTS = settings.login_lockout_attempts
_LOCKOUT_MINUTES = settings.login_lockout_minutes


def _check_lockout(key: str) -> None:
    """Raise 429 if the key is currently locked out."""
    record = _login_attempts.get(key)
    if not record or not record.get("locked_until"):
        return
    now = datetime.now(timezone.utc)
    if now < record["locked_until"]:
        remaining = int((record["locked_until"] - now).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Trop de tentatives. Réessayez dans {remaining} secondes.",
            headers={"Retry-After": str(remaining)},
        )
    del _login_attempts[key]


def _record_failure(key: str) -> None:
    now = datetime.now(timezone.utc)
    record = _login_attempts.get(key)
    if not record:
        _login_attempts[key] = {"count": 1, "locked_until": None, "first_attempt": now}
        return
    record["count"] += 1
    if record["count"] >= _MAX_ATTEMPTS:
        record["locked_until"] = now + timedelta(minutes=_LOCKOUT_MINUTES)
        logger.warning("Account lockout triggered for %s after %d attempts", key, record["count"])


def _clear_attempts(*keys: str) -> None:
    for k in keys:
        _login_attempts.pop(k, None)


def _cleanup_stale_records() -> None:
    now = datetime.now(timezone.utc)
    stale = [
        k for k, v in _login_attempts.items()
        if (v.get("locked_until") and now > v["locked_until"])
        or (now - v.get("first_attempt", now)) > timedelta(hours=1)
    ]
    for k in stale:
        del _login_attempts[k]


def validate_password_strength(password: str) -> None:
    """Validate password meets minimum security requirements."""
    errors = []
    if len(password) < settings.min_password_length:
        errors.append(f"au moins {settings.min_password_length} caractères")
    if not any(c.isupper() for c in password):
        errors.append("au moins une majuscule")
    if not any(c.islower() for c in password):
        errors.append("au moins une minuscule")
    if not any(c.isdigit() for c in password):
        errors.append("au moins un chiffre")
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mot de passe trop faible. Requis : {', '.join(errors)}",
        )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, req: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT token (set as httpOnly cookie)."""
    client_ip = req.client.host if req.client else "unknown"
    ip_key = f"ip:{client_ip}"
    email_key = f"email:{request.email.lower().strip()}"

    # Periodic cleanup
    if len(_login_attempts) > 1000:
        _cleanup_stale_records()

    # Check lockout for both IP and email
    _check_lockout(ip_key)
    _check_lockout(email_key)

    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        _record_failure(ip_key)
        _record_failure(email_key)
        logger.warning("Failed login attempt for email=%s from ip=%s", request.email, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )

    if not user.is_active:
        logger.warning("Login attempt on disabled account email=%s ip=%s", request.email, client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé",
        )

    # Success — clear attempts
    _clear_attempts(ip_key, email_key)
    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    logger.info("Successful login user=%s (id=%s) ip=%s", user.username, user.id, client_ip)

    # Set JWT as httpOnly secure cookie (not accessible via JavaScript)
    response.set_cookie(
        key="rfp_access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax" if not settings.cookie_secure else "strict",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        role=user.role.value,
        username=user.username,
    )


@router.post("/logout")
async def logout(response: Response):
    """Clear the authentication cookie."""
    response.delete_cookie(
        key="rfp_access_token",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax" if not settings.cookie_secure else "strict",
        path="/",
    )
    return {"message": "Déconnexion réussie"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "is_active": current_user.is_active,
    }


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect",
        )
    validate_password_strength(request.new_password)
    current_user.hashed_password = hash_password(request.new_password)
    await db.commit()
    logger.info("Password changed for user=%s (id=%s)", current_user.username, current_user.id)
    return {"message": "Mot de passe modifié avec succès"}
