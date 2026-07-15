import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import httpx

load_dotenv()


def send_via_resend(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return False
    try:
        from_email = os.getenv("SMTP_FROM_EMAIL")
        # If no verified domain is set, use Resend's default onboarding domain
        if not from_email or "@gmail.com" in from_email.lower():
            from_email = "onboarding@resend.dev"

        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": to_email,
                "subject": subject,
                "html": html_content,
                "text": text_content,
            },
            timeout=10.0,
        )
        if response.status_code in (200, 201):
            print("Successfully sent email via Resend API.")
            return True
        else:
            print(f"Resend API returned status code {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"Failed to send email via Resend API: {e}")
        return False


def send_otp_email(to_email: str, code: str, purpose: str):
    """
    Sends an OTP code via Resend API or falls back to SMTP.
    """
    subject = "Verify your account" if purpose == "register" else "Reset your password"
    title_text = "Welcome to SmacoFit!" if purpose == "register" else "Reset Password Request"
    body_text = (
        "Please use the code below to complete your registration:"
        if purpose == "register"
        else "Please use the code below to reset your password:"
    )

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #4A90E2; text-align: center;">{title_text}</h2>
        <p style="font-size: 16px; color: #333;">{body_text}</p>
        <div style="text-align: center; margin: 30px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #4A90E2; background-color: #f5f5f5; padding: 10px 20px; border-radius: 4px;">{code}</span>
        </div>
        <p style="font-size: 14px; color: #777;">This code is valid for 10 minutes. If you did not request this email, please ignore it.</p>
    </div>
    """
    text_content = f"{body_text}\n\n{code}\n\nThis code is valid for 10 minutes."

    # 1. Try sending via Resend API first (highly reliable on cloud providers like Render)
    if os.getenv("RESEND_API_KEY"):
        if send_via_resend(to_email, subject, html_content, text_content):
            return

    # 2. Fallback to SMTP
    smtp_username = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not smtp_username or not smtp_password:
        raise Exception("SMTP_EMAIL or SMTP_PASSWORD is not set in environment variables")

    # Determine SMTP Host
    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        if "@gmail.com" in smtp_username.lower():
            smtp_host = "smtp.gmail.com"
        else:
            smtp_host = "localhost"

    # Determine SMTP Port (Default to 465 on Render/Cloud environments since 587 is blocked)
    smtp_port_str = os.getenv("SMTP_PORT")
    if smtp_port_str:
        try:
            smtp_port = int(smtp_port_str)
        except ValueError:
            smtp_port = 465
    else:
        smtp_port = 465

    smtp_from_email = os.getenv("SMTP_FROM_EMAIL", smtp_username)
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = smtp_from_email
    message["To"] = to_email

    message.attach(MIMEText(text_content, "plain"))
    message.attach(MIMEText(html_content, "html"))

    # Connect and send
    if smtp_port == 465:
        # Use SMTP_SSL for port 465
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10.0)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10.0)

    try:
        # STARTTLS is only needed for non-465 ports (like 587)
        if smtp_port != 465 and smtp_use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_from_email, [to_email], message.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass
