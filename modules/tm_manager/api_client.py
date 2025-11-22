import requests
import hmac
import hashlib
import logging
import email.utils
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class VexTmApiClient:
    def __init__(self, client_id, client_secret, api_key, base_url):
        self.client_id = client_id
        self.client_secret = client_secret
        # CRITICAL: Strip whitespace from API Key. 
        # Copy-paste often adds a hidden space at the end which breaks the hash.
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip('/') # Ensure no double slashes later
        self.token = None
        self.token_expires = datetime.now(timezone.utc)

    def get_auth_token(self):
        """
        Retrieves an OAuth2 token from the VEX TM authentication server.
        """
        if self.token and self.token_expires > datetime.now(timezone.utc):
            logger.debug("Reusing existing auth token.")
            return self.token

        logger.info("Requesting new auth token for VEX TM API.")
        url = "https://auth.vextm.dwabtech.com/oauth2/token"
        
        try:
            response = requests.post(
                url,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                timeout=10
            )
            response.raise_for_status()
            token_data = response.json()
            self.token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
            logger.info("Successfully obtained new VEX TM auth token.")
            return self.token
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obtaining VEX TM auth token: {e}")
            self.token = None
            return None

    def create_signature(self, http_verb, uri_path_query, host, date_str):
        """
        Creates the HMAC-SHA256 signature for a request.
        Spec:
        StringToSign = HTTP Verb + "\n" +
                       URI Path and Query string + "\n" +
                       "token:" + {BearerToken} + "\n" +
                       "host:" + Host header value + "\n" +
                       "x-tm-date:" + {Date} + "\n"
        Signature = Hex(HMAC-SHA256({APIKey}, {StringToSign}))
        """
        if not self.token:
            self.get_auth_token()
        if not self.token:
            raise Exception("Cannot create signature without an auth token.")

        # Note: The spec explicitly requires a trailing newline after the date.
        string_to_sign = (
            f"{http_verb.upper()}\n"
            f"{uri_path_query}\n"
            f"token:{self.token}\n"
            f"host:{host}\n"
            f"x-tm-date:{date_str}\n"
        )
        
        # logger.debug(f"String to sign:\n{repr(string_to_sign)}")
        
        # Encode key and message to UTF-8 to be safe
        signature = hmac.new(
            self.api_key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest() # DOCS: Use Hex, not Base64
        
        return signature

    def get(self, endpoint):
        """
        Makes an authenticated and signed GET request to the VEX TM API.
        """
        self.get_auth_token()
        if not self.token:
            logger.error(f"Cannot make GET request to {endpoint}, no auth token.")
            return None

        # Handle endpoint formatting
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"
            
        url = f"{self.base_url}{endpoint}"
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        
        # Reconstruct Path + Query
        # If url is /api/teams?division=1, we need strictly that part.
        uri_path_query = parsed_url.path
        if parsed_url.query:
            uri_path_query += f"?{parsed_url.query}"
        
        # Generate RFC1123 Date using email.utils to prevent locale issues (e.g., 'Sat' vs 'Sam')
        date_str = email.utils.formatdate(usegmt=True)
        
        try:
            signature = self.create_signature("GET", uri_path_query, host, date_str)
        except Exception as e:
            logger.error(f"Failed to create signature: {e}")
            return None

        headers = {
            "Host": host,
            "Authorization": f"Bearer {self.token}",
            "x-tm-date": date_str,
            "x-tm-signature": signature
        }

        try:
            # logger.info(f"Making GET request to {url}")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error during GET request to {url}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                 logger.error(f"Response content: {e.response.text}")
            return None