"""
GitHub OAuth Service
Handles GitHub OAuth 2.0 authentication flow.
"""

import httpx
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlencode

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class GitHubOAuthService:
    """
    Service class for GitHub OAuth 2.0 operations.
    Implements the Authorization Code flow.
    """
    
    # GitHub OAuth endpoints
    AUTHORIZATION_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_API_URL = "https://api.github.com/user"
    EMAILS_API_URL = "https://api.github.com/user/emails"
    
    # OAuth scopes
    SCOPES = [
        "read:user",
        "user:email"
    ]
    
    @classmethod
    def get_authorization_url(cls, state: Optional[str] = None) -> str:
        """
        Generate GitHub OAuth authorization URL.
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            GitHub OAuth authorization URL
        """
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
            "scope": " ".join(cls.SCOPES)
        }
        
        if state:
            params["state"] = state
        
        return f"{cls.AUTHORIZATION_URL}?{urlencode(params)}"
    
    @classmethod
    async def exchange_code_for_token(cls, code: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from GitHub
            
        Returns:
            Tuple of (success, access_token, error_message)
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    cls.TOKEN_URL,
                    data={
                        "client_id": settings.GITHUB_CLIENT_ID,
                        "client_secret": settings.GITHUB_CLIENT_SECRET,
                        "code": code,
                        "redirect_uri": settings.GITHUB_REDIRECT_URI
                    },
                    headers={
                        "Accept": "application/json"
                    }
                )
                
                if response.status_code != 200:
                    return (False, None, "Token exchange failed")
                
                token_data = response.json()
                
                if "error" in token_data:
                    return (False, None, token_data.get("error_description", token_data["error"]))
                
                access_token = token_data.get("access_token")
                if not access_token:
                    logger.warning("GitHub token exchange: no access_token in response")
                    return (False, None, "No access token received")
                
                return (True, access_token, None)
                
            except httpx.RequestError as e:
                logger.error("GitHub token exchange network error: %s", e)
                return (False, None, f"Network error: {str(e)}")
    
    @classmethod
    async def get_user_info(cls, access_token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Fetch user information from GitHub using access token.
        
        Args:
            access_token: GitHub OAuth access token
            
        Returns:
            Tuple of (success, user_info, error_message)
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    cls.USER_API_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json"
                    }
                )
                
                if response.status_code != 200:
                    return (False, None, "Failed to fetch user info")
                
                user_info = response.json()
                return (True, user_info, None)
                
            except httpx.RequestError as e:
                return (False, None, f"Network error: {str(e)}")
    
    @classmethod
    async def get_user_emails(cls, access_token: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Fetch user's primary email from GitHub.
        
        Args:
            access_token: GitHub OAuth access token
            
        Returns:
            Tuple of (success, primary_email, error_message)
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    cls.EMAILS_API_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github.v3+json"
                    }
                )
                
                if response.status_code != 200:
                    return (False, None, "Failed to fetch user emails")
                
                emails = response.json()
                
                # Find primary email
                for email_obj in emails:
                    if email_obj.get("primary") and email_obj.get("verified"):
                        return (True, email_obj["email"], None)
                
                # Fallback to first verified email
                for email_obj in emails:
                    if email_obj.get("verified"):
                        return (True, email_obj["email"], None)
                
                # Fallback to first email
                if emails:
                    return (True, emails[0]["email"], None)
                
                return (False, None, "No email found")
                
            except httpx.RequestError as e:
                return (False, None, f"Network error: {str(e)}")
    
    @classmethod
    async def authenticate(cls, code: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Complete GitHub OAuth authentication flow.
        
        Args:
            code: Authorization code from GitHub callback
            
        Returns:
            Tuple of (success, user_info, error_message)
            user_info contains: id, email, name, avatar_url
        """
        # Exchange code for token
        success, access_token, error = await cls.exchange_code_for_token(code)
        if not success:
            return (False, None, error)
        
        # Get user info
        success, user_info, error = await cls.get_user_info(access_token)
        if not success:
            return (False, None, error)
        
        # Get user email (GitHub may not include email in user info)
        email = user_info.get("email")
        if not email:
            success, email, error = await cls.get_user_emails(access_token)
            if not success:
                return (False, None, error)
        
        # Format user info
        formatted_user = {
            "provider_id": str(user_info.get("id")),
            "email": email,
            "name": user_info.get("name") or user_info.get("login", ""),
            "avatar_url": user_info.get("avatar_url")
        }
        
        logger.info("GitHub OAuth success for: %s", email)
        return (True, formatted_user, None)


# Export singleton instance
github_oauth_service = GitHubOAuthService()
