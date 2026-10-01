"""Controlled Initial Admin & Police Provisioning Script for SafeZone.

Usage:
    python scripts/init_admin.py --admin-email admin@safezone.gov.in --admin-password <password> --admin-name "Super Admin"
"""

import argparse
import os
import sys

# Add project backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from sqlalchemy import select
from app.database.session import SessionLocal
from app.models.user import User, UserRole
from app.models.police import PoliceOfficer
from app.core.security import get_password_hash


def provision_admin(email: str, password: str, full_name: str, phone: str = None):
    db = SessionLocal()
    try:
        stmt = select(User).where(User.email == email)
        user = db.execute(stmt).scalar_one_or_none()
        if user:
            print(f"User with email '{email}' already exists. Updating role to ADMIN.")
            user.role = UserRole.ADMIN
            user.hashed_password = get_password_hash(password)
            user.full_name = full_name
            user.is_active = True
        else:
            print(f"Creating new ADMIN user: {email}")
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                phone_number=phone,
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
        db.commit()
        print(f"[SUCCESS] Admin account '{email}' provisioned successfully.")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to provision admin: {str(e)}")
        sys.exit(1)
    finally:
        db.close()


def provision_police_officer(email: str, password: str, full_name: str, badge_number: str, rank: str, station_name: str):
    db = SessionLocal()
    try:
        stmt = select(User).where(User.email == email)
        user = db.execute(stmt).scalar_one_or_none()
        if not user:
            print(f"Creating POLICE user: {email}")
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                full_name=full_name,
                role=UserRole.POLICE,
                is_active=True,
            )
            db.add(user)
            db.flush()

        stmt_officer = select(PoliceOfficer).where(PoliceOfficer.user_id == user.id)
        officer = db.execute(stmt_officer).scalar_one_or_none()
        if not officer:
            officer = PoliceOfficer(
                user_id=user.id,
                badge_number=badge_number,
                rank=rank,
                station_name=station_name,
                on_duty=True,
                is_available=True,
            )
            db.add(officer)
        db.commit()
        print(f"[SUCCESS] Police officer '{badge_number}' ({email}) provisioned successfully.")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to provision police officer: {str(e)}")
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="SafeZone Admin & Officer Provisioning Utility")
    parser.add_argument("--admin-email", default=os.getenv("INITIAL_ADMIN_EMAIL", "admin@safezone.gov.in"))
    parser.add_argument("--admin-password", default=os.getenv("INITIAL_ADMIN_PASSWORD", "AdminSecure2026!"))
    parser.add_argument("--admin-name", default="SafeZone Command Administrator")
    parser.add_argument("--admin-phone", default="9000000001")
    args = parser.parse_args()

    print("Provisioning SafeZone initial administrator...")
    provision_admin(
        email=args.admin_email,
        password=args.admin_password,
        full_name=args.admin_name,
        phone=args.admin_phone
    )


if __name__ == "__main__":
    main()
