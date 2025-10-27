#!/usr/bin/env python3
"""
Migration script: backup and remove trailing legacy tokens (or any extra fields) from
userInfo/*/Me.txt so each record contains exactly: username,hashed_password,role

Backup: creates a directory userInfo_backup_<timestamp>/ with copies of original files.

Usage: python3 tools/migrate_remove_legacy.py
"""
import os
import shutil
import time

ROOT = 'userInfo'
if __name__ == '__main__':
    if not os.path.isdir(ROOT):
        print('No userInfo/ directory found. Nothing to do.')
        raise SystemExit(0)

    ts = time.strftime('%Y%m%d_%H%M%S')
    backup_dir = f'userInfo_backup_{ts}'
    os.makedirs(backup_dir, exist_ok=True)

    modified = []
    for user in os.listdir(ROOT):
        userdir = os.path.join(ROOT, user)
        if not os.path.isdir(userdir):
            continue
        me_path = os.path.join(userdir, 'Me.txt')
        if not os.path.isfile(me_path):
            continue

        # Backup original
        relpath = os.path.join(user, 'Me.txt')
        bak_dest = os.path.join(backup_dir, relpath)
        os.makedirs(os.path.dirname(bak_dest), exist_ok=True)
        shutil.copy2(me_path, bak_dest)

        # Read and rewrite only the first three fields
        with open(me_path, 'r') as f:
            data = f.read().strip()
        fields = data.split(',') if data else []
        if len(fields) >= 3:
            new_fields = fields[:3]
            with open(me_path, 'w') as f:
                f.write(','.join(new_fields))
            modified.append(me_path)
        else:
            print(f'Skipping {me_path}: not enough fields')

    print(f'Backup of originals created at: {backup_dir}')
    if modified:
        print('Modified files:')
        for p in modified:
            print(' -', p)
    else:
        print('No files required modification.')
