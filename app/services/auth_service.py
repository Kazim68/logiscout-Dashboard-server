"""
Authentication Service
Handles user registration, login, and authentication logic.
"""

from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from app.core.database import Database, USERS_COLLECTION
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_token_payload
)
from app.core.logging_config import get_logger
from app.models.user_model import user_helper
from app.schemas.user_schema import UserSignUpRequest, UserSignInRequest

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
        collection = Database.get_collection(USERS_COLLECTION)
        user = await collection.find_one({"email": email.lower()})
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
        
        collection = Database.get_collection(USERS_COLLECTION)
        try:
            user = await collection.find_one({"_id": ObjectId(user_id)})
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
        collection = Database.get_collection(USERS_COLLECTION)
        
        # Prepare user document
        user_doc = {
            "name": name,
            "email": email.lower(),
            "password": hash_password(password) if password else None,
            "provider": provider,
            "provider_id": provider_id,
            "created_at": datetime.utcnow()
        }
        
        # Insert user
        result = await collection.insert_one(user_doc)
        
        # Retrieve and return created user
        created_user = await collection.find_one({"_id": result.inserted_id})
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


# Export singleton instance
auth_service = AuthService()
