from typing import Union

from sqlalchemy import event
from sqlalchemy.engine import Engine

from .cloud_sql import DEFAULT_TIMEOUT, CloudSqlInstance, IpType, Timeout
from .token_provider import GoogleCloudTokenProvider

try:
    from sqlalchemy.ext.asyncio import AsyncEngine
except ImportError:
    AsyncEngine = None


def register_connector(
    engine: Union[Engine, "AsyncEngine"],
    token_provider: GoogleCloudTokenProvider | None = None,
    instance_connection_name: str | None = None,
    ip_type: IpType = IpType.PUBLIC,
    enable_iam_auth: bool = True,
    timeout: Timeout = DEFAULT_TIMEOUT,
) -> None:
    """
    Registers an event listener to inject IAM tokens into the connection password
    and optionally configure the host IP for a Cloud SQL instance.

    Args:
        engine: The SQLAlchemy Engine or AsyncEngine to register the hook on.
        token_provider: Optional provider for IAM tokens.
        instance_connection_name: Optional Cloud SQL connection name in the format
            "project:region:instance". If provided, the instance IP will be resolved
            and used as the host.
        ip_type: The type of IP to resolve (PUBLIC or PRIVATE). Defaults to PUBLIC.
        enable_iam_auth: Whether to inject the IAM token as the password. Defaults to True.
        timeout: Seconds to wait for each Admin API and token endpoint request, as a
            single value or a (connect, read) tuple. Defaults to (5, 15). It does not
            reach a token_provider you pass in; configure that one directly.

    Usage:
        engine = create_engine("postgresql+psycopg://user@/db")
        register_connector(engine, instance_connection_name="my-proj:us-central1:my-inst")
    """
    host: str | None = None
    if instance_connection_name:
        cloud_sql_instance = CloudSqlInstance(instance_connection_name, timeout=timeout)
        host = cloud_sql_instance.get_host(ip_type)

    if enable_iam_auth and token_provider is None:
        token_provider = GoogleCloudTokenProvider(timeout=timeout)

    # AsyncEngine does not support event listeners directly;
    # register on the underlying sync_engine instead.
    event_target = (
        engine.sync_engine
        if AsyncEngine and isinstance(engine, AsyncEngine)
        else engine
    )

    @event.listens_for(event_target, "do_connect")
    def receive_do_connect(dialect, conn_rec, cargs, cparams):
        if host:
            cparams["host"] = host
        if enable_iam_auth:
            cparams["password"] = token_provider.get_token()
