import pytest
import urllib.parse
from simple_gcp_connector.psycopg import GoogleCloudConnInfoProvider
from simple_gcp_connector.token_provider import GoogleCloudTokenProvider
from psycopg_pool import ConnectionPool
import os
from dotenv import load_dotenv

load_dotenv()

INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")
if not INSTANCE_CONNECTION_NAME:
    raise ValueError("INSTANCE_CONNECTION_NAME is not set")

IAM_USER = os.getenv("IAM_USER")
if not IAM_USER:
    raise ValueError("IAM_USER is not set")

ENCODED_IAM_USER = urllib.parse.quote(IAM_USER)
DEFAULT_DB_URL = f"postgresql://{ENCODED_IAM_USER}@localhost/postgres"
DEFAULT_SQLALCHEMY_DB_URL = (
    f"postgresql+psycopg://{ENCODED_IAM_USER}@localhost/postgres"
)


def test_get_token():
    token_provider = GoogleCloudTokenProvider()
    token = token_provider.get_token()
    assert token is not None


@pytest.mark.integration
def test_psycopg_end_to_end_cloudsql_proxy():
    get_conninfo = GoogleCloudConnInfoProvider(DEFAULT_DB_URL)
    with ConnectionPool(conninfo=get_conninfo) as pool:
        with pool.connection() as conn:
            print("Connected!")
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            result = cursor.fetchone()
            print(f"Result: {result}")
            assert result is not None


@pytest.mark.integration
def test_psycopg_end_to_end_cloudql_direct():
    get_conninfo = GoogleCloudConnInfoProvider(
        conninfo=f"postgresql://{ENCODED_IAM_USER}@TBD/postgres",
        instance_connection_name=INSTANCE_CONNECTION_NAME,
    )
    with ConnectionPool(conninfo=get_conninfo) as pool:
        with pool.connection() as conn:
            print("Connected!")
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            result = cursor.fetchone()
            print(f"Result: {result}")
            assert result is not None


@pytest.mark.integration
def test_sqlalchemy_end_to_end_cloudsql_proxy():
    from sqlalchemy import create_engine, text
    from simple_gcp_connector.sqlalchemy import register_connector

    engine = create_engine(
        DEFAULT_SQLALCHEMY_DB_URL,
        connect_args={"sslmode": "disable"},
    )
    register_connector(engine)

    with engine.connect() as conn:
        print("Connected!")
        result = conn.execute(text("SELECT version()"))
        row = result.fetchone()
        print(f"Result: {row}")
        assert row is not None


@pytest.mark.integration
def test_sqlalchemy_end_to_end_cloudql_direct():
    from sqlalchemy import create_engine, text
    from simple_gcp_connector.sqlalchemy import register_connector
    # The helper now supports looking up the instance IP automatically

    # We use a placeholder host in the URL since it will be overwritten
    engine = create_engine(
        f"postgresql+psycopg://{ENCODED_IAM_USER}@tbd/postgres",
        connect_args={"sslmode": "require"},
    )
    register_connector(engine, instance_connection_name=INSTANCE_CONNECTION_NAME)

    with engine.connect() as conn:
        print("Connected!")
        result = conn.execute(text("SELECT version()"))
        row = result.fetchone()
        print(f"Result: {row}")
        assert row is not None
