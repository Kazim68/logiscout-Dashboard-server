"""
Authentication Routes
Handles email/password signup and signin endpoints.
Tokens are stored in httpOnly cookies for security.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status, Depends
from pydantic import BaseModel

from app.schemas.user_schema import (
    UserSignUpRequest,
    UserSignInRequest,
    AuthResponse,
    OTPVerifyRequest,
    OTPResendRequest,
    OnboardingRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UpdatePasswordRequest,
)
from app.services.auth_service import auth_service
from app.services.otp_service import otp_service
from app.utils.response_handler import create_response
from app.dependencies.auth_dependency import get_current_user
from app.core.config import settings
from app.core.security import decode_access_token
from app.core.logging_config import get_logger
from app.core import database as db
from app.models.user_model import user_helper

logger = get_logger(__name__)


COOKIE_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # seconds


def set_auth_cookie(response: Response, token: str):
    """Set httpOnly cookie with JWT token."""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=COOKIE_MAX_AGE,
        path="/",
    )


def clear_auth_cookie(response: Response):
    """Clear the auth cookie."""
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


@router.post(
    "/signup",
    status_code=status.HTTP_200_OK,
    summary="Register a new user (sends OTP)",
    description="Initiate signup by storing pending data and sending a verification OTP to the user's email."
)
async def signup(request: UserSignUpRequest):
    """
    Step 1 of email signup.
    Saves pending signup data and sends a 6-digit OTP to the user's email.
    The user must verify the OTP via /api/auth/verify-otp to complete registration.
    """
    success, message = await otp_service.create_pending_signup(
        name=request.name,
        email=request.email,
        password=request.password,
        company=request.company,
    )

    if not success:
        logger.info("Signup rejected: %s — %s", request.email, message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_response(success=False, message=message),
        )

    return create_response(
        success=True,
        message=message,
        data={"email": request.email.lower()},
    )


@router.post(
    "/verify-otp",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Verify OTP and complete signup",
    description="Verify the emailed OTP code to finish account creation."
)
async def verify_otp(request: OTPVerifyRequest, response: Response):
    """
    Step 2 of email signup.
    Verifies the OTP, creates the user account, and sets the auth cookie.
    """
    success, message, user_data, token = await otp_service.verify_otp(
        email=request.email,
        otp=request.otp,
    )

    if not success:
        logger.info("OTP verification failed for %s: %s", request.email, message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_response(success=False, message=message),
        )

    # Set JWT in httpOnly cookie
    set_auth_cookie(response, token)
    logger.info("OTP verified, user logged in: %s", request.email)

    return create_response(
        success=True,
        message=message,
        data=user_data,
    )


@router.post(
    "/resend-otp",
    status_code=status.HTTP_200_OK,
    summary="Resend OTP",
    description="Resend the OTP verification code to the user's email."
)
async def resend_otp(request: OTPResendRequest):
    """
    Re-generate and resend the OTP for a pending signup.
    """
    success, message = await otp_service.resend_otp(email=request.email)

    if not success:
        logger.info("Resend OTP failed for %s: %s", request.email, message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_response(success=False, message=message),
        )

    return create_response(success=True, message=message)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="User login",
    description="Authenticate user with email and password."
)
async def login(request: UserSignInRequest, response: Response):
    """
    Authenticate user with email and password.
    
    - **email**: User's registered email address
    - **password**: User's password
    
    Returns user data. JWT token is set as httpOnly cookie.
    """
    success, message, user_data, token = await auth_service.signin(request)
    
    if not success:
        logger.info("Login failed for %s: %s", request.email, message)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=create_response(
                success=False,
                message=message
            )
        )
    
    # Set JWT in httpOnly cookie
    set_auth_cookie(response, token)
    
    logger.info("User logged in: %s", request.email)
    return create_response(
        success=True,
        message=message,
        data=user_data
    )


@router.get(
    "/me",
    summary="Get current user",
    description="Get the currently authenticated user's information from cookie session."
)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get current user information from the cookie-based session.
    Returns user data if the httpOnly cookie contains a valid JWT.
    """
    return create_response(
        success=True,
        message="User session active",
        data=current_user
    )


