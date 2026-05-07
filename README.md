# LogiScout Backend API

A professional, modular FastAPI backend for the LogiScout AI-powered incident resolution platform.

## Features

- 🔐 **JWT Authentication** - Secure token-based authentication
- 📧 **Email/Password Auth** - Traditional signup and login
- 🔑 **Google OAuth 2.0** - Sign in with Google
- 🐙 **GitHub OAuth 2.0** - Sign in with GitHub
- 📊 **Protected Dashboard API** - Authenticated endpoints
- 🗄️ **MongoDB** - Async database with Motor driver
- 📝 **Redux-Ready Responses** - Consistent response format

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── __init__.py
│   │
│   ├── core/                   # Core configuration and utilities
│   │   ├── config.py           # Environment settings
│   │   ├── security.py         # JWT and password utilities
│   │   ├── database.py         # MongoDB connection
│   │   └── __init__.py
│   │
│   ├── models/                 # Database models
│   │   ├── user_model.py       # User document model
│   │   └── __init__.py
│   │
│   ├── schemas/                # Pydantic schemas
│   │   ├── user_schema.py      # Request/response schemas
│   │   └── __init__.py
│   │
│   ├── services/               # Business logic layer
│   │   ├── auth_service.py     # Authentication logic
│   │   ├── google_oauth_service.py
│   │   ├── github_oauth_service.py
│   │   └── __init__.py
│   │
│   ├── routes/                 # API endpoints
│   │   ├── auth_routes.py      # Email auth endpoints
│   │   ├── google_oauth_routes.py
│   │   ├── github_oauth_routes.py
│   │   ├── dashboard_routes.py # Protected endpoints
│   │   └── __init__.py
│   │
│   ├── utils/                  # Utility functions
│   │   ├── response_handler.py # Standardized responses
│   │   └── __init__.py
│   │
│   └── dependencies/           # FastAPI dependencies
│       ├── auth_dependency.py  # Token validation
│       └── __init__.py
│
├── .env                        # Environment variables
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Quick Start

### Prerequisites

- Python 3.10+
- MongoDB (local or Atlas)
- Google OAuth credentials (for Google login)
- GitHub OAuth credentials (for GitHub login)

### Installation

1. **Navigate to backend directory**
   ```bash
   cd backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   
   Edit the `.env` file with your credentials:
   ```env
   MONGO_URI=mongodb://localhost:27017
   DATABASE_NAME=logiscout
   JWT_SECRET_KEY=your-secret-key
   GOOGLE_CLIENT_ID=your-google-client-id
   GOOGLE_CLIENT_SECRET=your-google-client-secret
   GITHUB_CLIENT_ID=your-github-client-id
   GITHUB_CLIENT_SECRET=your-github-client-secret
   ```

5. **Run the server**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

6. **Access the API**
   - API: http://localhost:8000
   - Swagger Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/signup` | Register new user |
| POST | `/api/auth/login` | User login |
| GET | `/api/auth/google` | Initiate Google OAuth |
| GET | `/api/auth/google/callback` | Google OAuth callback |
| GET | `/api/auth/github` | Initiate GitHub OAuth |
| GET | `/api/auth/github/callback` | GitHub OAuth callback |

### Protected Routes

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | Get dashboard data |
| GET | `/api/profile` | Get user profile |
| GET | `/api/health` | Health check |

## Response Format

All API responses follow this structure for easy Redux integration:

```json
{
  "success": true,
  "message": "Operation completed",
  "data": {
    "user": {...},
    "stats": {...}
  },
  "token": "eyJhbGciOiJIUzI1NiIs..."
}
```

## Authentication Flow

### Email/Password

1. **Signup**: POST `/api/auth/signup`
   ```json
   {
     "name": "John Doe",
     "email": "john@example.com",
     "password": "securePassword123"
   }
   ```

2. **Login**: POST `/api/auth/login`
   ```json
   {
     "email": "john@example.com",
     "password": "securePassword123"
   }
   ```

### OAuth Flow

1. Frontend calls `GET /api/auth/google` or `GET /api/auth/github`
2. Response contains `redirect_url`
3. Frontend redirects user to OAuth provider
4. User authorizes the app
5. Provider redirects to callback URL
6. Backend creates/logs in user and redirects to frontend with token

## JWT Token

Include the token in requests to protected endpoints:

```
Authorization: Bearer <your_jwt_token>
```

Token payload:
```json
{
  "user_id": "507f1f77bcf86cd799439011",
  "email": "user@example.com",
  "provider": "email",
  "exp": 1704067200
}
```

## OAuth Setup

### Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable Google+ API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URI: `http://localhost:8000/api/auth/google/callback`
6. Copy Client ID and Client Secret to `.env`

### GitHub OAuth

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Create a new OAuth App
3. Set Homepage URL: `https://logiscout-frontend.vercel.app`
4. Set Authorization callback URL: `http://localhost:8000/api/auth/github/callback`
5. Copy Client ID and Client Secret to `.env`

## MongoDB Schema

### User Document

```json
{
  "_id": "ObjectId",
  "name": "John Doe",
  "email": "john@example.com",
  "password": "hashed_password (nullable for OAuth)",
  "provider": "email | google | github",
  "provider_id": "external_provider_user_id",
  "created_at": "2024-01-15T10:30:00Z"
}
```

## Development

### Running in development mode

```bash
uvicorn app.main:app --reload --port 8000
```

### Running with debugger

```bash
python -m app.main
```

## Security

- Passwords are hashed using bcrypt
- JWT tokens expire after 1 day (configurable)
- CORS is configured for frontend integration
- OAuth state parameter for CSRF protection
- Sensitive data excluded from responses

## Frontend Integration

The frontend (Next.js) expects:
- Backend at `http://localhost:8000`
- Responses in the standard format
- JWT token for authentication
- OAuth redirects to `/dashboard?token=...`

## License

MIT License
