"""
Response Handler Utility
Provides standardized response format for API endpoints.
"""

from typing import Any, Optional


def create_response(
    success: bool,
    message: str,
    data: Optional[Any] = None,
    token: Optional[str] = None
) -> dict:
    """
    Create a standardized API response.
    
    This function creates responses in a consistent format
    that can be easily consumed by Redux on the frontend.
    
    Args:
        success: Whether the operation was successful
        message: Human-readable message about the operation
        data: Optional data payload (user info, dashboard data, etc.)
        token: Optional JWT token (for auth responses)
    
    Returns:
        Dictionary with standardized response format:
        {
            "success": bool,
            "message": str,
            "data": Any | None,
            "token": str | None
        }
    
    Example:
        >>> create_response(
        ...     success=True,
        ...     message="Login successful",
        ...     data={"id": "123", "email": "user@example.com"},
        ...     token="eyJhbGc..."
        ... )
        {
            "success": True,
            "message": "Login successful",
            "data": {"id": "123", "email": "user@example.com"},
            "token": "eyJhbGc..."
        }
    """
    response = {
        "success": success,
        "message": message,
        "data": data,
        "token": token
    }
    
    return response


def create_error_response(
    message: str,
    errors: Optional[dict] = None
) -> dict:
    """
    Create a standardized error response.
    
    Args:
        message: Error message
        errors: Optional dictionary of field-specific errors
    
    Returns:
        Dictionary with error response format
    """
    response = {
        "success": False,
        "message": message,
        "data": None,
        "token": None
    }
    
    if errors:
        response["errors"] = errors
    
    return response


def create_pagination_response(
    success: bool,
    message: str,
    data: list,
    page: int,
    per_page: int,
    total: int
) -> dict:
    """
    Create a standardized paginated response.
    
    Args:
        success: Whether the operation was successful
        message: Human-readable message
        data: List of items
        page: Current page number
        per_page: Items per page
        total: Total number of items
    
    Returns:
        Dictionary with pagination metadata
    """
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    
    return {
        "success": success,
        "message": message,
        "data": data,
        "token": None,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }
