from unittest.mock import MagicMock, patch

import pytest

from simple_gcp_connector.cloud_sql import DEFAULT_TIMEOUT, CloudSqlInstance, IpType
from simple_gcp_connector.psycopg import GoogleCloudConnInfoProvider


@patch("simple_gcp_connector.cloud_sql.requests.AuthorizedSession")
@patch("simple_gcp_connector.cloud_sql.google.auth.default")
def test_cloud_sql_instance_supports_primary_and_public_alias(
    mock_default, mock_session_cls
):
    mock_default.return_value = (MagicMock(), "project")
    mock_session = mock_session_cls.return_value
    mock_session.get.return_value.json.return_value = {
        "ipAddresses": [
            {"type": "PRIMARY", "ipAddress": "1.2.3.4"},
            {"type": "PRIVATE", "ipAddress": "10.0.0.1"},
        ]
    }

    instance = CloudSqlInstance("project:region:instance")

    assert instance.get_host(IpType.PRIMARY) == "1.2.3.4"
    assert instance.get_host(IpType.PRIVATE) == "10.0.0.1"
    assert instance.get_host(IpType.PUBLIC) == "1.2.3.4"


@patch("simple_gcp_connector.cloud_sql.requests.AuthorizedSession")
@patch("simple_gcp_connector.cloud_sql.google.auth.default")
def test_cloud_sql_instance_get_host_error(mock_default, mock_session_cls):
    mock_default.return_value = (MagicMock(), "project")
    mock_session = mock_session_cls.return_value
    mock_session.get.return_value.json.return_value = {"ipAddresses": []}

    instance = CloudSqlInstance("project:region:instance")

    with pytest.raises(ValueError, match="No IP address found"):
        instance.get_host(IpType.PRIMARY)


def test_ip_type_public_is_a_backwards_compatible_primary_alias():
    assert IpType.PUBLIC is IpType.PRIMARY
    assert IpType["PUBLIC"] is IpType.PRIMARY
    assert IpType("PRIMARY") is IpType.PRIMARY


@patch("simple_gcp_connector.psycopg.CloudSqlInstance")
@patch("simple_gcp_connector.psycopg.GoogleCloudTokenProvider")
def test_provider_with_metadata(mock_token_provider_cls, mock_cloud_sql_cls):
    mock_token_provider_cls.return_value.get_token.return_value = "fake-token"
    mock_instance = mock_cloud_sql_cls.return_value
    mock_instance.get_host.return_value = "1.2.3.4"

    provider = GoogleCloudConnInfoProvider(
        "postgresql://user@/db",
        instance_connection_name="my-project:region:my-instance",
        ip_type=IpType.PRIMARY,
    )

    conninfo = provider()

    assert "host=1.2.3.4" in conninfo
    assert "password=" in conninfo
    mock_cloud_sql_cls.assert_called_with(
        "my-project:region:my-instance", timeout=DEFAULT_TIMEOUT
    )
    mock_instance.get_host.assert_called_with(IpType.PRIMARY)


def test_provider_basic_usage():
    mock_token_provider = MagicMock()
    mock_token_provider.get_token.return_value = "fake-token"

    provider = GoogleCloudConnInfoProvider(
        "postgresql://user@host/db", token_provider=mock_token_provider
    )

    conninfo = provider()

    assert "password=" in conninfo
    assert "host=host" in conninfo


@patch("simple_gcp_connector.psycopg.CloudSqlInstance")
def test_provider_no_iam_auth(mock_cloud_sql_cls):
    mock_cloud_sql_cls.return_value.get_host.return_value = "1.2.3.4"

    provider = GoogleCloudConnInfoProvider(
        "postgresql://user@/db",
        instance_connection_name="my-project:region:my-instance",
        enable_iam_auth=False,
    )

    conninfo = provider()

    assert "host=1.2.3.4" in conninfo
    assert "password=" not in conninfo


@patch("simple_gcp_connector.psycopg.CloudSqlInstance")
@patch("simple_gcp_connector.psycopg.GoogleCloudTokenProvider")
def test_provider_passes_timeout(mock_token_provider_cls, mock_cloud_sql_cls):
    mock_cloud_sql_cls.return_value.get_host.return_value = "1.2.3.4"

    GoogleCloudConnInfoProvider(
        "postgresql://user@/db",
        instance_connection_name="my-project:region:my-instance",
        timeout=(1.0, 2.0),
    )

    mock_cloud_sql_cls.assert_called_with(
        "my-project:region:my-instance", timeout=(1.0, 2.0)
    )
    mock_token_provider_cls.assert_called_with(timeout=(1.0, 2.0))
