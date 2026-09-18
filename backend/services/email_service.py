"""Email service abstraction for OILTRACE.

Handles account activation invitations and password reset emails.
In production: delivers via SMTP using environment credentials.
In local development (or when SMTP_HOST is not set): prints secure, clearly marked
development URLs to the application console for rapid local verification.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from backend.core.config import settings
from backend.core.logging import logger


class EmailService:
    """Service for sending transactional emails (activation & password reset)."""

    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.frontend_base_url = settings.FRONTEND_BASE_URL.rstrip("/")
        self.expire_hours = settings.INVITATION_EXPIRE_HOURS
        self.reset_expire_hours = settings.RESET_PASSWORD_EXPIRE_HOURS
        self.dev_mode = settings.DEV_EMAIL_LOG or not bool(self.smtp_host)

    def _deliver_or_log(
        self,
        to_email: str,
        subject: str,
        text_content: str,
        html_content: str,
        dev_title: str,
        action_url: str,
    ) -> bool:
        """Send via SMTP in production or print development URL in local dev mode."""
        if not self.smtp_host:
            # Safe development mode fallback
            if settings.DEV_EMAIL_LOG:
                banner = "=" * 80
                print(
                    f"\n{banner}\n"
                    f"[DEVELOPMENT ONLY — DO NOT USE IN PRODUCTION]\n"
                    f"SIMULATED EMAIL: {dev_title}\n"
                    f"Recipient:  {to_email}\n"
                    f"Subject:    {subject}\n"
                    f"Action URL: {action_url}\n"
                    f"{banner}\n",
                    flush=True,
                )
                logger.info(f"[DEV_EMAIL] Generated {dev_title} for {to_email}")
            return True

        # Production SMTP delivery
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email

            part1 = MIMEText(text_content, "plain", "utf-8")
            part2 = MIMEText(html_content, "html", "utf-8")
            msg.attach(part1)
            msg.attach(part2)

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, [to_email], msg.as_string())

            logger.info(f"Successfully sent '{subject}' to {to_email} via SMTP")
            return True
        except Exception as exc:
            logger.error(f"Failed to deliver email to {to_email}: {exc}")
            # If SMTP fails in dev mode, log action URL as fallback
            if settings.DEV_EMAIL_LOG:
                logger.warning(f"[DEV_EMAIL FALLBACK] URL for {to_email}: {action_url}")
            return False

    def send_activation_email(
        self,
        to_email: str,
        full_name: str,
        employee_id: str,
        department: Optional[str],
        role: str,
        raw_token: str,
    ) -> bool:
        """Send an account activation email containing the single-use setup link."""
        activation_url = f"{self.frontend_base_url}/activate-account?token={raw_token}"
        dept_str = department or "Maritime Operations"
        subject = "Activate your OILTRACE account"

        text_content = (
            f"OILTRACE\n"
            f"Maritime Intelligence & Oil Spill Attribution System\n\n"
            f"Hello {full_name},\n\n"
            f"An OILTRACE account has been created for you.\n\n"
            f"Employee ID: {employee_id}\n"
            f"Department:  {dept_str}\n"
            f"Role:        {role}\n\n"
            f"To activate your account and create your password, open the link below:\n"
            f"{activation_url}\n\n"
            f"This activation link expires in {self.expire_hours} hours.\n"
            f"If you did not expect this email, please contact your Technology Administrator.\n"
        )

        html_content = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #070f1a; color: #f1f5f9; padding: 24px;">
  <div style="max-width: 580px; margin: 0 auto; background-color: #0b1526; border: 1px solid #1e293b; border-radius: 12px; padding: 32px;">
    <div style="font-family: monospace; font-size: 11px; letter-spacing: 2px; color: #06b6d4; text-transform: uppercase; margin-bottom: 8px;">
      OILTRACE &bull; MARITIME SURVEILLANCE AUTHORITY
    </div>
    <h1 style="font-size: 20px; font-weight: bold; color: #ffffff; margin-top: 0; margin-bottom: 16px;">
      Account Activation &amp; Access Authorization
    </h1>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.6;">
      Hello <strong>{full_name}</strong>,
    </p>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.6;">
      An official account has been provisioned for you on the OILTRACE Maritime Attribution System.
    </p>
    <div style="background-color: #0f1c33; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; margin: 20px 0; font-family: monospace; font-size: 13px;">
      <div style="margin-bottom: 6px;"><span style="color: #64748b;">Employee ID:</span> <strong style="color: #ffffff;">{employee_id}</strong></div>
      <div style="margin-bottom: 6px;"><span style="color: #64748b;">Department:</span> <span style="color: #cbd5e1;">{dept_str}</span></div>
      <div><span style="color: #64748b;">Assigned Role:</span> <span style="color: #38bdf8; font-weight: bold;">{role}</span></div>
    </div>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.6;">
      Click the button below to activate your account and securely set your personal password:
    </p>
    <div style="text-align: center; margin: 28px 0;">
      <a href="{activation_url}" style="background-color: #0284c7; color: #ffffff; padding: 12px 28px; font-family: monospace; font-size: 13px; font-weight: bold; text-decoration: none; border-radius: 6px; display: inline-block;">
        ACTIVATE OILTRACE ACCOUNT &rarr;
      </a>
    </div>
    <p style="font-size: 12px; color: #64748b; line-height: 1.5;">
      This activation link is single-use and will expire in <strong>{self.expire_hours} hours</strong>.<br/>
      If you did not expect this invitation, please contact your Technology Administrator immediately.
    </p>
  </div>
</body>
</html>"""

        return self._deliver_or_log(
            to_email=to_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            dev_title="ACCOUNT ACTIVATION",
            action_url=activation_url,
        )

    def send_password_reset_email(
        self,
        to_email: str,
        full_name: str,
        employee_id: str,
        raw_token: str,
    ) -> bool:
        """Send a password reset email containing the single-use reset link."""
        reset_url = f"{self.frontend_base_url}/reset-password?token={raw_token}"
        subject = "Reset your OILTRACE password"

        text_content = (
            f"OILTRACE\n"
            f"Maritime Intelligence & Oil Spill Attribution System\n\n"
            f"Hello {full_name} ({employee_id}),\n\n"
            f"A password reset request was initiated for your OILTRACE account.\n\n"
            f"To choose a new password, open the link below:\n"
            f"{reset_url}\n\n"
            f"This link expires in {self.reset_expire_hours} hours and can only be used once.\n"
            f"If you did not request this reset, please contact your Technology Administrator.\n"
        )

        html_content = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #070f1a; color: #f1f5f9; padding: 24px;">
  <div style="max-width: 580px; margin: 0 auto; background-color: #0b1526; border: 1px solid #1e293b; border-radius: 12px; padding: 32px;">
    <div style="font-family: monospace; font-size: 11px; letter-spacing: 2px; color: #f59e0b; text-transform: uppercase; margin-bottom: 8px;">
      OILTRACE &bull; SECURITY NOTIFICATION
    </div>
    <h1 style="font-size: 20px; font-weight: bold; color: #ffffff; margin-top: 0; margin-bottom: 16px;">
      Password Reset Request
    </h1>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.6;">
      Hello <strong>{full_name}</strong> (Employee ID: <code>{employee_id}</code>),
    </p>
    <p style="font-size: 14px; color: #cbd5e1; line-height: 1.6;">
      A password reset was requested for your account. Click the button below to set a new password:
    </p>
    <div style="text-align: center; margin: 28px 0;">
      <a href="{reset_url}" style="background-color: #d97706; color: #ffffff; padding: 12px 28px; font-family: monospace; font-size: 13px; font-weight: bold; text-decoration: none; border-radius: 6px; display: inline-block;">
        RESET OILTRACE PASSWORD &rarr;
      </a>
    </div>
    <p style="font-size: 12px; color: #64748b; line-height: 1.5;">
      This link expires in <strong>{self.reset_expire_hours} hours</strong> and is single-use.<br/>
      If you did not request this reset, report this immediately to your Technology Administrator.
    </p>
  </div>
</body>
</html>"""

        return self._deliver_or_log(
            to_email=to_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            dev_title="PASSWORD RESET",
            action_url=reset_url,
        )

    send_account_activation_email = send_activation_email


email_service = EmailService()


def send_account_activation_email(
    to_email: str,
    full_name: str,
    raw_token: str,
    employee_id: str = "",
    department: Optional[str] = None,
    role: str = "",
) -> bool:
    return email_service.send_activation_email(
        to_email=to_email,
        full_name=full_name,
        raw_token=raw_token,
        employee_id=employee_id,
        department=department,
        role=role,
    )


send_activation_email = send_account_activation_email


def send_password_reset_email(
    to_email: str,
    full_name: str,
    raw_token: str,
    employee_id: str = "",
) -> bool:
    return email_service.send_password_reset_email(
        to_email=to_email,
        full_name=full_name,
        raw_token=raw_token,
        employee_id=employee_id,
    )
