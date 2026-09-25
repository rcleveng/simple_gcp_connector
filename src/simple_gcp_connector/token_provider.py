from functools import partial

import google.auth
from google.auth.credentials import Credentials, TokenState
from google.auth.transport import requests

from .cloud_sql import DEFAULT_TIMEOUT, Timeout

# Scope for Cloud SQL IAM login
CLOUDSQL_IAM_LOGIN_SCOPE = [
    "https://www.googleapis.com/auth/sqlservice.login",
    "https://www.googleapis.com/auth/sqlservice.admin",
]


class GoogleCloudTokenProvider:
    """
    A helper class to fetch and refresh Google Cloud SQL IAM authentication tokens.

    Args:
        scopes: OAuth scopes to request. Defaults to CLOUDSQL_IAM_LOGIN_SCOPE.
        timeout: Seconds to wait for each token endpoint request, as a single
            value or a ``(connect, read)`` tuple. A credential that sets its own
            timeout on a request (the metadata server's probe, for example)
            keeps it.
    """

    def __init__(
        self, scopes: list[str] | None = None, timeout: Timeout = DEFAULT_TIMEOUT
    ):
        self.scopes = scopes or CLOUDSQL_IAM_LOGIN_SCOPE
        self.timeout = timeout
        self._credentials: Credentials | None = None

    def get_token(self) -> str:
        """
        Retrieves a fresh IAM authentication token.
        Refreshes the token if it is expired or not present.
        """
        if self._credentials is None:
            self._credentials, _ = google.auth.default(scopes=self.scopes)

        if self._credentials.token_state != TokenState.FRESH:
            # Same approach AuthorizedSession uses to bound its own refreshes.
            self._credentials.refresh(partial(requests.Request(), timeout=self.timeout))

        token = self._credentials.token
        if token is None:
            raise RuntimeError("Google auth credentials did not provide a token")

        return token
