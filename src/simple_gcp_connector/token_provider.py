from typing import List, Optional
import google.auth
from google.auth.transport import requests
from google.auth.credentials import TokenState, Credentials

# Scope for Cloud SQL IAM login
CLOUDSQL_IAM_LOGIN_SCOPE = [
    "https://www.googleapis.com/auth/sqlservice.login",
    "https://www.googleapis.com/auth/sqlservice.admin",
]


class GoogleCloudTokenProvider:
    """
    A helper class to fetch and refresh Google Cloud SQL IAM authentication tokens.
    """

    def __init__(self, scopes: Optional[List[str]] = None):
        self.scopes = scopes or CLOUDSQL_IAM_LOGIN_SCOPE
        self._credentials: Credentials = None

    def get_token(self) -> str:
        """
        Retrieves a fresh IAM authentication token.
        Refreshes the token if it is expired or not present.
        """
        if self._credentials is None:
            self._credentials, _ = google.auth.default(scopes=self.scopes)

        if self._credentials.token_state != TokenState.FRESH:
            self._credentials.refresh(requests.Request())

        return self._credentials.token
