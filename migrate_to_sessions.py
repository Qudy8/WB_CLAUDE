"""
Migration script to add session support to existing data.

This script:
1. Creates a Session for each existing user
2. Creates SessionMember with role='owner' for each user
3. Sets active_session_id for each user
4. Migrates all user data to their session (sets session_id)
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import Flask app and models
from app import app
from models import (
    db, User, Session, SessionMember, ProductGroup, Order, ProductionItem,
    CISLabel, Box, Delivery, PrintTask, Inventory, FinishedGoodsStock, Defect
)

def migrate_to_sessions():
    """Migrate existing user data to session-based structure."""
    with app.app_context():
        print("Starting migration to session-based structure...")
        print("-" * 50)

        # Get all existing users
        users = User.query.all()
        print(f"Found {len(users)} users to migrate")

        for user in users:
            print(f"\nMigrating user: {user.email}")

            # Check if user already has a session
            existing_session = Session.query.filter_by(owner_id=user.id).first()
            if existing_session:
                print(f"  ✓ User already has session: {existing_session.name}")
                session = existing_session
            else:
                # Create a new session for this user
                session = Session(
                    name=f"Workspace {user.name or user.email}",
                    access_code=Session.generate_access_code(),
                    owner_id=user.id
                )
                db.session.add(session)
                db.session.flush()  # Get session.id
                print(f"  ✓ Created session: {session.name} (code: {session.access_code})")

            # Check if user already is a member
            existing_member = SessionMember.query.filter_by(
                session_id=session.id,
                user_id=user.id
            ).first()

            if not existing_member:
                # Create SessionMember with owner role
                session_member = SessionMember(
                    session_id=session.id,
                    user_id=user.id,
                    role='owner'
                )
                db.session.add(session_member)
                print(f"  ✓ Created session membership (owner)")

            # Set active session for user
            if not user.active_session_id:
                user.active_session_id = session.id
                print(f"  ✓ Set active session")

            # Migrate all user's data to this session
            models_to_migrate = [
                ('ProductGroup', ProductGroup),
                ('Order', Order),
                ('ProductionItem', ProductionItem),
                ('CISLabel', CISLabel),
                ('Box', Box),
                ('Delivery', Delivery),
                ('PrintTask', PrintTask),
                ('Inventory', Inventory),
                ('FinishedGoodsStock', FinishedGoodsStock),
                ('Defect', Defect),
            ]

            for model_name, model_class in models_to_migrate:
                # Find records that need migration (session_id is NULL)
                records = model_class.query.filter_by(
                    user_id=user.id
                ).filter(
                    model_class.session_id == None
                ).all()

                if records:
                    for record in records:
                        record.session_id = session.id
                    print(f"  ✓ Migrated {len(records)} {model_name} records")

        # Commit all changes
        try:
            db.session.commit()
            print("\n" + "=" * 50)
            print("✓ Migration completed successfully!")
            print("=" * 50)
        except Exception as e:
            db.session.rollback()
            print(f"\n✗ Error during migration: {e}")
            print("Migration rolled back.")
            sys.exit(1)


if __name__ == '__main__':
    migrate_to_sessions()
