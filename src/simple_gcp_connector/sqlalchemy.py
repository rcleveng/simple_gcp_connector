from typing import Optional
from sqlalchemy import event
from sqlalchemy.engine import Engine
from .token_provider import GoogleCloudTokenProvider
from .cloud_sql import CloudSqlInstance, IpType


def register_connector(
    engine: Engine,
    token_provider: Optional[GoogleCloudTokenProvider] = None,
    instance_connection_name: Optional[str] = None,
    ip_type: IpType = IpType.PUBLIC,
    enable_iam_auth: bool = True,
) -> None:
    """
    Registers an event listener to inject IAM tokens into the connection password
    and optionally configure the host IP for a Cloud SQL instance.

    Args:
        engine: The SQLAlchemy Engine to register the hook on.
        token_provider: Optional provider for IAM tokens.
        instance_connection_name: Optional Cloud SQL connection name in the format
            "project:region:instance". If provided, the instance IP will be resolved
            and used as the host.
        ip_type: The type of IP to resolve (PUBLIC or PRIVATE). Defaults to PUBLIC.
        enable_iam_auth: Whether to inject the IAM token as the password. Defaults to True.

    Usage:
        engine = create_engine("postgresql+psycopg://user@/db")
        register_iam_auth(engine, instance_connection_name="my-proj:us-central1:my-inst")
    """
    host: Optional[str] = None
    if instance_connection_name:
        cloud_sql_instance = CloudSqlInstance(instance_connection_name)
        host = cloud_sql_instance.get_host(ip_type)

    if enable_iam_auth and token_provider is None:
        token_provider = GoogleCloudTokenProvider()

    @event.listens_for(engine, "do_connect")
    def receive_do_connect(dialect, conn_rec, cargs, cparams):
        if host:
            cparams["host"] = host
        if enable_iam_auth:
            cparams["password"] = token_provider.get_token()
