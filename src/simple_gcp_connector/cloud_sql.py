import google.auth
from google.auth.transport import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from enum import StrEnum

SQLADMIN_API_ENDPOINT = "https://sqladmin.googleapis.com"

# (connect, read) timeout in seconds for each HTTP request the connector makes.
Timeout = float | tuple[float, float]
DEFAULT_TIMEOUT: Timeout = (5.0, 15.0)

# Retries after the first attempt, so a fetch makes at most 4 requests.
DEFAULT_MAX_RETRIES = 3
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


class IpType(StrEnum):
    PUBLIC = "PRIMARY"
    PRIVATE = "PRIVATE"


class _AdminApiRetry(Retry):
    """
    A Retry that honors Retry-After, but never sleeps longer than
    RETRY_AFTER_MAX seconds for it.

    The metadata fetch runs while an application is starting up, so a server
    asking for a long pause should surface as an error rather than a stall.
    urllib3 only gained a ``retry_after_max`` argument in 2.6; capping here
    keeps older urllib3 2.x releases working.
    """

    RETRY_AFTER_MAX = 30.0

    def get_retry_after(self, response):
        retry_after = super().get_retry_after(response)
        if retry_after is None:
            return None
        return min(retry_after, self.RETRY_AFTER_MAX)


def _admin_api_retry(max_retries: int = DEFAULT_MAX_RETRIES) -> Retry:
    """
    Retry policy for Cloud SQL Admin API reads.

    Retries connection errors, read timeouts and transient HTTP statuses on GET
    only, with exponential backoff and jitter. Other statuses (401, 403, 404,
    ...) are returned at once. ``raise_on_status=False`` hands the last response
    back to the caller once retries run out, so ``raise_for_status()`` raises
    the real ``requests.HTTPError`` instead of a ``RetryError``.
    """
    return _AdminApiRetry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=max_retries,
        allowed_methods=frozenset({"GET"}),
        status_forcelist=RETRYABLE_STATUS_CODES,
        backoff_factor=0.5,
        backoff_max=10.0,
        backoff_jitter=0.5,
        raise_on_status=False,
        respect_retry_after_header=True,
    )


class CloudSqlInstance:
    """
    Helper to fetch metadata for a Cloud SQL instance.

    Args:
        instance_connection_name: "project:region:instance".
        timeout: Seconds to wait for each Admin API request, as a single value
            or a ``(connect, read)`` tuple. Also bounds the credential refresh
            the request may trigger. Transient failures are retried, so the
            whole fetch can take several times this long.
    """

    def __init__(
        self, instance_connection_name: str, timeout: Timeout = DEFAULT_TIMEOUT
    ):
        parts = instance_connection_name.split(":")
        if len(parts) != 3:
            raise ValueError(
                "instance_connection_name must be in the format 'project:region:instance'"
            )
        self.project, _, self.instance = parts
        self.timeout = timeout
        self._credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/sqlservice.admin"]
        )
        self._session = requests.AuthorizedSession(
            self._credentials, refresh_timeout=timeout
        )
        self._session.mount(
            f"{SQLADMIN_API_ENDPOINT}/", HTTPAdapter(max_retries=_admin_api_retry())
        )
        self.metadata = self._fetch_metadata()

    def _fetch_metadata(self) -> dict:
        url = f"{SQLADMIN_API_ENDPOINT}/sql/v1beta4/projects/{self.project}/instances/{self.instance}"
        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_host(self, ip_type: IpType = IpType.PUBLIC) -> str:
        """
        Fetches the IP address of the Cloud SQL instance from stored metadata.
        """
        for ip_mapping in self.metadata.get("ipAddresses", []):
            if ip_mapping.get("type") == ip_type:
                return ip_mapping.get("ipAddress")

        raise ValueError(f"No IP address found for type {ip_type}")
