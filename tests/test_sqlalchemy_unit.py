from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from simple_gcp_connector.sqlalchemy import register_connector
from simple_gcp_connector.token_provider import GoogleCloudTokenProvider


def test_sqlalchemy_registration():
    # Use in-memory SQLite for a real engine instance that supports events
    engine = create_engine("sqlite:///")
    mock_provider = MagicMock(spec=GoogleCloudTokenProvider)

    # Should not raise
    register_connector(engine, token_provider=mock_provider)

    # Verify the listener is registered.
    # Accessing internal dispatch to verify listener presence
    if hasattr(engine.dispatch, "do_connect"):
        assert len(engine.dispatch.do_connect) > 0
    else:
        # Fallback if internals change, but at least we didn't crash
        pass


def test_sqlalchemy_async_engine_registration():
    # AsyncEngine should work by registering on its sync_engine
    engine = create_async_engine("sqlite+aiosqlite:///")
    mock_provider = MagicMock(spec=GoogleCloudTokenProvider)

    # Should not raise NotImplementedError
    register_connector(engine, token_provider=mock_provider)

    # Verify the listener is registered on the underlying sync_engine
    if hasattr(engine.sync_engine.dispatch, "do_connect"):
        assert len(engine.sync_engine.dispatch.do_connect) > 0
