import pytest


def test_sqlalchemy_import():
    try:
        from simple_gcp_connector.sqlalchemy import register_connector  # noqa: F401
    except ImportError:
        pytest.fail("Could not import simple_gcp_connector.sqlalchemy")


def test_psycopg_import():
    try:
        from simple_gcp_connector.psycopg import GoogleCloudConnInfoProvider  # noqa: F401
    except ImportError:
        pytest.fail("Could not import simple_gcp_connector.psycopg")
