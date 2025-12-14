from unittest.mock import MagicMock, patch
import pytest
from simple_gcp_connector.cloud_sql import CloudSqlInstance, IpType
from simple_gcp_connector.psycopg import GoogleCloudConnInfoProvider


@patch("simple_gcp_connector.cloud_sql.requests.AuthorizedSession")
@patch("simple_gcp_connector.cloud_sql.google.auth.default")
def test_cloud_sql_instance_get_host(mock_default, mock_session_cls):
    # Mock auth
    mock_creds = MagicMock()
    mock_default.return_value = (mock_creds, "project")

    # Mock session
    mock_session = mock_session_cls.return_value
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "ipAddresses": [
            {"type": "PRIMARY", "ipAddress": "1.2.3.4"},
            {"type": "PRIVATE", "ipAddress": "10.0.0.1"},
        ]
    }
    mock_session.get.return_value = mock_response

    # Initialization triggers the fetch
    instance = CloudSqlInstance("project:region:instance")

    # Test Public IP (uses stored metadata)
    assert instance.get_host(IpType.PUBLIC) == "1.2.3.4"

    # Test Private IP (uses stored metadata)
    assert instance.get_host(IpType.PRIVATE) == "10.0.0.1"


@patch("simple_gcp_connector.psycopg.CloudSqlInstance")
@patch("simple_gcp_connector.psycopg.GoogleCloudTokenProvider")
def test_provider_with_metadata(mock_token_provider_cls, mock_cloud_sql_cls):
    # Mock Token Provider
    mock_token_provider = mock_token_provider_cls.return_value
    mock_token_provider.get_token.return_value = "fake-token"

    # Mock Cloud SQL Instance
    mock_instance = mock_cloud_sql_cls.return_value
    mock_instance.get_host.return_value = "1.2.3.4"

    provider = GoogleCloudConnInfoProvider(
        "postgresql://user@/db",
        instance_connection_name="my-project:region:my-instance",
        ip_type=IpType.PUBLIC,
    )

    conninfo = provider()

    assert "host=1.2.3.4" in conninfo
    assert "password=fake-token" in conninfo

    # Verify constructor called the API
    mock_cloud_sql_cls.assert_called_with("my-project:region:my-instance")
    mock_instance.get_host.assert_called_with(IpType.PUBLIC)


@patch("simple_gcp_connector.cloud_sql.requests.AuthorizedSession")
@patch("simple_gcp_connector.cloud_sql.google.auth.default")
def test_cloud_sql_instance_get_host_error(mock_default, mock_session_cls):
    # Mock auth and session
    mock_default.return_value = (MagicMock(), "project")
    mock_session = mock_session_cls.return_value
    mock_session.get.return_value.json.return_value = {"ipAddresses": []}

    instance = CloudSqlInstance("project:region:instance")

    with pytest.raises(ValueError, match="No IP address found"):
        instance.get_host(IpType.PUBLIC)


def test_provider_basic_usage():
    mock_token_provider = MagicMock()
    mock_token_provider.get_token.return_value = "fake-token"

    provider = GoogleCloudConnInfoProvider(
        "postgresql://user@host/db", token_provider=mock_token_provider
    )

    conninfo = provider()

    assert "password=fake-token" in conninfo
    # Should maintain original host since no project/instance provided
    assert "host=host" in conninfo


@patch("simple_gcp_connector.psycopg.CloudSqlInstance")
def test_provider_no_iam_auth(mock_cloud_sql_cls):
    # Mock Cloud SQL Instance
    mock_instance = mock_cloud_sql_cls.return_value
    mock_instance.get_host.return_value = "1.2.3.4"

    provider = GoogleCloudConnInfoProvider(
        "postgresql://user@/db",
        instance_connection_name="my-project:region:my-instance",
        enable_iam_auth=False,
    )

    conninfo = provider()

    assert "host=1.2.3.4" in conninfo
    assert "password=" not in conninfo
