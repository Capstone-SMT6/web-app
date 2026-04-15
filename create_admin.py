import sys
import getpass
from sqlmodel import Session, select
from database import engine
from models import User
from routers.users import get_password_hash

def main():
    print("--- Web Admin Creation Tool ---")
    
    email = input("Enter admin email: ").strip()
    if not email:
        print("Error: Email cannot be empty.")
        sys.exit(1)
        
    username = input("Enter admin username: ").strip()
    if not username:
        print("Error: Username cannot be empty.")
        sys.exit(1)
        
    password = getpass.getpass("Enter admin password: ")
    if not password:
        print("Error: Password cannot be empty.")
        sys.exit(1)
        
    password_confirm = getpass.getpass("Confirm password: ")
    if password != password_confirm:
        print("Error: Passwords do not match.")
        sys.exit(1)

    with Session(engine) as session:
        # Check if user already exists
        existing_user = session.exec(select(User).where(User.email == email)).first()
        if existing_user:
            print(f"\nNotice: User with email '{email}' already exists.")
            make_admin = input("Do you want to elevate this existing user to admin? (y/n): ").strip().lower()
            if make_admin == 'y':
                existing_user.is_admin = True
                existing_user.password = get_password_hash(password)
                session.add(existing_user)
                session.commit()
                print(f"Success! Elevated '{email}' to admin status and updated the password.")
            else:
                print("Operation cancelled.")
            sys.exit(0)
            
        # Create a brand new admin user
        hashed_password = get_password_hash(password)
        new_admin = User(
            username=username,
            email=email,
            password=hashed_password,
            is_admin=True
        )
        session.add(new_admin)
        session.commit()
        print(f"\nSuccess! New admin user '{email}' has been securely created.")

if __name__ == "__main__":
    main()
