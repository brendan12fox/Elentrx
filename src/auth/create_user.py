"""CLI to create dashboard users."""

from __future__ import annotations

import argparse
import getpass

from src.auth.users import create_user, init_auth_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an Elentrx dashboard user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", default=None, help="Login email / alert address")
    parser.add_argument("--alert-email", default=None, help="Alert recipient (defaults to --email)")
    parser.add_argument("--admin", action="store_true")
    args = parser.parse_args()

    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")

    init_auth_tables()
    user = create_user(
        username=args.username,
        password=password,
        email=args.email,
        alert_email=args.alert_email or args.email,
        is_admin=args.admin,
    )
    print(f"Created user {user.username} (id={user.id}, admin={user.is_admin})")


if __name__ == "__main__":
    main()
