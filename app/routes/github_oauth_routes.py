"""
GitHub OAuth Routes
Handles GitHub OAuth 2.0 authentication flow.
Tokens are stored in httpOnly cookies for security.
"""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, status, Query, Response
from fastapi.responses import RedirectResponse

from app.services.github_oauth_service import github_oauth_service
from app.services.auth_service import auth_service
from app.utils.response_handler import create_response
from app.core.config import settings
from app.core.logging_config import get_logger
from app.routes.auth_routes import set_auth_cookie

logger = get_logger(__name__)


router = APIRouter(
    prefix="/api/auth",
    tags=["GitHub OAuth"]
)


@router.get(
    "/github",
    summary="Initiate GitHub OAuth",
    description="Redirect user to GitHub OAuth authorization page."
)
async def github_oauth_redirect():
    """
    Initiate GitHub OAuth 2.0 flow.
    
    Redirects the user to GitHub's OAuth authorization page.
    After authorization, GitHub redirects back to the callback URL.
    """
    # Generate authorization URL
    auth_url = github_oauth_service.get_authorization_url()
    
    # Return redirect URL for frontend to handle
    return create_response(
        success=True,
        message="Redirect to GitHub OAuth",
        data={"redirect_url": auth_url}
    )


@router.get(
    "/github/callback",
    summary="GitHub OAuth callback",
    description="Handle callback from GitHub after authorization."
)
async def github_oauth_callback(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(None, description="State parameter for CSRF protection"),
    error: str = Query(None, description="Error from GitHub OAuth"),
    error_description: str = Query(None, description="Error description from GitHub")
):
    """
    Handle GitHub OAuth callback.
    
    This endpoint is called by GitHub after user authorization.
    It exchanges the authorization code for user information
    and creates/logs in the user.
    
    - **code**: Authorization code from GitHub
    - **state**: Optional state parameter
    - **error**: Error type if authorization failed
    - **error_description**: Detailed error message
    """
    # Handle error from GitHub
    if error:
        error_msg = error_description or error
        logger.warning("GitHub OAuth error: %s", error_msg)
        # Redirect to frontend with URL-encoded error
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}?error={quote(error_msg)}&provider=github",
            status_code=302
        )
    
    # Authenticate with GitHub
    success, user_info, error_msg = await github_oauth_service.authenticate(code)
    
    if not success:
        logger.warning("GitHub OAuth authenticate failed: %s", error_msg)
        # Redirect to frontend with URL-encoded error
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}?error={quote(error_msg or 'authentication_failed')}&provider=github",
            status_code=302
        )
    
    # Get or create user in database
    user, is_new = await auth_service.get_or_create_oauth_user(
        email=user_info["email"],
        name=user_info["name"],
        provider="github",
        provider_id=user_info["provider_id"]
    )
    
    # Generate auth response
    user_data, token = auth_service.generate_auth_response(user)

    # Redirect to frontend callback with the JWT as a query parameter.
    # The frontend immediately exchanges it for an httpOnly cookie via XHR
    # and clears it from the URL.
    redirect_url = (
        f"{settings.FRONTEND_URL}/auth/callback"
        f"?provider=github&new_user={str(is_new).lower()}&token={token}"
    )
    logger.info("GitHub OAuth callback success: %s (new=%s)", user_info["email"], is_new)
    return RedirectResponse(url=redirect_url, status_code=302)


@router.post(
    "/github/token",
    summary="Exchange GitHub code for token",
    description="Exchange authorization code for JWT token (for SPA flow)."
)
async def github_oauth_token(code: str, response: Response):
    """
    Exchange GitHub authorization code for JWT token.
    
    This endpoint is for Single Page Applications that handle
    the OAuth flow client-side and need to exchange the code
    for a JWT token. Token is set as httpOnly cookie.
    
    - **code**: Authorization code from GitHub
    """
    # Authenticate with GitHub
    success, user_info, error_msg = await github_oauth_service.authenticate(code)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=create_response(
                success=False,
                message=error_msg or "GitHub authentication failed"
            )
        )
    
    # Get or create user in database
    user, is_new = await auth_service.get_or_create_oauth_user(
        email=user_info["email"],
        name=user_info["name"],
        provider="github",
        provider_id=user_info["provider_id"]
    )
    
    # Generate auth response
    user_data, token = auth_service.generate_auth_response(user)
    
    # Set httpOnly cookie
    set_auth_cookie(response, token)
    
    action = "Account created" if is_new else "Login successful"
    
    return create_response(
        success=True,
        message=f"{action} with GitHub",
        data=user_data
    )
