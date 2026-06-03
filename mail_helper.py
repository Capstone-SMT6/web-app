import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_otp_email(to_email: str, code: str, purpose: str):
    """
    Sends an OTP code via Gmail SMTP.
    """
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not smtp_email or not smtp_password:
        raise Exception("SMTP_EMAIL or SMTP_PASSWORD is not set in environment variables")

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

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = smtp_email
    message["To"] = to_email
    message.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, to_email, message.as_string())
    except Exception as e:
        print(f"Error sending email via SMTP: {e}")
        raise Exception("Failed to send verification email")
