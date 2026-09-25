import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import google.auth.exceptions
import pytest
import requests
from google.auth.credentials import Credentials

from simple_gcp_connector.cloud_sql import DEFAULT_MAX_RETRIES, CloudSqlInstance
from simple_gcp_connector.token_provider import GoogleCloudTokenProvider

METADATA = {"ipAddresses": [{"type": "PRIMARY", "ipAddress": "1.2.3.4"}]}


class FakeCredentials(Credentials):
    """Credentials that refresh without a network call, so the real
    AuthorizedSession can be used against the local server."""

    def refresh(self, request):
        self.token = "fake-token"


class ScriptedServer:
    """
    A local HTTP server that answers requests from a script of
    (status, headers, delay_seconds) entries, repeating the last entry once
    the script runs out. Records the path of every request it receives.
    """

    def __init__(self):
        self.script = [(200, {}, 0)]
        self.paths = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _respond(self):
                server.paths.append(self.path)
                index = min(len(server.paths), len(server.script)) - 1
                status, headers, delay = server.script[index]
                if delay:
                    # Event.wait rather than time.sleep, which the tests mock.
                    threading.Event().wait(delay)
                body = json.dumps(METADATA if status == 200 else {}).encode()
                try:
                    self.send_response(status)
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client gave up waiting, which is the point

            do_GET = _respond
            do_POST = _respond

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self._httpd.block_on_close = False
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        # A short poll interval keeps shutdown() from stalling each teardown.
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def server(monkeypatch):
    # Keep requests to the local server away from any configured HTTP proxy.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    with ScriptedServer() as s:
        monkeypatch.setattr(
            "simple_gcp_connector.cloud_sql.SQLADMIN_API_ENDPOINT", s.url
        )
        yield s


@pytest.fixture
def fake_auth():
    with patch(
        "google.auth.default", return_value=(FakeCredentials(), "project")
    ) as mock_default:
        yield mock_default


@pytest.fixture
def mock_sleep():
    # urllib3's Retry sleeps with time.sleep between attempts.
    with patch("urllib3.util.retry.time.sleep") as sleep:
        yield sleep


def test_a_transient_503_is_retried_until_the_fetch_succeeds(
    server, fake_auth, mock_sleep
):
    """A 503 followed by a 200 from the Admin API is retried transparently:
    the instance is built from the second response's metadata and the server
    sees exactly two GETs for the instance."""
    server.script = [(503, {}, 0), (200, {}, 0)]

    instance = CloudSqlInstance("project:region:instance")

    assert instance.get_host() == "1.2.3.4"
    assert server.paths == ["/sql/v1beta4/projects/project/instances/instance"] * 2


def test_a_persistent_503_raises_http_error_after_bounded_attempts(
    server, fake_auth, mock_sleep
):
    """An Admin API that keeps answering 503 gets one request plus
    DEFAULT_MAX_RETRIES retries, sleeping for a growing backoff between them,
    and then the constructor raises requests.HTTPError for the final 503
    rather than a urllib3 RetryError."""
    server.script = [(503, {}, 0)]

    with pytest.raises(requests.HTTPError) as excinfo:
        CloudSqlInstance("project:region:instance")

    assert excinfo.value.response.status_code == 503
    assert len(server.paths) == 1 + DEFAULT_MAX_RETRIES
    sleeps = [call.args[0] for call in mock_sleep.call_args_list]
    assert sleeps, "expected a backoff sleep between attempts"
    assert all(s > 0 for s in sleeps)
    assert sleeps == sorted(sleeps)


@pytest.mark.parametrize("status", [403, 404])
def test_a_permanent_client_error_fails_without_retrying(
    server, fake_auth, mock_sleep, status
):
    """A 403 or 404 from the Admin API is not transient: the constructor
    raises requests.HTTPError carrying that status after a single request,
    without sleeping."""
    server.script = [(status, {}, 0), (200, {}, 0)]

    with pytest.raises(requests.HTTPError) as excinfo:
        CloudSqlInstance("project:region:instance")

    assert excinfo.value.response.status_code == status
    assert len(server.paths) == 1
    mock_sleep.assert_not_called()


def test_a_long_retry_after_is_capped(server, fake_auth, mock_sleep):
    """A 429 asking the client to wait an hour is still retried, but the pause
    is capped at 30 seconds so an application's startup does not stall on the
    metadata fetch; the retry then succeeds."""
    server.script = [(429, {"Retry-After": "3600"}, 0), (200, {}, 0)]

    instance = CloudSqlInstance("project:region:instance")

    assert instance.get_host() == "1.2.3.4"
    mock_sleep.assert_called_once_with(30.0)


def test_a_read_timeout_is_enforced_and_retried(server, fake_auth, mock_sleep):
    """The configured read timeout reaches the Admin API request: a first
    response that takes 2s is abandoned after 0.2s and the GET is retried,
    succeeding on the second attempt. Without the timeout the slow first
    response would have been accepted and the server would see one request."""
    server.script = [(200, {}, 2.0), (200, {}, 0)]

    instance = CloudSqlInstance("project:region:instance", timeout=(1.0, 0.2))

    assert instance.get_host() == "1.2.3.4"
    assert len(server.paths) == 2


def test_the_admin_api_lookup_bounds_the_credential_refresh(server, monkeypatch):
    """The configured timeout also reaches the credential refresh that the
    Admin API request triggers: a token endpoint that takes 2s to answer fails
    after the 0.2s read timeout with google-auth's TransportError, before the
    Admin API is ever called."""

    class SlowEndpointCredentials(FakeCredentials):
        def refresh(self, request):
            request(url=f"{server.url}/token", method="POST")
            self.token = "fake-token"

    server.script = [(200, {}, 2.0)]
    monkeypatch.setattr(
        "google.auth.default", lambda scopes=None: (SlowEndpointCredentials(), None)
    )

    with pytest.raises(google.auth.exceptions.TransportError):
        CloudSqlInstance("project:region:instance", timeout=(1.0, 0.2))

    assert server.paths == ["/token"]


def test_connection_errors_are_retried_then_raised(monkeypatch, fake_auth, mock_sleep):
    """When nothing listens on the Admin API port, the connection is retried
    with backoff and the constructor finally raises requests.ConnectionError."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setattr(
        "simple_gcp_connector.cloud_sql.SQLADMIN_API_ENDPOINT",
        f"http://127.0.0.1:{port}",
    )

    with pytest.raises(requests.ConnectionError):
        CloudSqlInstance("project:region:instance")

    assert mock_sleep.call_count >= 1


def test_the_token_provider_bounds_the_token_request(server, monkeypatch):
    """GoogleCloudTokenProvider passes its timeout to the credential refresh:
    a token endpoint that takes 2s to answer fails after the 0.2s read
    timeout with google-auth's TransportError instead of waiting."""

    class SlowEndpointCredentials(FakeCredentials):
        def refresh(self, request):
            request(url=f"{server.url}/token", method="POST")
            self.token = "fake-token"

    server.script = [(200, {}, 2.0)]
    monkeypatch.setattr(
        "google.auth.default", lambda scopes=None: (SlowEndpointCredentials(), None)
    )

    provider = GoogleCloudTokenProvider(timeout=(1.0, 0.2))

    with pytest.raises(google.auth.exceptions.TransportError):
        provider.get_token()
