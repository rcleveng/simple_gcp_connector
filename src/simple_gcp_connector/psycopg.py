from typing import Optional
from psycopg.conninfo import make_conninfo
from .token_provider import GoogleCloudTokenProvider
from .cloud_sql import CloudSqlInstance, IpType


class GoogleCloudConnInfoProvider:
    """
    A helper to provide dynamic connection info with fresh IAM tokens and optional host lookup.
    Designed for use with psycopg_pool.ConnectionPool(conninfo=...)

    Usage:
        # Standard usage with full conninfo
        get_conninfo = GoogleCloudConnInfoProvider("postgresql://user@host/db")

        # Usage with metadata lookup
        get_conninfo = GoogleCloudConnInfoProvider(
            "postgresql://user@/db",
            project="my-project",
            instance="my-instance",
            ip_type=IpType.PUBLIC
        )
        pool = ConnectionPool(conninfo=get_conninfo)
    """

    def __init__(
        self,
        conninfo: str,
        instance_connection_name: str | None = None,
        ip_type: IpType = IpType.PUBLIC,
        token_provider: Optional[GoogleCloudTokenProvider] = None,
        enable_iam_auth: bool = True,
    ) -> None:
        self.conninfo = conninfo
        self.host = None
        self.enable_iam_auth = enable_iam_auth

        # Only initialize token provider if IAM auth is enabled
        if enable_iam_auth:
            self.token_provider = token_provider or GoogleCloudTokenProvider()
        else:
            self.token_provider = None

        # Fail fast: resolve host immediately if instance connection name is provided
        if instance_connection_name:
            cloud_sql = CloudSqlInstance(instance_connection_name)
            self.host = cloud_sql.get_host(ip_type)

    def __call__(self) -> str:
        conn_args = {}

        if self.enable_iam_auth and self.token_provider:
            conn_args["password"] = self.token_provider.get_token()

        if self.host:
            conn_args["host"] = self.host

        return make_conninfo(self.conninfo, **conn_args)
