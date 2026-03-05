"""
Google OAuth Service
Handles Google OAuth 2.0 authentication flow.
"""

import httpx
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlencode

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class GoogleOAuthService:
    """
    Service class for Google OAuth 2.0 operations.
    Implements the Authorization Code flow.
    """
    
    # Google OAuth endpoints
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    
    # OAuth scopes
    SCOPES = [
        "openid",
        "email",
        "profile"
    ]
    
    @classmethod
    def get_authorization_url(cls, state: Optional[str] = None) -> str:
        """
        Generate Google OAuth authorization URL.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Google OAuth authorization URL
        """
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(cls.SCOPES),
            "access_type": "offline",
            "prompt": "consent"
        }
        
        if state:
            params["state"] = state
        
        return f"{cls.AUTHORIZATION_URL}?{urlencode(params)}"
    
    @classmethod
    async def exchange_code_for_token(cls, code: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from Google
            
        Returns:
            Tuple of (success, token_data, error_message)
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    cls.TOKEN_URL,
                    data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "code": code,
                        "grant_type": "authorization_code",
                        "redirect_uri": settings.GOOGLE_REDIRECT_URI
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded"
                    }
                )
                
                if response.status_code != 200:
                    error_data = response.json()
                    return (False, None, error_data.get("error_description", "Token exchange failed"))
                
                token_data = response.json()
                return (True, token_data, None)
                
            except httpx.RequestError as e:
                return (False, None, f"Network error: {str(e)}")
    
    @classmethod
    async def get_user_info(cls, access_token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Fetch user information from Google using access token.
        
        Args:
            access_token: Google OAuth access token
            
        Returns:
            Tuple of (success, user_info, error_message)
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    cls.USERINFO_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}"
                    }
                )
                
                if response.status_code != 200:
                    return (False, None, "Failed to fetch user info")
                
                user_info = response.json()
                return (True, user_info, None)
                
            except httpx.RequestError as e:
                return (False, None, f"Network error: {str(e)}")
    
    @classmethod
    async def authenticate(cls, code: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Complete Google OAuth authentication flow.
        
        Args:
            code: Authorization code from Google callback
            
        Returns:
            Tuple of (success, user_info, error_message)
            user_info contains: id, email, name, picture
        """
        # Exchange code for token
        success, token_data, error = await cls.exchange_code_for_token(code)
        if not success:
            return (False, None, error)
        
        # Get user info
        access_token = token_data.get("access_token")
        if not access_token:
            return (False, None, "No access token received")
        
        success, user_info, error = await cls.get_user_info(access_token)
        if not success:
            return (False, None, error)
        
        # Format user info
        formatted_user = {
            "provider_id": user_info.get("id"),
            "email": user_info.get("email"),
            "name": user_info.get("name", user_info.get("email", "").split("@")[0]),
            "picture": user_info.get("picture")
        }
        
        logger.info("Google OAuth success for: %s", formatted_user.get("email"))
        return (True, formatted_user, None)


# Export singleton instance
google_oauth_service = GoogleOAuthService()
