import os
import hashlib
import logging
import shutil
try:
    # Force use of Werkzeug for password helpers. If Werkzeug is not available,
    # fail fast with an informative error so the environment can be configured.
    from werkzeug.security import generate_password_hash, check_password_hash
except Exception as e:
    raise ImportError('Werkzeug is required for password hashing. Install it with: pip install Werkzeug') from e


class User:
    def __init__(self, userName, password, role, email=None):
        self.userName = userName
        # we don't expose the password; keep empty for returned objects
        self.password = password
        self.role = role
        self.email = email
        self.avatar = None
        if self.email:
            logging.debug(f"User '{userName}' has email: '{self.email}'")
            email_hash = hashlib.md5(self.email.lower().strip().encode('utf-8')).hexdigest()
            self.avatar = f"https://www.gravatar.com/avatar/{email_hash}?d=mp&s=40"
            logging.debug(f"Generated avatar URL for '{userName}': {self.avatar}")
        else:
            logging.debug(f"User '{userName}' has no email, so no avatar will be used.")


class UserManager:
    """
    UserManager stores user records under `storage/userInfo/<username>/Me.txt`.
    File format (CSV-like): username,hashed_password,role,<legacy-token?>

    Behavior changes:
    - Passwords are stored hashed using werkzeug.security.generate_password_hash
    - Auth supports migrating existing plaintext-stored passwords automatically
      (on successful plaintext auth the password file will be re-written with a hash).
    """

    def _user_file(self, userName):
        return os.path.join('storage/userInfo', userName, 'Me.txt')

    def _read_user(self, userName):
        """Return list of fields or None if not found."""
        path = self._user_file(userName)
        if os.path.isfile(path):
            with open(path, 'r') as f:
                data = f.read()
            # keep all fields - split only on commas
            fields = data.split(',')
            return fields
        return None

    def _write_user(self, userName, fields):
        """Write fields (list) as a comma-separated line to the user file."""
        user_dir = os.path.join('storage/userInfo', userName)
        if not os.path.isdir(user_dir):
            os.makedirs(user_dir, exist_ok=True)
        path = self._user_file(userName)
        with open(path, 'w') as f:
            f.write(','.join(fields))

    def Auth(self, userName, password):
        """
        Authenticate userName with password.
        Returns {'user': User or None, 'message': str}

        If the stored password is plaintext (legacy), the function will accept it
        and replace it with a hashed password (migration on first successful login).
        """
        logging.debug(f"Attempting to authenticate user: {userName}")
        userData = self._read_user(userName)
        if not userData:
            logging.warning(f"Auth failed for '{userName}': user not found.")
            return {'user': None, 'message': 'Incorrect Username or Password'}

        # Ensure we have at least username,password,role
        if len(userData) < 3:
            logging.error(f"Corrupt user data for '{userName}': {userData}")
            return {'user': None, 'message': 'Corrupt user data'}

        stored_password = userData[1]
        role = userData[2]
        email = userData[3] if len(userData) > 3 else None
        logging.debug(f"Read user data for '{userName}': role='{role}', email='{email}'")

        # Try standard hash check first
        try:
            if check_password_hash(stored_password, password):
                user = User(userName, '', role, email)
                logging.info(f"User '{userName}' authenticated successfully via hash.")
                return {'user': user, 'message': 'User found'}
        except Exception as e:
            logging.warning(f"Hash check failed for '{userName}', falling back. Error: {e}")
            pass

        # Fallback: support legacy plaintext password (migration path)
        if stored_password == password:
            # Migrate: replace stored password with a hash
            new_hash = generate_password_hash(password)
            # preserve existing trailing fields if any
            # Write an updated record with only the canonical fields
            new_fields = [userData[0], new_hash, userData[2]]
            if len(userData) > 3:
                new_fields.append(userData[3])
            self._write_user(userName, new_fields)
            
            user = User(userName, '', role, email)
            logging.info(f"User '{userName}' authenticated via plaintext password (migrated to hash).")
            return {'user': user, 'message': 'User found (password migrated)'}

        logging.warning(f"Authentication failed for '{userName}': password incorrect.")
        return {'user': None, 'message': 'Incorrect Username or Password'}

    def Signup(self, userName, password, role, email=None):
        """Create a new user and store the hashed password."""
        # Avoid overwriting existing users
        if os.path.isdir(os.path.join('storage/userInfo', userName)):
            raise FileExistsError('User already exists')

        hashed = generate_password_hash(password)
        # Only write canonical fields: username, hashed_password, role
        fields = [userName, hashed, role]
        if email:
            fields.append(email)
        self._write_user(userName, fields)

    def list_users(self):
        """Returns a list of all users."""
        users = []
        user_info_dir = 'storage/userInfo'
        if not os.path.isdir(user_info_dir):
            return users
        
        for username in os.listdir(user_info_dir):
            user_dir = os.path.join(user_info_dir, username)
            if os.path.isdir(user_dir):
                userData = self._read_user(username)
                if userData and len(userData) >= 3:
                    role = userData[2]
                    email = userData[3] if len(userData) > 3 else None
                    users.append(User(username, '', role, email))
        return sorted(users, key=lambda u: u.userName)

    def update_user(self, username, role, email):
        """Updates a user's role and email, preventing modification of owners."""
        logging.debug(f"Attempting to update user '{username}' with role='{role}' and email='{email}'")
        userData = self.getDetails(username)
        if not userData:
            raise FileNotFoundError('User not found')

        # Prevent owners from being modified
        if userData[2] == 'owner':
            raise PermissionError("Owner accounts cannot be modified.")
        
        # [username, password_hash, role, email]
        new_fields = [userData[0], userData[1], role]
        if len(userData) > 3:
            new_fields.append(email)
        elif email:
             new_fields.append(email)

        self._write_user(username, new_fields)
        logging.info(f"Successfully updated user '{username}'")

    def delete_user(self, username):
        """Deletes a user, preventing deletion of owners."""
        userData = self.getDetails(username)
        if userData and userData[2] == 'owner':
            raise PermissionError("Owner accounts cannot be deleted.")

        user_dir = os.path.join('storage/userInfo', username)
        if os.path.isdir(user_dir):
            shutil.rmtree(user_dir)
            logging.info(f"Deleted user '{username}'")
            return True
        logging.warning(f"Attempted to delete non-existent user '{username}'")
        return False

    def getDetails(self, userName):
        """Return the user data fields or False if not present."""
        fields = self._read_user(userName)
        return fields if fields is not None else False

    def changePassword(self, uname, new_pwd):
        """Change a user's password: store the hashed new password."""
        userData = self.getDetails(uname)
        if not userData:
            raise FileNotFoundError('User not found')
        new_hash = generate_password_hash(new_pwd)
        new_fields = [userData[0], new_hash, userData[2]]
        if len(userData) > 3:
            new_fields.append(userData[3])
        self._write_user(uname, new_fields)

    def changeEmail(self, uname, new_email):
        """Change a user's email."""
        logging.debug(f"Attempting to change email for user '{uname}' to '{new_email}'")
        userData = self.getDetails(uname)
        if not userData:
            raise FileNotFoundError('User not found')
        
        new_fields = [userData[0], userData[1], userData[2]]
        if len(userData) > 3:
            new_fields[3] = new_email
        else:
            new_fields.append(new_email)
        self._write_user(uname, new_fields)
        logging.info(f"Successfully changed email for user '{uname}'")