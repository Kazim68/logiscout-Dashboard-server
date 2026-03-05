"""
Google OAuth Routes
Handles Google OAuth 2.0 authentication flow.
Tokens are stored in httpOnly cookies for security.
"""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, status, Query, Response
from fastapi.responses import RedirectResponse

from app.services.google_oauth_service import google_oauth_service
from app.services.auth_service import auth_service
from app.utils.response_handler import create_response
from app.core.config import settings
from app.core.logging_config import get_logger
from app.routes.auth_routes import set_auth_cookie

logger = get_logger(__name__)


router = APIRouter(
    prefix="/api/auth",
    tags=["Google OAuth"]
)


@router.get(
    "/google",
    summary="Initiate Google OAuth",
    description="Redirect user to Google OAuth authorization page."
)
async def google_oauth_redirect():
    """
    Initiate Google OAuth 2.0 flow.
    
    Redirects the user to Google's OAuth authorization page.
    After authorization, Google redirects back to the callback URL.
    """
    # Generate authorization URL
    auth_url = google_oauth_service.get_authorization_url()
    
    # Return redirect URL for frontend to handle
    return create_response(
        success=True,
        message="Redirect to Google OAuth",
        data={"redirect_url": auth_url}
    )


@router.get(
    "/google/callback",
    summary="Google OAuth callback",
    description="Handle callback from Google after authorization."
)
async def google_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(None, description="State parameter for CSRF protection"),
    error: str = Query(None, description="Error from Google OAuth")
):
    """
    Handle Google OAuth callback.
    
    This endpoint is called by Google after user authorization.
    It exchanges the authorization code for user information
    and creates/logs in the user.
    
    - **code**: Authorization code from Google
    - **state**: Optional state parameter
    - **error**: Error message if authorization failed
    """
    # Handle error from Google
    if error:
        logger.warning("Google OAuth error: %s", error)
        # Redirect to frontend with URL-encoded error
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}?error={quote(error)}&provider=google",
            status_code=302
        )
    
    # Authenticate with Google
    success, user_info, error_msg = await google_oauth_service.authenticate(code)
    
    if not success:
        logger.warning("Google OAuth authenticate failed: %s", error_msg)
        # Redirect to frontend with URL-encoded error
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}?error={quote(error_msg or 'authentication_failed')}&provider=google",
            status_code=302
        )
    
    # Get or create user in database
    user, is_new = await auth_service.get_or_create_oauth_user(
        email=user_info["email"],
        name=user_info["name"],
        provider="google",
        provider_id=user_info["provider_id"]
    )
    
    # Generate auth response
    user_data, token = auth_service.generate_auth_response(user)

    # Redirect to frontend callback with the JWT as a query parameter.
    # The frontend immediately exchanges it for an httpOnly cookie via XHR
    # and clears it from the URL.
    redirect_url = (
        f"{settings.FRONTEND_URL}/auth/callback"
        f"?provider=google&new_user={str(is_new).lower()}&token={token}"
    )
    logger.info("Google OAuth callback success: %s (new=%s)", user_info["email"], is_new)
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post(
    "/google/token",
    summary="Exchange Google code for token",
    description="Exchange authorization code for JWT token (for SPA flow)."
)
async def google_oauth_token(code: str, response: Response):
    """
    Exchange Google authorization code for JWT token.
    
    This endpoint is for Single Page Applications that handle
    the OAuth flow client-side and need to exchange the code
    for a JWT token. Token is set as httpOnly cookie.
    
    - **code**: Authorization code from Google
    """
    # Authenticate with Google
    success, user_info, error_msg = await google_oauth_service.authenticate(code)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_response(
                success=False,
                message=error_msg or "Google authentication failed"
            )
        )
    
    # Get or create user in database
    user, is_new = await auth_service.get_or_create_oauth_user(
        email=user_info["email"],
        name=user_info["name"],
        provider="google",
        provider_id=user_info["provider_id"]
    )
    
    # Generate auth response
    user_data, token = auth_service.generate_auth_response(user)
    
    # Set httpOnly cookie
    set_auth_cookie(response, token)
    
    action = "Account created" if is_new else "Login successful"
    
    return create_response(
        success=True,
        message=f"{action} with Google",
        data=user_data
    )
