#!/usr/bin/env python3
"""
Small CLI to add a new user to the `storage/userInfo/` store using secure password hashing.

Usage:
  - Interactive: python3 tools/add_user.py
  - Non-interactive: python3 tools/add_user.py --username alice --password secret --role user

The script uses the same on-disk format as `userManager.UserManager.Signup`.
"""
import argparse
import getpass
import sys
import os

try:
    from werkzeug.security import generate_password_hash
except Exception as e:
    raise ImportError('Werkzeug is required for add_user. Install it with: pip install Werkzeug') from e




def add_user(username, password, role, email=None):
    userdir = os.path.join('storage/userInfo', username)
    if os.path.isdir(userdir):
        print(f"Error: user '{username}' already exists", file=sys.stderr)
        return 2

    os.makedirs(userdir, exist_ok=True)
    hashed = generate_password_hash(password)
    # Only write canonical fields: username, hashed_password, role
    fields = [username, hashed, role]
    if email:
        fields.append(email)
    path = os.path.join(userdir, 'Me.txt')
    with open(path, 'w') as f:
        f.write(','.join(fields))
    print(f"User '{username}' created successfully")
    return 0


def main():
    parser = argparse.ArgumentParser(description='Add a user with a hashed password')
    parser.add_argument('--username', '-u', help='username')
    parser.add_argument('--password', '-p', help='password (use with caution on command-line)')
    parser.add_argument('--role', '-r', default='user', help='role (default: user)')
    parser.add_argument('--email', '-e', help='email (optional)')
    args = parser.parse_args()

    if not args.username:
        args.username = input('Username: ').strip()
    if not args.password:
        args.password = getpass.getpass('Password: ')
    if not args.email:
        args.email = input('Email (optional): ').strip()

    if not args.username or not args.password:
        print('username and password are required', file=sys.stderr)
        return 1

    return add_user(args.username, args.password, args.role, args.email)


if __name__ == '__main__':
    raise SystemExit(main())
