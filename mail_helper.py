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


def send_via_sendgrid(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        return False
    try:
        from_email = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_EMAIL", "panjirafi96@gmail.com"))
        response = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "personalizations": [
                    {
                        "to": [{"email": to_email}],
                        "subject": subject
                    }
                ],
                "from": {"email": from_email},
                "content": [
                    {"type": "text/plain", "value": text_content},
                    {"type": "text/html", "value": html_content}
                ]
            },
            timeout=10.0,
        )
        if response.status_code == 202:
            print("Successfully sent email via SendGrid API.")
            return True
        else:
            print(f"SendGrid API returned status code {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"Failed to send email via SendGrid API: {e}")
        return False


def send_via_brevo(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        return False
    try:
        from_email = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_EMAIL", "panjirafi96@gmail.com"))
        response = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "sender": {"email": from_email},
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
            },
            timeout=10.0,
        )
        if response.status_code in (200, 201):
            print("Successfully sent email via Brevo API.")
            return True
        else:
            print(f"Brevo API returned status code {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"Failed to send email via Brevo API: {e}")
        return False


def send_otp_email(to_email: str, code: str, purpose: str):
    """
    Sends an OTP code using verified API providers, falling back to SMTP.
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

    # 1. Try Resend API (Only works for account owner without verified domain)
    if os.getenv("RESEND_API_KEY"):
        if send_via_resend(to_email, subject, html_content, text_content):
            return

    # 2. Try SendGrid API (Works for all if Single Sender Verification is completed)
    if os.getenv("SENDGRID_API_KEY"):
        if send_via_sendgrid(to_email, subject, html_content, text_content):
            return

    # 3. Try Brevo API (Works for all if Single Sender Verification is completed)
    if os.getenv("BREVO_API_KEY"):
        if send_via_brevo(to_email, subject, html_content, text_content):
            return

    # 4. Fallback to SMTP (Will fail on Render Free Tier due to SMTP blocks)
    smtp_username = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not smtp_username or not smtp_password:
        raise Exception("SMTP_EMAIL or SMTP_PASSWORD is not set in environment variables")

    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        if "@gmail.com" in smtp_username.lower():
            smtp_host = "smtp.gmail.com"
        else:
            smtp_host = "localhost"

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

    if smtp_port == 465:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10.0)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10.0)

    try:
        if smtp_port != 465 and smtp_use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_from_email, [to_email], message.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass
