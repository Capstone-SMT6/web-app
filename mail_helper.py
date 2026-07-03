import os
import resend


def send_otp_email(to_email: str, code: str, purpose: str):
    """
    Sends an OTP code via Resend API.
    """
    resend.api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM_EMAIL", "SmacoFit <onboarding@resend.dev>")

    if not resend.api_key:
        raise Exception("RESEND_API_KEY is not set in environment variables")

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

    params: resend.Emails.SendParams = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_content,
    }

    resend.Emails.send(params)
