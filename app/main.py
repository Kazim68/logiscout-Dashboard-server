"""
LogiScout API - Main Application Entry Point
A professional FastAPI backend for the LogiScout incident management platform.
"""

from contextlib import asynccontextmanager
import time
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.config import settings
from app.core.database import Database, init_collections
from app.core.logging_config import setup_logging, get_logger
from app.routes import (
    auth_router,
    google_oauth_router,
    github_oauth_router,
    dashboard_router,
    project_router,
)
from app.utils.response_handler import create_error_response

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup: Initialise logging and connect to database
    setup_logging()
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await Database.connect()
    init_collections()

    yield
    
    # Shutdown: Disconnect from database
    await Database.disconnect()
    logger.info("%s shutdown complete", settings.APP_NAME)


# Create FastAPI application instance
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    ## LogiScout API
    
    AI-Powered Incident Resolution Platform for Modern Engineering Teams.
    
    ### Features
    - 🔐 JWT Authentication
    - 🔑 Google OAuth 2.0
    - 🐙 GitHub OAuth 2.0
    - 📊 Dashboard API
    - 📝 Structured responses for Redux integration
    
    ### Authentication
    Most endpoints require a JWT token. Include it in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)


# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# ============================================
# Request Logging Middleware
# ============================================

request_logger = get_logger("http")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming HTTP request and its response time."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)

    request_logger.info(
        "%s %s → %s (%sms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "ip": request.client.host if request.client else None,
        },
    )
    return response


# ============================================
# Exception Handlers
# ============================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    """
    Handle Pydantic validation errors.
    Returns errors in the standard response format.
    """
    errors = {}
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"][1:])  # Skip 'body'
        errors[field] = error["msg"]
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=create_error_response(
            message="Validation error",
            errors=errors
        )
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception
):
    """
    Handle unexpected exceptions.
    Returns a generic error in production, detailed error in debug mode.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    if settings.DEBUG:
        message = str(exc)
    else:
        message = "An unexpected error occurred"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(message=message)
    )


# ============================================
# Include Routers
# ============================================

# Auth routes (signup, login)
app.include_router(auth_router)

# Google OAuth routes
app.include_router(google_oauth_router)

# GitHub OAuth routes
app.include_router(github_oauth_router)

# Dashboard routes (protected)
app.include_router(dashboard_router)

# Project & Token Management routes (protected)
app.include_router(project_router)


# ============================================
# Root Endpoints
# ============================================

@app.get(
    "/",
    tags=["Root"],
    summary="API Root",
    description="Welcome endpoint with API information."
)
async def root():
    """
    Root endpoint.
    Returns basic API information.
    """
    return {
        "success": True,
        "message": f"Welcome to {settings.APP_NAME}",
        "data": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "redoc": "/redoc"
        },
        "token": None
    }


@app.get(
    "/api",
    tags=["Root"],
    summary="API Info",
    description="API version and available endpoints."
)
async def api_info():
    """
    API information endpoint.
    Lists available endpoints and their purposes.
    """
    return {
        "success": True,
        "message": "LogiScout API",
        "data": {
            "version": settings.APP_VERSION,
            "endpoints": {
                "auth": {
                    "signup": "POST /api/auth/signup",
                    "login": "POST /api/auth/login",
                    "google": "GET /api/auth/google",
                    "github": "GET /api/auth/github"
                },
                "protected": {
                    "dashboard": "GET /api/dashboard",
                    "profile": "GET /api/profile"
                },
                "utility": {
                    "health": "GET /api/health"
                }
            }
        },
        "token": None
    }


# ============================================
# Development Server
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
