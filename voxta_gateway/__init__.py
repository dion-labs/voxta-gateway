"""
Voxta Gateway - A state-mirroring gateway for the Voxta conversational AI platform.

This package provides high-level semantic APIs for downstream applications to interact
with Voxta without needing to understand its internal protocol.
"""

from voxta_gateway.state import AIState, CharacterInfo, GatewayState

__version__ = "0.1.0"
__all__ = ["AIState", "CharacterInfo", "GatewayState", "__version__"]

