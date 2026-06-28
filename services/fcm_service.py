import os
import json
import firebase_admin
from firebase_admin import credentials, messaging
from sqlmodel import Session, select
from models import User
from database import engine

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred_info = os.getenv("FIREBASE_SERVICE_ACCOUNT_INFO")
    cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if cred_info:
        try:
            info = json.loads(cred_info)
            cred = credentials.Certificate(info)
            firebase_admin.initialize_app(cred)
            print("Firebase Admin initialized via FIREBASE_SERVICE_ACCOUNT_INFO.")
        except Exception as e:
            print(f"Error initializing Firebase Admin via FIREBASE_SERVICE_ACCOUNT_INFO: {e}")
    elif cred_path and os.path.exists(cred_path):
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            print(f"Firebase Admin initialized via key file: {cred_path}")
        except Exception as e:
            print(f"Error initializing Firebase Admin via key file: {e}")
    else:
        try:
            firebase_admin.initialize_app()
            print("Firebase Admin initialized using application default credentials.")
        except Exception as e:
            print(f"WARNING: Firebase Admin SDK could not be initialized: {e}")


def send_push_notification(user_id: str, title: str, body: str, data: dict = None) -> bool:
    """
    Sends a push notification to a specific user via FCM.
    Returns True if successful, False otherwise.
    """
    # Simple comment to mark the start of database session
    with Session(engine) as session:
        user = session.exec(select(User).where(User.id == user_id)).first()
        if not user:
            print(f"User {user_id} not found.")
            return False
        if not user.fcmToken:
            print(f"Skipping notification: User {user_id} has no FCM token.")
            return False
        if not user.notificationEnabled:
            print(f"Skipping notification: User {user_id} has notifications disabled.")
            return False
        
        token = user.fcmToken

    try:
        # Stringify all values in data payload as FCM requires string values
        stringified_data = {}
        if data:
            for k, v in data.items():
                stringified_data[k] = str(v)

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=stringified_data,
            token=token,
        )
        response = messaging.send(message)
        print(f"Successfully sent message: {response}")
        return True
    except Exception as e:
        print(f"Error sending FCM message: {e}")
        return False
