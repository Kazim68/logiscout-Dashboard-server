"""
Email Sender Utility
Sends emails via SMTP. Falls back to console logging when SMTP is not configured.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def _smtp_configured() -> bool:
    """Check whether SMTP credentials are present."""
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


def send_otp_email(to_email: str, otp_code: str, user_name: str = "there") -> bool:
    """
    Send an OTP verification email.

    If SMTP is not configured the OTP is printed to the console so the
    developer can still test the flow.

    Returns True on success, False on failure.
    """

    subject = f"LogiScout — Your verification code is {otp_code}"
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px">
        <h2 style="color:#18181b">Verify your email</h2>
        <p>Hi {user_name},</p>
        <p>Use the code below to complete your LogiScout sign-up. It expires in {settings.OTP_EXPIRE_MINUTES} minutes.</p>
        <div style="text-align:center;margin:24px 0">
            <span style="font-size:32px;letter-spacing:8px;font-weight:bold;color:#18181b">{otp_code}</span>
        </div>
        <p style="color:#71717a;font-size:13px">If you didn't request this, you can safely ignore this email.</p>
    </div>
    """

    if not _smtp_configured():
        # Dev fallback — just log it
        logger.info("OTP for %s: %s (SMTP not configured — printed to console)", to_email, otp_code)
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to_email], msg.as_string())

        logger.info("OTP email sent to %s", to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send OTP email to %s: %s", to_email, exc)
        # Still log OTP so dev can proceed
        logger.info("OTP for %s: %s (fallback after SMTP error)", to_email, otp_code)
        return False


def send_reset_code_email(to_email: str, code: str, user_name: str = "there") -> bool:
    """
    Send a password-reset code email.
    Falls back to console logging when SMTP is not configured.
    """
    subject = f"LogiScout — Your password reset code is {code}"
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px">
        <h2 style="color:#18181b">Reset your password</h2>
        <p>Hi {user_name},</p>
        <p>We received a request to reset your LogiScout password. Use the code below to set a new password. It expires in {settings.RESET_CODE_EXPIRE_MINUTES} minutes.</p>
        <div style="text-align:center;margin:24px 0">
            <span style="font-size:32px;letter-spacing:8px;font-weight:bold;color:#18181b">{code}</span>
        </div>
        <p style="color:#71717a;font-size:13px">If you didn't request this, you can safely ignore this email — your password will remain unchanged.</p>
    </div>
    """

    if not _smtp_configured():
        logger.info("RESET CODE for %s: %s (SMTP not configured — printed to console)", to_email, code)
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to_email], msg.as_string())

        logger.info("Reset code email sent to %s", to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send reset code email to %s: %s", to_email, exc)
        logger.info("RESET CODE for %s: %s (fallback after SMTP error)", to_email, code)
        return False


def send_collaborator_invite_email(
    to_email: str,
    inviter_name: str,
    project_name: str,
    role: str,
    accept_url: str,
) -> bool:
    """
    Send an invitation email to a user being added as a project collaborator.
    Falls back to console logging when SMTP is not configured.
    """
    role_label = "Editor" if role == "edit" else "Viewer"
    subject = f"LogiScout — {inviter_name} invited you to {project_name}"
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px">
        <h2 style="color:#18181b;margin-bottom:8px">You're invited to collaborate</h2>
        <p style="color:#52525b">Hi there,</p>
        <p style="color:#52525b">
            <strong>{inviter_name}</strong> has invited you to collaborate on the
            project <strong>{project_name}</strong> on LogiScout as a
            <strong>{role_label}</strong>.
        </p>
        <div style="text-align:center;margin:32px 0">
            <a href="{accept_url}"
               style="background:#18181b;color:#ffffff;padding:12px 28px;
                      border-radius:6px;text-decoration:none;font-weight:600;
                      display:inline-block">
                Accept Invitation
            </a>
        </div>
        <p style="color:#71717a;font-size:13px">
            Or copy and paste this link into your browser:<br/>
            <span style="word-break:break-all">{accept_url}</span>
        </p>
        <p style="color:#71717a;font-size:13px;margin-top:24px">
            You must be signed in to the LogiScout account associated with
            <strong>{to_email}</strong> to accept this invitation.
        </p>
    </div>
    """

    if not _smtp_configured():
        logger.info(
            "COLLABORATOR INVITE for %s -> %s (role=%s, project=%s) "
            "(SMTP not configured — printed to console). Accept URL: %s",
            to_email, inviter_name, role, project_name, accept_url,
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(msg["From"], [to_email], msg.as_string())

        logger.info("Collaborator invite email sent to %s", to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send collaborator invite email to %s: %s", to_email, exc)
        logger.info(
            "COLLABORATOR INVITE for %s (fallback after SMTP error). Accept URL: %s",
            to_email, accept_url,
        )
        return False
