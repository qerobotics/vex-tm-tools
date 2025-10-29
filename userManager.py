import os
try:
    # Force use of Werkzeug for password helpers. If Werkzeug is not available,
    # fail fast with an informative error so the environment can be configured.
    from werkzeug.security import generate_password_hash, check_password_hash
except Exception as e:
    raise ImportError('Werkzeug is required for password hashing. Install it with: pip install Werkzeug') from e


class User:
    def __init__(self, userName, password, role):
        self.userName = userName
        # we don't expose the password; keep empty for returned objects
        self.password = password
        self.role = role


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
        userData = self._read_user(userName)
        if not userData:
            return {'user': None, 'message': 'Incorrect Username or Password'}

        # Ensure we have at least username,password,role
        if len(userData) < 3:
            return {'user': None, 'message': 'Corrupt user data'}

        stored = userData[1]

        # Try standard hash check first
        try:
            if check_password_hash(stored, password):
                user = User(userData[0], '', userData[2])
                return {'user': user, 'message': 'User found'}
        except Exception:
            # check_password_hash can throw if stored is malformed; fall back
            pass

        # Fallback: support legacy plaintext password (migration path)
        if stored == password:
            # Migrate: replace stored password with a hash
            new_hash = generate_password_hash(password)
            # preserve existing trailing fields if any
            # Write an updated record with only the canonical fields
            new_fields = [userData[0], new_hash, userData[2]]
            self._write_user(userName, new_fields)
            user = User(userData[0], '', userData[2])
            return {'user': user, 'message': 'User found (password migrated)'}

        return {'user': None, 'message': 'Incorrect Username or Password'}

    def Signup(self, userName, password, role):
        """Create a new user and store the hashed password."""
        # Avoid overwriting existing users
        if os.path.isdir(os.path.join('storage/userInfo', userName)):
            raise FileExistsError('User already exists')

        hashed = generate_password_hash(password)
        # Only write canonical fields: username, hashed_password, role
        fields = [userName, hashed, role]
        self._write_user(userName, fields)

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
        self._write_user(uname, new_fields)