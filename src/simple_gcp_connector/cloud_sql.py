import google.auth
from google.auth.transport import requests
from enum import StrEnum


class IpType(StrEnum):
    PUBLIC = "PRIMARY"
    PRIVATE = "PRIVATE"


class CloudSqlInstance:
    """
    Helper to fetch metadata for a Cloud SQL instance.
    """

    def __init__(self, instance_connection_name: str):
        parts = instance_connection_name.split(":")
        if len(parts) != 3:
            raise ValueError(
                "instance_connection_name must be in the format 'project:region:instance'"
            )
        self.project, _, self.instance = parts
        self._credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/sqlservice.admin"]
        )
        self._session = requests.AuthorizedSession(self._credentials)
        self.metadata = self._fetch_metadata()

    def _fetch_metadata(self) -> dict:
        url = f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{self.project}/instances/{self.instance}"
        response = self._session.get(url)
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
