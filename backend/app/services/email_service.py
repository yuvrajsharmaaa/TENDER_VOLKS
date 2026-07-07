import os
import smtplib
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Any
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

def send_email_with_attachment(to_email: str, subject: str, body: str, file_path: str) -> None:
    """
    Sends an email with the specified CSV file attachment.
    If SMTP variables are not configured in the environment, it logs the mock
    sending process to the console.
    """
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", "tender-alerts@volksenergies.com")
    
    # 1. Fallback to mock log if SMTP details are missing (perfect for local development MVP)
    if not smtp_host or not smtp_user or not smtp_password:
        logger.info(
            "email_mock_dispatch",
            extra={
                "custom_fields": {
                    "event": "email_mock_dispatch",
                    "recipient": to_email,
                    "subject": subject,
                    "attachment": file_path,
                    "reason": "SMTP host/credentials not configured. Mocking dispatch success."
                }
            }
        )
        return
        
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        
        msg.attach(MIMEText(body, "plain"))
        
        # 2. Attach File
        attachment_path = Path(file_path)
        if attachment_path.exists():
            part = MIMEBase("application", "octet-stream")
            with open(attachment_path, "rb") as attachment_file:
                part.set_payload(attachment_file.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={attachment_path.name}",
            )
            msg.attach(part)
        else:
            logger.warning(f"Attachment file not found at path: {file_path}. Sending email without attachment.")
            
        # 3. SMTP Session Dispatch
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            
        logger.info(
            "email_dispatch_success",
            extra={
                "custom_fields": {
                    "event": "email_dispatch_success",
                    "recipient": to_email,
                    "subject": subject,
                    "attachment": file_path
                }
            }
        )
        
    except Exception as e:
        logger.error(
            f"Failed to send SMTP email to {to_email}: {e}",
            exc_info=True,
            extra={
                "custom_fields": {
                    "event": "email_dispatch_failure",
                    "recipient": to_email,
                    "subject": subject
                }
            }
        )
        raise e

def send_tender_csv_email(recipient_email: str, csv_path: Any, tender_id: str) -> None:
    """Compatibility wrapper for legacy routes."""
    return send_email_with_attachment(recipient_email, f"Processed Tender - {tender_id}", "Please see attached.", str(csv_path))