@router.post(
    "/onboarding",
    status_code=status.HTTP_200_OK,
    summary="Complete user onboarding",
    description="Save onboarding preferences and mark the user as onboarded."
)
async def complete_onboarding(
    request: OnboardingRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Save onboarding data (role, team_size, use_case, industry, etc.)
    and mark onboarding_completed = True on the user document.
    Optionally creates a first project.
    """
    from bson import ObjectId

    user_id = current_user["id"]

    update_fields = {
        "onboarding_completed": True,
    }
    if request.company:
        update_fields["company"] = request.company
    if request.role:
        update_fields["role"] = request.role
    if request.team_size:
        update_fields["team_size"] = request.team_size
    if request.use_case:
        update_fields["use_case"] = request.use_case
    if request.industry:
        update_fields["industry"] = request.industry
    if request.notification_preferences:
        update_fields["notification_preferences"] = request.notification_preferences

    await db.Users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_fields},
    )

    # Optionally create first project
    project_data = None
    token_data = None
    if request.project_name:
        from app.services.project_service import project_service as ps

        project = await ps.create_project(
            name=request.project_name,
            owner_id=user_id,
            description=request.project_description or "",
        )
        project_id = str(project["_id"])

        token_doc, plain_token = await ps.create_token(
            project_id=project_id,
            owner_id=user_id,
            label="Default API Key",
        )

        project_data = {
            "id": project_id,
            "name": request.project_name,
        }
        token_data = {
            "id": str(token_doc["_id"]),
            "token": plain_token,
        }

        logger.info("Onboarding project created for user %s: %s", user_id, project_id)

    # Return refreshed user data
    updated_user = await db.Users.find_one({"_id": ObjectId(user_id)})
    user_data = user_helper(updated_user)

    logger.info("Onboarding completed for user %s", user_id)

    return create_response(
        success=True,
        message="Onboarding completed",
        data={
            "user": user_data,
            "project": project_data,
            "token": token_data,
        },
    )


@router.post(
    "/logout",
    summary="Logout user",
    description="Clear the auth cookie to end the session."
)
async def logout_user(response: Response):
    """
    Logout the current user by clearing the httpOnly auth cookie.
    """
    clear_auth_cookie(response)
    logger.info("User logged out")
    return create_response(
        success=True,
        message="Logged out successfully",
        data=None
    )


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request a password reset code",
)
async def forgot_password(request: ForgotPasswordRequest):
    success, message = await auth_service.create_password_reset(request.email)
    return create_response(success=True, message=message)


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset password with code",
)
async def reset_password(request: ResetPasswordRequest):
    success, message, status_code = await auth_service.reset_password(
        reset_token=request.resetToken,
        new_password=request.newPassword,
    )
    if not success:
        raise HTTPException(
            status_code=status_code,
            detail=create_response(success=False, message=message),
        )
    return create_response(success=True, message=message)


@router.post(
    "/update-password",
    status_code=status.HTTP_200_OK,
    summary="Update password (authenticated)",
    description="Change the current user's password. Requires the current password for verification.",
)
async def update_password(
    request: UpdatePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    success, message = await auth_service.update_password(
        user_id=current_user["id"],
        current_password=request.currentPassword,
        new_password=request.newPassword,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_response(success=False, message=message),
        )
    logger.info("Password updated for user %s", current_user["id"])
    return create_response(success=True, message=message)


class SessionTokenRequest(BaseModel):
    token: str


@router.post(
    "/session",
    status_code=status.HTTP_200_OK,
    summary="Exchange a JWT for an httpOnly cookie session",
    description="Validates a JWT and sets it as an httpOnly cookie. Used by the frontend after OAuth redirect.",
)
async def set_session(request: SessionTokenRequest, response: Response):
    """
    Exchange a JWT token (received via OAuth redirect fragment) for an
    httpOnly cookie session.  This ensures the cookie is set on an
    XHR response from the frontend's origin, which is reliable across
    all browsers and cross-origin setups.
    """
    payload = decode_access_token(request.token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=create_response(success=False, message="Invalid or expired token"),
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=create_response(success=False, message="Invalid token payload"),
        )

    user = await auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=create_response(success=False, message="User not found"),
        )

    set_auth_cookie(response, request.token)
    logger.info("Session set via token exchange for user %s", user_id)

    return create_response(
        success=True,
        message="Session created",
        data=user_helper(user),
    )
