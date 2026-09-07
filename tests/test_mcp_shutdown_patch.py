"""Transport-close cancellation contract provided by FastMCP 4 / MCP SDK 2."""

import anyio
import pytest
from fastmcp import FastMCP
from mcp.shared.memory import create_client_server_memory_streams
from mcp.shared.message import SessionMessage
import mcp.types as types


def _request(rid, method, params):
    return SessionMessage(
        types.JSONRPCRequest(
            jsonrpc="2.0",
            id=rid,
            method=method,
            params=params,
        )
    )


def _notification(method):
    return SessionMessage(
        types.JSONRPCNotification(
            jsonrpc="2.0",
            method=method,
            params={},
        )
    )


@pytest.mark.asyncio
async def test_stock_fastmcp_cancels_handler_when_transport_closes():
    """A vanished client must not leave a recording handler or microphone alive."""
    handler_started = anyio.Event()
    handler_cancelled = anyio.Event()
    server_returned = anyio.Event()
    mcp = FastMCP("vm2015-transport-close")

    @mcp.tool
    async def slow_tool() -> str:
        """Stand-in for an active VoiceMode recording."""
        handler_started.set()
        try:
            await anyio.sleep(60)
        except anyio.get_cancelled_exc_class():
            handler_cancelled.set()
            raise
        return "never reached"  # pragma: no cover

    async with create_client_server_memory_streams() as (
        client_streams,
        server_streams,
    ):
        client_read, client_write = client_streams
        server_read, server_write = server_streams

        async def serve():
            await mcp._mcp_server.run(
                server_read,
                server_write,
                mcp._mcp_server.create_initialization_options(),
            )
            server_returned.set()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(serve)
            await client_write.send(
                _request(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "vm2015-test",
                            "version": "0",
                        },
                    },
                )
            )
            with anyio.fail_after(10):
                await client_read.receive()

            await client_write.send(_notification("notifications/initialized"))
            await client_write.send(
                _request(
                    2,
                    "tools/call",
                    {"name": "slow_tool", "arguments": {}},
                )
            )
            with anyio.fail_after(10):
                await handler_started.wait()

            await client_write.aclose()

            with anyio.fail_after(3):
                await handler_cancelled.wait()
                await server_returned.wait()

            task_group.cancel_scope.cancel()
