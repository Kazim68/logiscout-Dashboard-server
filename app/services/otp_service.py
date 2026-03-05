"""
OTP Service
Generates, stores, and verifies one-time passwords for email verification.
Pending signups are stored in a separate MongoDB collection with a TTL index.
"""

import random
import string
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.database import Database, PENDING_SIGNUPS_COLLECTION, USERS_COLLECTION
from app.core.security import hash_password, create_access_token, create_token_payload
from app.core.logging_config import get_logger
from app.models.user_model import user_helper
from app.utils.email_sender import send_otp_email

logger = get_logger(__name__)


class OTPService:
    """Handles OTP generation, storage, verification, and user activation."""

    @staticmethod
    def _generate_otp() -> str:
        """Generate a random numeric OTP of configured length."""
        return "".join(random.choices(string.digits, k=settings.OTP_LENGTH))

    @staticmethod
    async def _ensure_ttl_index():
        """Create a TTL index on `expires_at` so expired docs auto-delete."""
        collection = Database.get_collection(PENDING_SIGNUPS_COLLECTION)
        await collection.create_index("expires_at", expireAfterSeconds=0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    async def create_pending_signup(
        name: str,
        email: str,
        password: str,
        company: str | None = None,
    ) -> tuple[bool, str]:
        """
        Store signup data + OTP in `pending_signups`, then send the OTP email.

        Returns (success, message).
        """
        await OTPService._ensure_ttl_index()

        collection = Database.get_collection(PENDING_SIGNUPS_COLLECTION)
        users_col = Database.get_collection(USERS_COLLECTION)

        # Check if a verified user with this email already exists
        existing = await users_col.find_one({"email": email.lower()})
        if existing:
            logger.info("Pending signup rejected — email already registered: %s", email)
            return (False, "Email already registered")

        otp_code = OTPService._generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

        # Upsert so re-requesting an OTP refreshes the code
        await collection.update_one(
            {"email": email.lower()},
            {
                "$set": {
                    "name": name,
                    "email": email.lower(),
                    "password": hash_password(password),
                    "company": company,
                    "otp": otp_code,
                    "expires_at": expires_at,
                    "created_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

        # Send OTP
        send_otp_email(to_email=email, otp_code=otp_code, user_name=name)
        logger.info("OTP sent to %s (expires in %d min)", email, settings.OTP_EXPIRE_MINUTES)

        return (True, "Verification code sent to your email")

    @staticmethod
    async def verify_otp(email: str, otp: str):
        """
        Verify the OTP and, if valid, create the real user and return auth data.

        Returns (success, message, user_data | None, token | None).
        """
        collection = Database.get_collection(PENDING_SIGNUPS_COLLECTION)
        users_col = Database.get_collection(USERS_COLLECTION)

        pending = await collection.find_one({"email": email.lower()})

        if not pending:
            logger.info("OTP verify — no pending signup for: %s", email)
            return (False, "No pending verification for this email. Please sign up again.", None, None)

        # Check expiry
        if pending.get("expires_at") and pending["expires_at"] < datetime.utcnow():
            await collection.delete_one({"_id": pending["_id"]})
            logger.info("OTP expired for: %s", email)
            return (False, "Verification code has expired. Please sign up again.", None, None)

        # Check OTP match
        if pending.get("otp") != otp:
            logger.warning("Invalid OTP attempt for: %s", email)
            return (False, "Invalid verification code", None, None)

        # OTP valid — check if email already verified (race condition guard)
        existing = await users_col.find_one({"email": email.lower()})
        if existing:
            await collection.delete_one({"_id": pending["_id"]})
            return (False, "Email already registered", None, None)

        # Create the real user
        user_doc = {
            "name": pending["name"],
            "email": pending["email"],
            "password": pending["password"],  # already hashed
            "provider": "email",
            "provider_id": None,
            "created_at": datetime.utcnow(),
        }
        result = await users_col.insert_one(user_doc)
        created_user = await users_col.find_one({"_id": result.inserted_id})

        # Remove pending signup
        await collection.delete_one({"_id": pending["_id"]})

        # Generate JWT
        token_payload = create_token_payload(
            user_id=str(created_user["_id"]),
            email=created_user["email"],
            provider=created_user["provider"],
        )
        token = create_access_token(token_payload)

        user_data = user_helper(created_user)

        logger.info("OTP verified — user created: %s", email, extra={"email": email})
        return (True, "Email verified — account created", user_data, token)

    @staticmethod
    async def resend_otp(email: str):
        """
        Re-generate and resend the OTP for an existing pending signup.

        Returns (success, message).
        """
        collection = Database.get_collection(PENDING_SIGNUPS_COLLECTION)
        pending = await collection.find_one({"email": email.lower()})

        if not pending:
            logger.info("Resend OTP — no pending signup for: %s", email)
            return (False, "No pending verification for this email")

        otp_code = OTPService._generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

        await collection.update_one(
            {"_id": pending["_id"]},
            {"$set": {"otp": otp_code, "expires_at": expires_at}},
        )

        send_otp_email(
            to_email=pending["email"],
            otp_code=otp_code,
            user_name=pending.get("name", "there"),
        )

        logger.info("OTP resent to %s", email)
        return (True, "A new verification code has been sent")


otp_service = OTPService()
