"""
Voxta Gateway - A state-mirroring gateway for the Voxta conversational AI platform.

This package provides high-level semantic APIs for downstream applications to interact
with Voxta without needing to understand its internal protocol.

Server:
    Run the gateway server with `voxta-gateway` or `uvicorn voxta_gateway.main:app`

Client:
    Use `GatewayClient` to connect to a running gateway:

    ```python
    from voxta_gateway import GatewayClient

    client = GatewayClient("http://localhost:8081", "my-app")

    @client.on("dialogue_received")
    async def on_dialogue(data):
        print(f"Message: {data['text']}")

    await client.start()
    ```
"""

from voxta_gateway.client import ConnectionState, GatewayClient
from voxta_gateway.state import AIState, CharacterInfo, GatewayState

__version__ = "0.1.0"
__all__ = [
    "GatewayClient",
    "ConnectionState",
    "AIState",
    "CharacterInfo",
    "GatewayState",
    "__version__",
]
