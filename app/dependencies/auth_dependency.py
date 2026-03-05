"""
Authentication Dependency
Provides JWT token validation for protected routes.
Reads token from httpOnly cookie (primary) or Authorization header (fallback).
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.core.security import decode_access_token
from app.services.auth_service import auth_service
from app.models.user_model import user_helper
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# HTTP Bearer token security scheme (used as fallback / Swagger UI)
security = HTTPBearer(
    scheme_name="JWT",
    description="Enter your JWT token",
    auto_error=False  # Don't auto-error; we check cookie first
)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Dependency to get the current authenticated user.
    
    Reads the JWT token from:
      1. httpOnly cookie 'access_token' (primary)
      2. Authorization Bearer header (fallback for API clients)
    
    Returns the user information dict.
    """
    token: Optional[str] = None
    
    # 1. Try httpOnly cookie first
    token = request.cookies.get("access_token")
    
    # 2. Fallback to Authorization header
    if not token and credentials:
        token = credentials.credentials
    
    if not token:
        logger.debug("Auth rejected: no token in cookie or header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "Not authenticated",
                "data": None,
                "token": None
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Decode and validate token
    payload = decode_access_token(token)
    
    if payload is None:
        logger.warning("Auth rejected: invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "Invalid or expired token",
                "data": None,
                "token": None
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Extract user_id from token
    user_id = payload.get("user_id")
    
    if not user_id:
        logger.warning("Auth rejected: no user_id in token payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "Invalid token payload",
                "data": None,
                "token": None
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Fetch user from database
    user = await auth_service.get_user_by_id(user_id)
    
    if not user:
        logger.warning("Auth rejected: user not found in DB (user_id=%s)", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "message": "User not found",
                "data": None,
                "token": None
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Return formatted user data
    return user_helper(user)


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[dict]:
    """
    Optional dependency to get the current user if authenticated.
    
    Unlike get_current_user, this does not raise an error if
    no token is provided. Useful for endpoints that work both
    authenticated and unauthenticated.
    """
    if not request.cookies.get("access_token") and not credentials:
        return None
    
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def require_provider(allowed_providers: list):
    """
    Dependency factory to require specific authentication providers.
    
    Args:
        allowed_providers: List of allowed providers (e.g., ["email", "google"])
        
    Returns:
        Dependency function that validates provider
        
    Example:
        @router.get("/email-only")
        async def email_only_route(
            user: dict = Depends(require_provider(["email"]))
        ):
            ...
    """
    async def provider_checker(
        current_user: dict = Depends(get_current_user)
    ) -> dict:
        if current_user.get("provider") not in allowed_providers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "message": f"This action requires authentication via: {', '.join(allowed_providers)}",
                    "data": None,
                    "token": None
                }
            )
        return current_user
    
    return provider_checker
