import requests
import hmac
import hashlib
import base64
import logging
import time
import json
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class VexTmApiClient:
    def __init__(self, client_id, client_secret, api_key, base_url):
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_key = api_key.strip() if api_key else api_key
        self.base_url = base_url
        self.token = None
        self.token_expires = datetime.now(timezone.utc)
        self.last_auth_attempt = 0
        self.auth_retry_delay = 1  # Start with 1 second delay for rate limiting
        self.token_cache_file = ".auth_token"
        
        # Load cached token if available
        self._load_cached_token()

    def _load_cached_token(self):
        """Load auth token from cache file if it exists and is still valid."""
        try:
            if os.path.exists(self.token_cache_file):
                with open(self.token_cache_file, 'r') as f:
                    cache_data = json.load(f)
                    self.token = cache_data.get('token')
                    expires_str = cache_data.get('expires')
                    if expires_str and self.token:
                        self.token_expires = datetime.fromisoformat(expires_str)
                        if self.token_expires > datetime.now(timezone.utc):
                            logger.info("Loaded cached auth token from file.")
                            return True
                    logger.debug("Cached token is expired.")
        except (json.JSONDecodeError, IOError, ValueError) as e:
            logger.debug(f"Could not load cached token: {e}")
        
        self.token = None
        return False

    def _save_cached_token(self):
        """Save auth token to cache file."""
        try:
            cache_data = {
                'token': self.token,
                'expires': self.token_expires.isoformat() if self.token_expires else None
            }
            with open(self.token_cache_file, 'w') as f:
                json.dump(cache_data, f)
            logger.debug("Cached auth token to file.")
        except IOError as e:
            logger.warning(f"Could not save auth token cache: {e}")

    def get_auth_token(self):
        """
        Retrieves an OAuth2 token from the VEX TM authentication server.
        Includes rate limit handling, retry logic, and file-based caching.
        """
        if self.token and self.token_expires > datetime.now(timezone.utc):
            logger.debug("Reusing existing auth token.")
            return self.token

        # Rate limit our auth requests to avoid 429 errors
        time_since_last = time.time() - self.last_auth_attempt
        if time_since_last < self.auth_retry_delay:
            wait_time = self.auth_retry_delay - time_since_last
            logger.debug(f"Rate limiting auth request, waiting {wait_time:.1f}s")
            time.sleep(wait_time)

        logger.info("Requesting new auth token for VEX TM API.")
        url = "https://auth.vextm.dwabtech.com/oauth2/token"
        
        try:
            response = requests.post(
                url,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                timeout=10
            )
            self.last_auth_attempt = time.time()
            
            if response.status_code == 429:
                # Handle rate limiting - increase retry delay
                retry_after = int(response.headers.get('Retry-After', 5))
                self.auth_retry_delay = min(retry_after, 30)  # Cap at 30 seconds
                logger.warning(f"Auth rate limited, will retry after {self.auth_retry_delay}s")
                return None
            
            response.raise_for_status()
            token_data = response.json()
            self.token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
            self.auth_retry_delay = 1  # Reset delay on success
            
            # Save token to cache file
            self._save_cached_token()
            
            logger.info("Successfully obtained new VEX TM auth token.")
            return self.token
        except requests.exceptions.RequestException as e:
            logger.error(f"Error obtaining VEX TM auth token: {e}")
            self.token = None
            return None

    def create_signature(self, http_verb, uri_path, host, date):
        """
        Creates the HMAC-SHA256 signature for a request.
        According to VEX TM API spec:
        StringToSign = HTTP Verb + "\n" +
                       URI Path and Query string + "\n" +
                       "token:" + {BearerToken} + "\n" +
                       "host:" + Host header value + "\n" +
                       "x-tm-date:" + {Date} + "\n"
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
        
        logger.debug(f"String to sign:\n{repr(string_to_sign)}")
        logger.debug(f"API key length: {len(self.api_key)}")
        logger.debug(f"API key (first 10 chars): {self.api_key[:10]}...")
        
        signature = hmac.new(
            self.api_key.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).hexdigest()
        
        logger.debug(f"Generated HMAC-SHA256 signature: {signature}")
        return signature

    def get(self, endpoint):
        """
        Makes an authenticated and signed GET request to the VEX TM API.
        Includes retry logic for rate limiting.
        """
        self.get_auth_token()
        if not self.token:
            logger.error(f"Cannot make GET request to {endpoint}, no auth token.")
            return None

        url = f"{self.base_url}{endpoint}"
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        uri_path = parsed_url.path
        
        # Retry logic for rate limiting
        max_retries = 3
        for attempt in range(max_retries):
            date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
            signature = self.create_signature("GET", uri_path, host, date)

            headers = {
                "Host": host,
                "Authorization": f"Bearer {self.token}",
                "x-tm-date": date,
                "x-tm-signature": signature
            }

            try:
                logger.info(f"Making GET request to {url} (attempt {attempt + 1}/{max_retries})")
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = int(response.headers.get('Retry-After', 5))
                    if attempt < max_retries - 1:
                        logger.warning(f"Rate limited on {endpoint}, retrying after {retry_after}s")
                        time.sleep(retry_after)
                        continue
                    else:
                        logger.error(f"Rate limited on {endpoint}, max retries exceeded")
                        return None
                
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error during GET request to {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return None
