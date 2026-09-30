"""Auth endpoints (CONTRACT.md §5: Auth)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, verify_password
from app.models.models import User
from app.schemas.schemas import CaptchaOut, LoginRequest, TokenResponse, UserOut
from app.services import audit_service, captcha_service

router = APIRouter(prefix="/api/auth", tags=["auth"])

DEMO_OFFICER_EMAIL = "officer@demo.cpcl.in"


def _token_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email/password + CAPTCHA and return a JWT."""
    if not captcha_service.verify(payload.captcha_id, payload.captcha_text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired security code. Please try a new code.",
        )
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="LOGIN",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"email": user.email},
    )
    return _token_for(user)


@router.get("/captcha", response_model=CaptchaOut)
def get_captcha():
    """Issue a fresh CAPTCHA challenge for the login form."""
    captcha_id, image = captcha_service.generate()
    return CaptchaOut(captcha_id=captcha_id, image=image)


@router.post("/demo", response_model=TokenResponse)
def demo_login(db: Session = Depends(get_db)):
    """Log in as the seeded demo Procurement Officer (no credentials)."""
    user = db.query(User).filter(User.email == DEMO_OFFICER_EMAIL).one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo user is not seeded",
        )
    audit_service.append_audit(
        db,
        user_id=user.id,
        action="LOGIN",
        entity_type="user",
        entity_id=str(user.id),
        metadata={"email": user.email, "via": "demo"},
    )
    return _token_for(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserOut.model_validate(user)
