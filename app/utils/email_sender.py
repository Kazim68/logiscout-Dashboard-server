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
