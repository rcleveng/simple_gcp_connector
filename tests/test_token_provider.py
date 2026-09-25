from unittest.mock import MagicMock, patch

import pytest

from simple_gcp_connector.token_provider import GoogleCloudTokenProvider


@patch("simple_gcp_connector.token_provider.google.auth.default")
def test_get_token_raises_if_refresh_does_not_provide_a_token(mock_default):
    mock_credentials = MagicMock()
    mock_credentials.token_state = object()
    mock_credentials.token = None
    mock_default.return_value = (mock_credentials, "project")

    provider = GoogleCloudTokenProvider()

    with pytest.raises(RuntimeError, match="did not provide a token"):
        provider.get_token()

    mock_credentials.refresh.assert_called_once()
