"""
User Model
Defines the User document structure for MongoDB.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId


class PyObjectId(ObjectId):
    """
    Custom ObjectId type for Pydantic models.
    Enables proper serialization of MongoDB ObjectIds.
    """
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v, handler=None):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)
    
    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        return {"type": "string"}


class UserModel(BaseModel):
    """
    User document model for MongoDB.
    
    Attributes:
        id: MongoDB ObjectId (auto-generated)
        name: User's full name
        email: User's email address (unique)
        password: Hashed password (nullable for OAuth users)
        provider: Authentication provider (email/google/github)
        provider_id: External provider's user ID (for OAuth)
        company: Organization / company name
        role: User's job role (e.g. DevOps Engineer, SRE, CTO)
        team_size: Size of the user's team
        use_case: Primary use case for LogiScout
        industry: Company industry vertical
        notification_preferences: Alert channel preferences
        onboarding_completed: Whether the user finished the onboarding wizard
        created_at: Account creation timestamp
    """
    
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    email: EmailStr
    password: Optional[str] = None  # Nullable for OAuth users
    provider: str = "email"  # email | google | github
    provider_id: Optional[str] = None  # External provider's user ID
    company: Optional[str] = None
    role: Optional[str] = None
    team_size: Optional[str] = None
    use_case: Optional[str] = None
    industry: Optional[str] = None
    notification_preferences: Optional[list] = Field(default_factory=list)
    onboarding_completed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "password": "hashed_password_here",
                "provider": "email",
                "provider_id": None,
                "company": "Acme Corp",
                "role": "DevOps Engineer",
                "team_size": "11-50",
                "use_case": "log_management",
                "industry": "saas",
                "notification_preferences": ["email", "slack"],
                "onboarding_completed": False,
                "created_at": "2024-01-01T00:00:00Z"
            }
        }


class UserInDB(UserModel):
    """
    User model as stored in database.
    Includes the MongoDB _id field.
    """
    pass


def user_helper(user: dict) -> dict:
    """
    Helper function to format user document from MongoDB.
    Converts ObjectId to string and removes sensitive data.
    
    Args:
        user: Raw user document from MongoDB
        
    Returns:
        Formatted user dictionary safe for API response
    """
    return {
        "id": str(user["_id"]),
        "name": user.get("name", ""),
        "email": user.get("email", ""),
        "provider": user.get("provider", "email"),
        "provider_id": user.get("provider_id"),
        "company": user.get("company"),
        "role": user.get("role"),
        "team_size": user.get("team_size"),
        "use_case": user.get("use_case"),
        "industry": user.get("industry"),
        "notification_preferences": user.get("notification_preferences", []),
        "onboarding_completed": user.get("onboarding_completed", False),
        "created_at": user.get("created_at", datetime.now(timezone.utc)).isoformat()
    }
