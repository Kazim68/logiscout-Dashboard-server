"""
Chat Encryption Utility
Provides symmetric encryption/decryption for stored chat payloads.
"""

from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from hashlib import sha256
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ChatEncryption:
    """
    Encrypts and decrypts chat payloads using a deterministic Fernet key.

    If CHAT_ENCRYPTION_KEY is configured it is used as the seed material.
    Otherwise, the JWT secret is used as a fallback so the service works
    without extra environment setup.
    """

    def __init__(self) -> None:
        self._fernet = Fernet(self._build_key())

    @staticmethod
    def _build_key() -> bytes:
        secret_seed = settings.CHAT_ENCRYPTION_KEY or settings.JWT_SECRET_KEY
        return urlsafe_b64encode(sha256(secret_seed.encode("utf-8")).digest())

    def encrypt_payload(self, payload: Any) -> str:
        serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        return self._fernet.encrypt(serialized.encode("utf-8")).decode("utf-8")

    def decrypt_payload(self, encrypted_payload: str) -> Any:
        try:
            decrypted = self._fernet.decrypt(encrypted_payload.encode("utf-8"))
        except InvalidToken as exc:
            logger.error("Failed to decrypt chat payload")
            raise ValueError("Invalid encrypted chat payload") from exc

        return json.loads(decrypted.decode("utf-8"))


chat_encryption = ChatEncryption()
