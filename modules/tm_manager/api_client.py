import requests
import hmac
import hashlib
import base64
import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class VexTmApiClient:
    def __init__(self, client_id, client_secret, api_key, base_url):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_key = api_key
        self.base_url = base_url
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
                data={"grant_type": "client_credentials"}
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

    def create_signature(self, http_verb, uri_path, host, date):
        """
        Creates the HMAC-SHA256 signature for a request.
        """
        if not self.token:
            self.get_auth_token()
        if not self.token:
            raise Exception("Cannot create signature without an auth token.")

        string_to_sign = (
            f"{http_verb.upper()}\n"
            f"{uri_path}\n"
            f"token:{self.token}\n"
            f"host:{host}\n"
            f"x-tm-date:{date}\n"
        )
        signature = hmac.new(
            self.api_key.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    def get(self, endpoint):
        """
        Makes an authenticated and signed GET request to the VEX TM API.
        """
        self.get_auth_token()
        if not self.token:
            logger.error(f"Cannot make GET request to {endpoint}, no auth token.")
            return None

        url = f"{self.base_url}{endpoint}"
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        uri_path = parsed_url.path
        
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature = self.create_signature("GET", uri_path, host, date)

        headers = {
            "Host": host,
            "Authorization": f"Bearer {self.token}",
            "x-tm-date": date,
            "x-tm-signature": signature
        }

        try:
            logger.info(f"Making GET request to {url}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error during GET request to {url}: {e}")
            return None
