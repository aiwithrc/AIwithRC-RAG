"""Admin CLI: `python -m app.cli <command>`.

Commands: create-user, reset-password (reindex and export arrive with the ingest pipeline).
"""

import argparse
import getpass
import sys

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal, init_engine, utcnow
from app.migrate import upgrade_to_head
from app.models import Session, User, Workspace
from app.security.passwords import MIN_PASSWORD_LENGTH, hash_password


def _prompt_password(given: str | None) -> str:
    pw = given or getpass.getpass("New password: ")
    if not given and getpass.getpass("Repeat password: ") != pw:
        sys.exit("Passwords don't match.")
    if len(pw) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password needs at least {MIN_PASSWORD_LENGTH} characters.")
    return pw


def create_user(args: argparse.Namespace) -> None:
    from app.routers.auth import bootstrap_workspace

    email = args.email.strip().lower()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            sys.exit(f"A user with email {email} already exists.")
        pw = _prompt_password(args.password)
        first = (db.scalar(select(func.count()).select_from(User)) or 0) == 0
        if first:
            ws, kb = bootstrap_workspace(db, args.name)
            default_kb = kb.id
        else:
            ws = db.scalars(select(Workspace).order_by(Workspace.created_at)).first()
            default_kb = None
        assert ws is not None
        role = "owner" if first or args.owner else "member"
        db.add(User(workspace_id=ws.id, email=email, name=args.name, password_hash=hash_password(pw),
                    role=role, default_kb_id=default_kb))
        db.commit()
    print(f"Created {role} {email}.")


def reset_password(args: argparse.Namespace) -> None:
    email = args.email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            sys.exit(f"No user with email {email}.")
        user.password_hash = hash_password(_prompt_password(args.password))
        # Sign out everywhere: whoever forgot the password may not be the only one who had it.
        for s in db.scalars(select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))):
            s.revoked_at = utcnow()
        db.commit()
    print(f"Password reset for {email}. All their sessions were signed out.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="AIwithRC-RAG admin commands")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create-user", help="Create a user (the first one becomes the owner)")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--password", help="Omit to be prompted")
    p.add_argument("--owner", action="store_true", help="Make this user an owner")
    p.set_defaults(fn=create_user)

    p = sub.add_parser("reset-password", help="Set a new password for a user")
    p.add_argument("--email", required=True)
    p.add_argument("--password", help="Omit to be prompted")
    p.set_defaults(fn=reset_password)

    args = parser.parse_args(argv)
    settings = get_settings()
    settings.ensure_dirs()
    upgrade_to_head(settings.db_url)
    init_engine(settings.db_url)
    args.fn(args)


if __name__ == "__main__":
    main()
