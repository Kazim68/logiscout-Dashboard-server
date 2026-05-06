"""
Collaborator Service
Business logic for inviting, listing, updating, and removing project
collaborators.

Access model:
- Each project has exactly one owner (the creator).
- Owners can invite registered LogiScout users by email as collaborators.
- A collaborator has a role of "read" or "edit".
- Only the owner can manage the collaborator list and roles.
"""

import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId

from app.core import database as db
from app.core.config import settings
from app.core.logging_config import get_logger
from app.utils.email_sender import send_collaborator_invite_email

logger = get_logger(__name__)


def _collaborator_helper(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Format a collaborator document for API responses."""
    return {
        "id": str(doc["_id"]),
        "project_id": doc.get("project_id", ""),
        "user_id": doc.get("user_id", ""),
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "role": doc.get("role", "read"),
        "status": doc.get("status", "pending"),
        "created_at": doc.get("created_at", datetime.now(timezone.utc)).isoformat(),
        "accepted_at": (
            doc["accepted_at"].isoformat() if doc.get("accepted_at") else None
        ),
    }


class CollaboratorService:
    """Manages project collaborators."""

    # ------------------------------------------------------------------
    # Invite
    # ------------------------------------------------------------------

    @staticmethod
    async def invite_collaborator(
        project_id: str,
        owner_id: str,
        owner_name: str,
        email: str,
        role: str,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Invite a registered user to collaborate on a project.

        Rules:
        - Caller must be the project owner.
        - Invited user must already have a LogiScout account.
        - Cannot invite the owner themselves.
        - Cannot invite someone already invited (pending or active).
        """
        email = email.strip().lower()

        # 1. Verify project exists and is owned by caller
        try:
            project = await db.Projects.find_one({
                "_id": ObjectId(project_id),
                "owner_id": owner_id,
            })
        except Exception:
            return False, "Project not found", None
        if not project:
            return False, "Project not found", None

        # 2. Look up the invitee in users collection (case-insensitive).
        # Anchored exact match — escaped to prevent regex injection from email.
        safe_email = re.escape(email)
        invitee = await db.Users.find_one({
            "email": {"$regex": f"^{safe_email}$", "$options": "i"}
        })
        if not invitee:
            return (
                False,
                "No LogiScout account is registered with that email. Ask them to sign up first.",
                None,
            )

        invitee_id = str(invitee["_id"])
        if invitee_id == owner_id:
            return False, "You can't invite yourself — you're already the project owner.", None

        # 3. If a previous invite was removed/rejected, allow re-inviting by
        # cleaning up the stale doc. Active collaborators are still blocked.
        existing = await db.Collaborators.find_one({
            "project_id": project_id,
            "user_id": invitee_id,
        })
        if existing:
            existing_status = existing.get("status", "active")
            if existing_status == "active":
                return (
                    False,
                    f"{invitee.get('name') or email} is already a collaborator on this project.",
                    None,
                )
            # Pending invite already exists — resend by replacing the old token.
            new_token = secrets.token_urlsafe(32)
            await db.Collaborators.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "role": role,
                    "invite_token": new_token,
                    "created_at": datetime.now(timezone.utc),
                }},
            )
            refreshed = await db.Collaborators.find_one({"_id": existing["_id"]})
            accept_url = (
                f"{settings.FRONTEND_URL.rstrip('/')}/dashboard?accept_invite={new_token}"
            )
            try:
                send_collaborator_invite_email(
                    to_email=email,
                    inviter_name=owner_name or "A LogiScout user",
                    project_name=project.get("name", "a project"),
                    role=role,
                    accept_url=accept_url,
                )
            except Exception as exc:
                logger.warning("Failed re-sending invite email to %s: %s", email, exc)
            logger.info(
                "Collaborator invite re-sent: project=%s invitee=%s role=%s",
                project_id, invitee_id, role,
            )
            return True, "Invitation re-sent", _collaborator_helper(refreshed)

        # 4. Create collaborator doc
        invite_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        doc = {
            "project_id": project_id,
            "user_id": invitee_id,
            "email": email,
            "name": invitee.get("name", ""),
            "role": role,
            "invited_by": owner_id,
            "status": "pending",
            "invite_token": invite_token,
            "created_at": now,
            "accepted_at": None,
        }
        result = await db.Collaborators.insert_one(doc)
        created = await db.Collaborators.find_one({"_id": result.inserted_id})

        # 5. Send invite email (non-blocking failure — log but still succeed)
        accept_url = (
            f"{settings.FRONTEND_URL.rstrip('/')}/dashboard?accept_invite={invite_token}"
        )
        try:
            send_collaborator_invite_email(
                to_email=email,
                inviter_name=owner_name or "A LogiScout user",
                project_name=project.get("name", "a project"),
                role=role,
                accept_url=accept_url,
            )
        except Exception as exc:
            logger.warning("Failed sending invite email to %s: %s", email, exc)

        logger.info(
            "Collaborator invited: project=%s invitee=%s role=%s",
            project_id, invitee_id, role,
            extra={"project_id": project_id, "user_id": invitee_id},
        )
        return True, "Invitation sent", _collaborator_helper(created)

    # ------------------------------------------------------------------
    # Accept invite
    # ------------------------------------------------------------------

    @staticmethod
    async def accept_invite(invite_token: str, user_id: str) -> Tuple[bool, str]:
        """
        Accept a pending collaborator invite.
        The authenticated user_id must match the invitee on the doc.
        """
        doc = await db.Collaborators.find_one({
            "invite_token": invite_token,
            "status": "pending",
        })
        if not doc:
            return False, "Invite not found or already accepted"

        if doc.get("user_id") != user_id:
            logger.warning(
                "Invite token mismatch: token belongs to %s but accepted by %s",
                doc.get("user_id"), user_id,
            )
            return False, "This invite was sent to a different account"

        await db.Collaborators.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "status": "active",
                "accepted_at": datetime.now(timezone.utc),
                "invite_token": None,
            }},
        )
        logger.info(
            "Invite accepted: project=%s user=%s",
            doc.get("project_id"), user_id,
            extra={"project_id": doc.get("project_id"), "user_id": user_id},
        )
        return True, "Invite accepted"

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    @staticmethod
    async def list_collaborators(
        project_id: str,
        owner_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """List all collaborators for a project. Owner-only."""
        try:
            project = await db.Projects.find_one({
                "_id": ObjectId(project_id),
                "owner_id": owner_id,
            })
        except Exception:
            return None
        if not project:
            return None

        cursor = db.Collaborators.find({"project_id": project_id}).sort("created_at", -1)
        docs = await cursor.to_list(length=200)
        return [_collaborator_helper(d) for d in docs]

    # ------------------------------------------------------------------
    # Update role
    # ------------------------------------------------------------------

    @staticmethod
    async def update_role(
        project_id: str,
        collaborator_id: str,
        owner_id: str,
        new_role: str,
    ) -> Tuple[bool, str]:
        """Change a collaborator's role. Owner-only."""
        try:
            project = await db.Projects.find_one({
                "_id": ObjectId(project_id),
                "owner_id": owner_id,
            })
        except Exception:
            return False, "Project not found"
        if not project:
            return False, "Project not found"

        try:
            result = await db.Collaborators.update_one(
                {"_id": ObjectId(collaborator_id), "project_id": project_id},
                {"$set": {"role": new_role}},
            )
        except Exception:
            return False, "Collaborator not found"

        if result.matched_count == 0:
            return False, "Collaborator not found"

        logger.info(
            "Collaborator role updated: project=%s collab=%s role=%s",
            project_id, collaborator_id, new_role,
        )
        return True, "Role updated"

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    @staticmethod
    async def remove_collaborator(
        project_id: str,
        collaborator_id: str,
        owner_id: str,
    ) -> Tuple[bool, str]:
        """Remove a collaborator from a project. Owner-only."""
        try:
            project = await db.Projects.find_one({
                "_id": ObjectId(project_id),
                "owner_id": owner_id,
            })
        except Exception:
            return False, "Project not found"
        if not project:
            return False, "Project not found"

        try:
            result = await db.Collaborators.delete_one({
                "_id": ObjectId(collaborator_id),
                "project_id": project_id,
            })
        except Exception:
            return False, "Collaborator not found"

        if result.deleted_count == 0:
            return False, "Collaborator not found"

        logger.info(
            "Collaborator removed: project=%s collab=%s",
            project_id, collaborator_id,
        )
        return True, "Collaborator removed"

    # ------------------------------------------------------------------
    # Invitations addressed to the current user
    # ------------------------------------------------------------------

    @staticmethod
    async def list_my_invitations(user_id: str) -> List[Dict[str, Any]]:
        """
        Return all pending invitations addressed to this user, enriched with
        project name and inviter name for display in the notification dropdown.
        """
        cursor = db.Collaborators.find({
            "user_id": user_id,
            "status": "pending",
        }).sort("created_at", -1)
        invites = await cursor.to_list(length=50)

        enriched: List[Dict[str, Any]] = []
        for inv in invites:
            # Resolve project name
            project_name = ""
            try:
                proj = await db.Projects.find_one({"_id": ObjectId(inv["project_id"])})
                if proj:
                    project_name = proj.get("name", "")
            except Exception:
                pass

            # Resolve inviter name
            inviter_name = ""
            inviter_email = ""
            inviter_id = inv.get("invited_by")
            if inviter_id:
                try:
                    inviter = await db.Users.find_one({"_id": ObjectId(inviter_id)})
                    if inviter:
                        inviter_name = inviter.get("name", "")
                        inviter_email = inviter.get("email", "")
                except Exception:
                    pass

            enriched.append({
                "id": str(inv["_id"]),
                "project_id": inv.get("project_id", ""),
                "project_name": project_name,
                "role": inv.get("role", "read"),
                "inviter_name": inviter_name or inviter_email or "A teammate",
                "inviter_email": inviter_email,
                "created_at": inv.get("created_at", datetime.now(timezone.utc)).isoformat(),
            })
        return enriched

    @staticmethod
    async def respond_to_invitation(
        invitation_id: str,
        user_id: str,
        action: str,
    ) -> Tuple[bool, str]:
        """
        Accept or decline a pending invitation by its document id.
        action ∈ {"accept", "decline"}.
        """
        try:
            doc = await db.Collaborators.find_one({"_id": ObjectId(invitation_id)})
        except Exception:
            return False, "Invitation not found"
        if not doc:
            return False, "Invitation not found"
        if doc.get("user_id") != user_id:
            return False, "This invitation belongs to a different account"
        if doc.get("status") != "pending":
            return False, "This invitation is no longer pending"

        if action == "accept":
            await db.Collaborators.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "status": "active",
                    "accepted_at": datetime.now(timezone.utc),
                    "invite_token": None,
                }},
            )
            logger.info(
                "Invitation accepted from dashboard: project=%s user=%s",
                doc.get("project_id"), user_id,
            )
            return True, "Invitation accepted"
        if action == "decline":
            await db.Collaborators.delete_one({"_id": doc["_id"]})
            logger.info(
                "Invitation declined: project=%s user=%s",
                doc.get("project_id"), user_id,
            )
            return True, "Invitation declined"
        return False, "Invalid action"

    # ------------------------------------------------------------------
    # Access checks (used by other services)
    # ------------------------------------------------------------------

    @staticmethod
    async def get_user_role(project_id: str, user_id: str) -> Optional[str]:
        """
        Return the user's role on a project: "owner", "edit", "read", or None.
        Used by project_service to allow collaborator access.
        """
        try:
            project = await db.Projects.find_one({"_id": ObjectId(project_id)})
        except Exception:
            return None
        if not project:
            return None

        if project.get("owner_id") == user_id:
            return "owner"

        collab = await db.Collaborators.find_one({
            "project_id": project_id,
            "user_id": user_id,
            "status": "active",
        })
        if collab:
            return collab.get("role", "read")
        return None


collaborator_service = CollaboratorService()
