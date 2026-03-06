"""
setup_passwords.py
Run this ONCE after creating the database to set proper bcrypt passwords.
Usage: python setup_passwords.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.all_models import User
from app.core.security import hash_password


def setup():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("❌ No users found. Run database/schema.sql first.")
            return

        # Set all users password to 'admin123' for development
        default_passwords = {
            'admin':  'admin123',
            'ravi':   'admin123',
            'suresh': 'admin123',
            'metalm': 'admin123',
            'priya':  'admin123',
            'qcraj':  'admin123',
        }

        for user in users:
            pwd = default_passwords.get(user.username, 'admin123')
            user.password_hash = hash_password(pwd)
            print(f"  ✅ Set password for user: {user.username}")

        db.commit()
        print("\n✅ All passwords updated!")
        print("\nLogin credentials:")
        print("━" * 40)
        for uname, pwd in default_passwords.items():
            print(f"  Username: {uname:10} | Password: {pwd}")
        print("━" * 40)
        print("\n🚀 Start server: uvicorn app.main:app --reload --port 8000")
        print("🌐 Open browser: http://localhost:8000")
        print("📖 API docs:     http://localhost:8000/docs")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    setup()
