"""
Project Service
Business logic for project CRUD and API token management.
"""

import secrets
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from bson import ObjectId

from app.core import database as db
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ProjectService:
    """
    Handles project and API token operations.
    """

    TOKEN_PREFIX = "lgs_"
    TOKEN_INDEX_NAME = "token_unique_non_null"
    _token_index_ready = False

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    @staticmethod
    async def create_project(
        name: str,
        owner_id: str,
        description: Optional[str] = None,
        language: str = "python",
    ) -> Dict[str, Any]:
        """Create a new project for a user."""
        doc = {
            "name": name.strip(),
            "description": (description or "").strip(),
            "language": language,
            "owner_id": owner_id,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        result = await db.Projects.insert_one(doc)
        created = await db.Projects.find_one({"_id": result.inserted_id})
        logger.info("Project created: %s (owner=%s)", name, owner_id, extra={"project_id": str(result.inserted_id), "user_id": owner_id})
        return created

    @staticmethod
    async def list_projects(owner_id: str) -> List[Dict[str, Any]]:
        """List all projects owned by a user."""
        cursor = db.Projects.find({"owner_id": owner_id}).sort("created_at", -1)
        projects = await cursor.to_list(length=100)

        # Attach token counts
        for proj in projects:
            pid = str(proj["_id"])
            count = await db.APITokens.count_documents({"project_id": pid})
            proj["token_count"] = count

        return projects

    @staticmethod
    async def get_project(project_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
        """Get a single project by ID, scoped to the owner."""
        try:
            project = await db.Projects.find_one({
                "_id": ObjectId(project_id),
                "owner_id": owner_id,
            })
            if project:
                project["token_count"] = await db.APITokens.count_documents(
                    {"project_id": str(project["_id"])}
                )
            return project
        except Exception:
            logger.warning("get_project failed: project_id=%s, owner=%s", project_id, owner_id)
            return None

    @staticmethod
    async def update_project(
        project_id: str,
        owner_id: str,
        update_data: dict,
    ) -> Optional[Dict[str, Any]]:
        """Update a project's fields."""
        update_data["updated_at"] = datetime.now(timezone.utc)
        # Remove None values
        clean = {k: v for k, v in update_data.items() if v is not None}

        try:
            result = await db.Projects.find_one_and_update(
                {"_id": ObjectId(project_id), "owner_id": owner_id},
                {"$set": clean},
                return_document=True,
            )
            if result:
                logger.info("Project updated: %s", project_id, extra={"project_id": project_id})
            return result
        except Exception:
            logger.warning("update_project failed: project_id=%s", project_id)
            return None

    @staticmethod
    async def delete_project(project_id: str, owner_id: str) -> bool:
        """Delete a project and all its tokens."""
        try:
            result = await db.Projects.delete_one({
                "_id": ObjectId(project_id),
                "owner_id": owner_id,
            })
            if result.deleted_count > 0:
                # Cascade: remove all tokens for this project
                await db.APITokens.delete_many({"project_id": project_id})
                logger.info("Project deleted (cascaded tokens): %s", project_id, extra={"project_id": project_id})
                return True
            return False
        except Exception:
            logger.warning("delete_project failed: project_id=%s", project_id)
            return False

    # ------------------------------------------------------------------
    # API Tokens
    # ------------------------------------------------------------------

    @classmethod
    def _generate_token(cls) -> str:
        """Generate a simple unique token in the format lgs_<random>."""
        random_part = secrets.token_urlsafe(32)  # ~43 chars, URL-safe
        return f"{cls.TOKEN_PREFIX}{random_part}"

    @classmethod
    async def _ensure_token_index(cls) -> None:
<<<<<<< Updated upstream
        """
        Ensure a unique index for non-null token values.

        Legacy collections may contain old documents with token=None.
        A plain unique index on `token` fails in that case with duplicate
        key `{ token: null }`. To keep backwards compatibility, we enforce
        uniqueness only for string token values.
        """
        if cls._token_index_ready:
            return

        desired_key = {"token": 1}
        desired_partial = {"token": {"$type": "string"}}

        # Inspect existing indexes and migrate incompatible token indexes.
        indexes = await db.APITokens.list_indexes().to_list(length=None)
        for idx in indexes:
            key = dict(idx.get("key", {}))
            if key != desired_key:
                continue

            is_desired = (
                idx.get("name") == cls.TOKEN_INDEX_NAME
                and idx.get("unique") is True
                and idx.get("partialFilterExpression") == desired_partial
            )
            if is_desired:
                cls._token_index_ready = True
                return

            # Drop old/conflicting index definitions (e.g. token_1)
            # before creating the desired migration-safe index.
            try:
                await db.APITokens.drop_index(idx["name"])
                logger.info("Dropped legacy token index: %s", idx["name"])
            except Exception as exc:
                logger.warning("Failed dropping index %s: %s", idx.get("name"), exc)

        await db.APITokens.create_index(
            [("token", 1)],
            name=cls.TOKEN_INDEX_NAME,
            unique=True,
            partialFilterExpression=desired_partial,
        )
        cls._token_index_ready = True
        logger.info("Ensured token index: %s", cls.TOKEN_INDEX_NAME)
=======
        """Create a unique index on the `token` field for O(1) lookups.

        Uses a partial filter so legacy documents missing the `token` field
        (e.g. older `token_hash`-only rows) don't collide as `{token: null}`.
        If a stale full-unique `token_1` index exists from a prior schema,
        drop and recreate it with the partial filter.
        """
        desired_partial = {"token": {"$type": "string"}}
        try:
            existing = await db.APITokens.index_information()
        except Exception:
            existing = {}

        token_idx = existing.get("token_1")
        if token_idx is not None:
            if token_idx.get("partialFilterExpression") == desired_partial and token_idx.get("unique"):
                return
            try:
                await db.APITokens.drop_index("token_1")
            except Exception:
                logger.warning("Failed to drop stale token_1 index", exc_info=True)

        await db.APITokens.create_index(
            "token",
            unique=True,
            partialFilterExpression=desired_partial,
        )
>>>>>>> Stashed changes

    @classmethod
    async def create_token(
        cls,
        project_id: str,
        owner_id: str,
        label: str = "Default",
    ) -> Tuple[Dict[str, Any], str]:
        """
        Generate a new API token for a project.

        Returns:
            (token_document, plain_text_token)
            The plain_text_token is returned ONLY at creation time.
        """
        # Verify project ownership
        project = await cls.get_project(project_id, owner_id)
        if not project:
            raise ValueError("Project not found")

        # Enforce one-active-token-per-project
        active_token = await db.APITokens.find_one({
            "project_id": project_id,
            "is_active": {"$ne": False},
        })
        if active_token:
            raise ValueError(
                "An active token already exists for this project. "
                "Disable the current token before generating a new one."
            )

        # Ensure unique index exists on the `token` field
        await cls._ensure_token_index()

        plain_token = cls._generate_token()

        # Prefix for masked display, suffix for identification
        prefix = plain_token[:8]   # "lgs_Ab3x"
        suffix = plain_token[-4:]  # last 4 chars

        doc = {
            "project_id": project_id,
            "owner_id": owner_id,
            "label": label.strip(),
            "token": plain_token,
            "token_prefix": prefix,
            "token_suffix": suffix,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "last_used_at": None,
        }

        result = await db.APITokens.insert_one(doc)
        created = await db.APITokens.find_one({"_id": result.inserted_id})

        logger.info("API token created for project %s (label=%s)", project_id, label, extra={"project_id": project_id, "token_id": str(result.inserted_id)})
        return created, plain_token

    @staticmethod
    async def list_tokens(project_id: str, owner_id: str) -> List[Dict[str, Any]]:
        """List all tokens for a project (masked)."""
        cursor = db.APITokens.find({
            "project_id": project_id,
            "owner_id": owner_id,
        }).sort("created_at", -1)
        return await cursor.to_list(length=50)

    @staticmethod
    async def disable_token(token_id: str, owner_id: str) -> bool:
        """Disable an active API token (sets is_active=False)."""
        try:
            # Match tokens that are active OR pre-existing tokens that lack the field entirely
            result = await db.APITokens.update_one(
                {
                    "_id": ObjectId(token_id),
                    "owner_id": owner_id,
                    "is_active": {"$ne": False},
                },
                {"$set": {"is_active": False}},
            )
            if result.modified_count > 0:
                logger.info("Token disabled: %s", token_id, extra={"token_id": token_id})
                return True
            return False
        except Exception:
            logger.warning("disable_token failed: token_id=%s", token_id)
            return False

    @staticmethod
    async def delete_token(token_id: str, owner_id: str) -> bool:
        """Revoke/delete an API token."""
        try:
            result = await db.APITokens.delete_one({
                "_id": ObjectId(token_id),
                "owner_id": owner_id,
            })
            if result.deleted_count > 0:
                logger.info("Token revoked: %s", token_id, extra={"token_id": token_id})
            return result.deleted_count > 0
        except Exception:
            logger.warning("delete_token failed: token_id=%s", token_id)
            return False

    @classmethod
    async def validate_token(cls, plain_token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a plain-text API token (used by log ingestion).

        Performs a single indexed lookup on the `token` field.
        No hashing or parsing required — O(1) with the unique index.

        Returns the token doc (including project_id) if valid and active,
        None otherwise.
        """
        if not plain_token or not plain_token.startswith(cls.TOKEN_PREFIX):
            logger.warning("validate_token: malformed token (bad prefix)")
            return None

        # Single indexed query — no hashing, no parsing
        token_doc = await db.APITokens.find_one({
            "token": plain_token,
            "is_active": {"$ne": False},
        })

        if token_doc:
            # Update last_used_at (fire-and-forget is fine for analytics)
            await db.APITokens.update_one(
                {"_id": token_doc["_id"]},
                {"$set": {"last_used_at": datetime.now(timezone.utc)}},
            )
            logger.debug("Token validated for project %s", token_doc.get("project_id"))

        return token_doc


project_service = ProjectService()
