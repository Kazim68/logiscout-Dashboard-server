"""
User Schemas
Pydantic schemas for request/response validation.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


# ============================================
# Request Schemas
# ============================================

class UserSignUpRequest(BaseModel):
    """
    Schema for user registration request.
    """
    name: str = Field(..., min_length=2, max_length=100, description="User's full name")
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=6, max_length=100, description="User's password")
    company: Optional[str] = Field(None, max_length=100, description="User's company name")
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        """Validate password strength."""
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters long")
        return v
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        """Validate email format."""
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, v):
            raise ValueError("Invalid email format")
        return v.lower()  # Normalize email to lowercase
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "password": "securePass123",
                "company": "Acme Corp"
            }
        }


class UserSignInRequest(BaseModel):
    """
    Schema for user login request.
    """
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")
    
    @field_validator("email")
    @classmethod
    def normalize_email(cls, v):
        """Normalize email to lowercase."""
        return v.lower()
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "john@example.com",
                "password": "securePass123"
            }
        }


# ============================================
# Response Schemas
# ============================================

class UserResponse(BaseModel):
    """
    Schema for user data in responses.
    Excludes sensitive information like password.
    """
    id: str = Field(..., description="User's unique identifier")
    name: str = Field(..., description="User's full name")
    email: EmailStr = Field(..., description="User's email address")
    provider: str = Field(..., description="Authentication provider")
    provider_id: Optional[str] = Field(None, description="External provider's user ID")
    company: Optional[str] = Field(None, description="Company or organization name")
    role: Optional[str] = Field(None, description="User's job role")
    team_size: Optional[str] = Field(None, description="Team size range")
    use_case: Optional[str] = Field(None, description="Primary use case")
    industry: Optional[str] = Field(None, description="Company industry")
    notification_preferences: Optional[list] = Field(default_factory=list, description="Alert channels")
    onboarding_completed: bool = Field(False, description="Whether onboarding is done")
    created_at: str = Field(..., description="Account creation timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "John Doe",
                "email": "john@example.com",
                "provider": "email",
                "provider_id": None,
                "company": "Acme Corp",
                "role": "DevOps Engineer",
                "team_size": "11-50",
                "use_case": "log_management",
                "industry": "saas",
                "notification_preferences": ["email", "slack"],
                "onboarding_completed": True,
                "created_at": "2024-01-01T00:00:00"
            }
        }


class AuthResponse(BaseModel):
    """
    Schema for authentication responses.
    Follows the standard response format for Redux integration.
    """
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Response message")
    data: Optional[UserResponse] = Field(None, description="User data")
    token: Optional[str] = Field(None, description="JWT access token")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Login successful",
                "data": {
                    "id": "507f1f77bcf86cd799439011",
                    "name": "John Doe",
                    "email": "john@example.com",
                    "provider": "email",
                    "provider_id": None,
                    "created_at": "2024-01-01T00:00:00"
                },
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class DashboardStats(BaseModel):
    """
    Schema for dashboard statistics.
    """
    total_logs: int = Field(..., description="Total number of logs")
    active_incidents: int = Field(..., description="Number of active incidents")
    resolved_today: int = Field(..., description="Incidents resolved today")
    avg_resolution_time: str = Field(..., description="Average resolution time")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_logs": 15420,
                "active_incidents": 3,
                "resolved_today": 12,
                "avg_resolution_time": "4m 32s"
            }
        }


class DashboardResponse(BaseModel):
    """
    Schema for dashboard response.
    """
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Response message")
    data: Optional[dict] = Field(None, description="Dashboard data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Dashboard data retrieved",
                "data": {
                    "user": {
                        "id": "507f1f77bcf86cd799439011",
                        "name": "John Doe",
                        "email": "john@example.com"
                    },
                    "stats": {
                        "total_logs": 15420,
                        "active_incidents": 3,
                        "resolved_today": 12,
                        "avg_resolution_time": "4m 32s"
                    }
                }
            }
        }


# ============================================
# OAuth Schemas
# ============================================

class OAuthRedirectResponse(BaseModel):
    """
    Schema for OAuth redirect URL response.
    """
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Response message")
    data: dict = Field(..., description="OAuth redirect data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Redirect to OAuth provider",
                "data": {
                    "redirect_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
                }
            }
        }


class OAuthCallbackRequest(BaseModel):
    """
    Schema for OAuth callback request.
    """
    code: str = Field(..., description="Authorization code from OAuth provider")
    state: Optional[str] = Field(None, description="State parameter for CSRF protection")


# ============================================
# OTP Schemas
# ============================================

class OTPVerifyRequest(BaseModel):
    """Schema for OTP verification request."""
    email: EmailStr = Field(..., description="Email address that received the OTP")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v):
        return v.lower()


class OTPResendRequest(BaseModel):
    """Schema for requesting a new OTP."""
    email: EmailStr = Field(..., description="Email address to resend OTP to")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v):
        return v.lower()


# ============================================
# Onboarding Schema
# ============================================

class OnboardingRequest(BaseModel):
    """Schema for completing the user onboarding wizard."""
    company: Optional[str] = Field(None, max_length=100, description="Company or organization name")
    role: Optional[str] = Field(None, max_length=100, description="User's job role")
    team_size: Optional[str] = Field(None, max_length=20, description="Team size range")
    use_case: Optional[str] = Field(None, max_length=100, description="Primary use case")
    industry: Optional[str] = Field(None, max_length=100, description="Company industry")
    notification_preferences: Optional[list] = Field(default_factory=list, description="Alert channel preferences")
    project_name: Optional[str] = Field(None, max_length=100, description="First project name")
    project_description: Optional[str] = Field(None, max_length=500, description="First project description")
    invited_emails: Optional[list] = Field(default_factory=list, description="Team member emails to invite")
