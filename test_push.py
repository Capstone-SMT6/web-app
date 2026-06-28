import os
from sqlmodel import Session, select
from models import User
from database import engine
from services.fcm_service import send_push_notification

def main():
    print("Starting push notification test script...")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.fcmToken != None)).first()
        if user:
            print(f"Found user '{user.username}' (ID: {user.id}) with registered FCM token.")
            success = send_push_notification(
                user_id=user.id,
                title="Halo! 💪",
                body="Ini adalah push notification pertama dari server!"
            )
            if success:
                print("Notification successfully sent!")
            else:
                print("Failed to send notification. Check logs above.")
        else:
            print("\n[WARNING]: Belum ada user dengan FCM token di database.")
            print("Silakan jalankan aplikasi Flutter, log in, dan biarkan aplikasi mengupload token ke server terlebih dahulu.")

if __name__ == "__main__":
    main()
