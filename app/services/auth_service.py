"""
Authentication Service
Handles user registration, login, and authentication logic.
"""

import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

from app.core import database as db
from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_token_payload
)
from app.core.logging_config import get_logger
from app.models.user_model import user_helper
from app.schemas.user_schema import UserSignUpRequest, UserSignInRequest
from app.utils.email_sender import send_reset_code_email

logger = get_logger(__name__)


class AuthService:
    """
    Service class for authentication operations.
    Handles all business logic for user authentication.
    """
    
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a user by email address.
        
        Args:
            email: User's email address
            
        Returns:
            User document if found, None otherwise
        """
        user = await db.Users.find_one({"email": email.lower()})
        if user:
            logger.debug("Found user by email: %s", email.lower())
        return user
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a user by their ID.
        
        Args:
            user_id: User's MongoDB ObjectId as string
            
        Returns:
            User document if found, None otherwise
        """
        from bson import ObjectId
        
        try:
            user = await db.Users.find_one({"_id": ObjectId(user_id)})
            return user
        except Exception:
            logger.warning("Invalid user_id format: %s", user_id)
            return None
    
    @staticmethod
    async def create_user(
        name: str,
        email: str,
        password: Optional[str] = None,
        provider: str = "email",
        provider_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new user in the database.
        
        Args:
            name: User's full name
            email: User's email address
            password: Plain text password (will be hashed)
            provider: Authentication provider (email/google/github)
            provider_id: External provider's user ID
            
        Returns:
            Created user document
        """
        # Prepare user document
        user_doc = {
            "name": name,
            "email": email.lower(),
            "password": hash_password(password) if password else None,
            "provider": provider,
            "provider_id": provider_id,
            "created_at": datetime.now(timezone.utc)
        }

        # Insert user
        result = await db.Users.insert_one(user_doc)

        # Retrieve and return created user
        created_user = await db.Users.find_one({"_id": result.inserted_id})
        logger.info("User created: %s (provider=%s)", email.lower(), provider, extra={"email": email.lower()})
        return created_user
    
    @staticmethod
    async def signup(request: UserSignUpRequest) -> Tuple[bool, str, Optional[Dict], Optional[str]]:
        """
        Register a new user with email and password.
        
        Args:
            request: User signup request data
            
        Returns:
            Tuple of (success, message, user_data, token)
        """
        # Check if user already exists
        existing_user = await AuthService.get_user_by_email(request.email)
        if existing_user:
            logger.info("Signup attempt with existing email: %s", request.email)
            return (False, "Email already registered", None, None)
        
        # Create new user
        user = await AuthService.create_user(
            name=request.name,
            email=request.email,
            password=request.password,
            provider="email"
        )
        
        # Generate JWT token
        token_payload = create_token_payload(
            user_id=str(user["_id"]),
            email=user["email"],
            provider=user["provider"]
        )
        token = create_access_token(token_payload)
        
        # Format user data for response
        user_data = user_helper(user)
        
        return (True, "Account created successfully", user_data, token)
    
    @staticmethod
    async def signin(request: UserSignInRequest) -> Tuple[bool, str, Optional[Dict], Optional[str]]:
        """
        Authenticate a user with email and password.
        
        Args:
            request: User signin request data
            
        Returns:
            Tuple of (success, message, user_data, token)
        """
        # Find user by email
        user = await AuthService.get_user_by_email(request.email)
        
        if not user:
            logger.info("Login attempt for non-existent email: %s", request.email)
            return (False, "Invalid email or password", None, None)
        
        # Check if user signed up with OAuth
        if user.get("provider") != "email":
            return (
                False,
                f"This account uses {user['provider']} authentication. Please sign in with {user['provider']}.",
                None,
                None
            )
        
        # Verify password
        if not user.get("password"):
            return (False, "Invalid email or password", None, None)
        
        if not verify_password(request.password, user["password"]):
            logger.warning("Failed login attempt for: %s", request.email, extra={"email": request.email})
            return (False, "Invalid email or password", None, None)
        
        # Generate JWT token
        token_payload = create_token_payload(
            user_id=str(user["_id"]),
            email=user["email"],
            provider=user["provider"]
        )
        token = create_access_token(token_payload)
        
        # Format user data for response
        user_data = user_helper(user)
        
        return (True, "Login successful", user_data, token)
    
    @staticmethod
    async def get_or_create_oauth_user(
        email: str,
        name: str,
        provider: str,
        provider_id: str
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Get existing user or create new one for OAuth authentication.
        
        Args:
            email: User's email from OAuth provider
            name: User's name from OAuth provider
            provider: OAuth provider name (google/github)
            provider_id: User's ID from OAuth provider
            
        Returns:
            Tuple of (user_data, is_new_user)
        """
        # Check if user exists by email
        existing_user = await AuthService.get_user_by_email(email)
        
        if existing_user:
            # Update provider info if needed
            if existing_user.get("provider") != provider:
                logger.info("OAuth login for existing user with different provider: %s (orig=%s, new=%s)", email, existing_user.get("provider"), provider)
                pass
            logger.info("OAuth login success: %s via %s", email, provider)
            return (existing_user, False)
        
        # Create new user
        user = await AuthService.create_user(
            name=name,
            email=email,
            provider=provider,
            provider_id=provider_id
        )
        
        logger.info("New OAuth user created: %s via %s", email, provider)
        return (user, True)
    
    @staticmethod
    def generate_auth_response(
        user: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], str]:
        """
        Generate authentication response with user data and token.
        
        Args:
            user: User document from database
            
        Returns:
            Tuple of (user_data, token)
        """
        # Generate JWT token
        token_payload = create_token_payload(
            user_id=str(user["_id"]),
            email=user["email"],
            provider=user["provider"]
        )
        token = create_access_token(token_payload)
        
        # Format user data
        user_data = user_helper(user)
        
        return (user_data, token)

    # ------------------------------------------------------------------
    # Password Reset
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_reset_code() -> str:
        return "".join(random.choices(string.digits, k=6))

    @staticmethod
    async def _ensure_reset_ttl_index():
        try:
            await db.PasswordResets.create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            await db.PasswordResets.drop_index("expires_at_1")
            await db.PasswordResets.create_index("expires_at", expireAfterSeconds=0)

    @staticmethod
    async def create_password_reset(email: str) -> Tuple[bool, str]:
        await AuthService._ensure_reset_ttl_index()

        user = await AuthService.get_user_by_email(email)
        if not user:
            return (True, "If that email is registered, a reset code has been sent")

        if user.get("provider") != "email":
            return (True, "If that email is registered, a reset code has been sent")

        code = AuthService._generate_reset_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.RESET_CODE_EXPIRE_MINUTES)

        await db.PasswordResets.update_one(
            {"email": email.lower()},
            {
                "$set": {
                    "email": email.lower(),
                    "code": code,
                    "expires_at": expires_at,
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

        send_reset_code_email(
            to_email=email,
            code=code,
            user_name=user.get("name", "there"),
        )
        logger.info("Password reset code sent to %s", email)
        return (True, "If that email is registered, a reset code has been sent")

    @staticmethod
    async def reset_password(reset_token: str, new_password: str) -> Tuple[bool, str, int]:
        doc = await db.PasswordResets.find_one({"code": reset_token})

        if not doc:
            return (False, "Invalid or expired token", 401)

        expires_at = doc.get("expires_at")
        if expires_at:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                await db.PasswordResets.delete_one({"_id": doc["_id"]})
                return (False, "Invalid or expired token", 401)

        user = await db.Users.find_one({"email": doc["email"]})
        if not user:
            await db.PasswordResets.delete_one({"_id": doc["_id"]})
            return (False, "Invalid or expired token", 401)

        await db.Users.update_one(
            {"_id": user["_id"]},
            {"$set": {"password": hash_password(new_password)}},
        )

        await db.PasswordResets.delete_one({"_id": doc["_id"]})

        logger.info("Password reset completed for %s", doc["email"])
        return (True, "Password updated successfully", 200)

    # ------------------------------------------------------------------
    # Update Password (authenticated)
    # ------------------------------------------------------------------

    @staticmethod
    async def update_password(
        user_id: str, current_password: str, new_password: str
    ) -> Tuple[bool, str]:
        from bson import ObjectId

        user = await AuthService.get_user_by_id(user_id)
        if not user:
            return (False, "User not found")

        if user.get("provider") != "email":
            return (False, "Password change is only available for email accounts")

        if not user.get("password"):
            return (False, "No password set for this account")

        if not verify_password(current_password, user["password"]):
            logger.warning("Incorrect current password for user %s", user_id)
            return (False, "Current password is incorrect")

        await db.Users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"password": hash_password(new_password)}},
        )

        logger.info("Password updated for user %s", user_id)
        return (True, "Password updated successfully")


# Export singleton instance
auth_service = AuthService()
