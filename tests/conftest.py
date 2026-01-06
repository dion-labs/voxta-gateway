"""Pytest fixtures for voxta-gateway tests."""

import pytest

from voxta_gateway.event_emitter import EventEmitter
from voxta_gateway.state import GatewayState


@pytest.fixture
def gateway_state():
    """Create a fresh GatewayState instance."""
    return GatewayState()


@pytest.fixture
def event_emitter():
    """Create a fresh EventEmitter instance."""
    return EventEmitter()



