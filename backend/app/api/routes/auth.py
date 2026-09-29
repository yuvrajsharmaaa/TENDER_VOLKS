from typing import Callable

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.auth import AuthLog, User
from backend.app.models.bid_compliance import Bidder
from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

bearer_scheme = HTTPBearer(
    auto_error=False,
)


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    company_name: str = Field(min_length=2, max_length=500)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    bidder_id: str | None
    company_name: str | None
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


def _request_metadata(request: Request):
    return {
        "ip_address": (
            request.client.host
            if request.client
            else None
        ),
        "user_agent": request.headers.get("user-agent"),
    }


def _write_auth_log(
    db: Session,
    *,
    user_id: str | None,
    email: str | None,
    event_type: str,
    success: bool,
    request: Request,
    details: dict | None = None,
):
    metadata = _request_metadata(request)

    db.add(
        AuthLog(
            user_id=user_id,
            email=email,
            event_type=event_type,
            success=success,
            ip_address=metadata["ip_address"],
            user_agent=metadata["user_agent"],
            details=details,
        )
    )


def _serialize_user(
    user: User,
) -> UserResponse:
    company_name = None

    if user.bidder:
        company_name = user.bidder.legal_name

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        bidder_id=user.bidder_id,
        company_name=company_name,
        is_active=user.is_active,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    payload = decode_access_token(credentials.credentials)

    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
        )

    user = (
        db.query(User)
        .filter(User.id == payload["sub"])
        .first()
    )

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or unavailable.",
        )

    return user


def require_role(
    required_role: str,
) -> Callable:

    def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:

        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This resource requires the {required_role} role."
                ),
            )

        return current_user

    return dependency


@router.post(
    "/register",
    response_model=AuthResponse,
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower().strip()

    existing = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if existing:
        _write_auth_log(
            db,
            user_id=existing.id,
            email=email,
            event_type="REGISTER_FAILED",
            success=False,
            request=request,
            details={"reason": "email_already_registered"},
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    bidder = Bidder(
        legal_name=payload.company_name.strip(),
        profile_data={
            "account_created_via": "self_service_registration",
        },
    )

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        role="BIDDER",
        bidder=bidder,
        is_active=True,
    )

    db.add(bidder)
    db.add(user)

    try:
        db.flush()

        _write_auth_log(
            db,
            user_id=user.id,
            email=user.email,
            event_type="REGISTER_SUCCESS",
            success=True,
            request=request,
            details={
                "role": "BIDDER",
                "bidder_id": bidder.id,
            },
        )

        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()

        _write_auth_log(
            db,
            user_id=None,
            email=email,
            event_type="REGISTER_FAILED",
            success=False,
            request=request,
            details={"reason": "database_integrity_error"},
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create the account.",
        )

    token = create_access_token(
        user_id=user.id,
        role=user.role,
    )

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=_serialize_user(user),
    )


@router.post(
    "/login",
    response_model=AuthResponse,
)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower().strip()

    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user or not verify_password(
        payload.password,
        user.hashed_password,
    ):
        _write_auth_log(
            db,
            user_id=user.id if user else None,
            email=email,
            event_type="LOGIN_FAILED",
            success=False,
            request=request,
            details={"reason": "invalid_credentials"},
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not user.is_active:
        _write_auth_log(
            db,
            user_id=user.id,
            email=email,
            event_type="LOGIN_FAILED",
            success=False,
            request=request,
            details={"reason": "inactive_account"},
        )
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive.",
        )

    from datetime import datetime, timezone

    user.last_login_at = datetime.now(timezone.utc)

    _write_auth_log(
        db,
        user_id=user.id,
        email=email,
        event_type="LOGIN_SUCCESS",
        success=True,
        request=request,
        details={"role": user.role},
    )

    db.commit()
    db.refresh(user)

    token = create_access_token(
        user_id=user.id,
        role=user.role,
    )

    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=_serialize_user(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def me(
    current_user: User = Depends(get_current_user),
):
    return _serialize_user(current_user)


@router.get("/activity")
def activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(AuthLog)
        .filter(AuthLog.user_id == current_user.id)
        .order_by(AuthLog.created_at.desc())
        .limit(50)
        .all()
    )

    return [
        {
            "id": log.id,
            "event_type": log.event_type,
            "success": log.success,
            "ip_address": log.ip_address,
            "created_at": log.created_at,
            "details": log.details,
        }
        for log in logs
    ]


@router.post("/logout")
def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _write_auth_log(
        db,
        user_id=current_user.id,
        email=current_user.email,
        event_type="LOGOUT",
        success=True,
        request=request,
    )

    db.commit()

    return {
        "success": True,
        "message": "Logout recorded.",
    }
