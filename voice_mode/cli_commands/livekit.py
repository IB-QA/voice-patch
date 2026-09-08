"""CLI commands for the optional local LiveKit integration."""

import asyncio
import webbrowser
from urllib.parse import quote

import click
from aiohttp import web

from voice_mode.livekit import BrowserConfig, LiveKitClient, LiveKitConfig
from voice_mode.livekit.browser_app import create_app
from voice_mode.livekit.errors import LiveKitError


@click.group()
def livekit() -> None:
    """Manage local LiveKit rooms and browser access."""


@livekit.group()
def rooms() -> None:
    """Inspect VoiceMode LiveKit rooms."""


@rooms.command("list")
def rooms_list() -> None:
    """List rooms from the configured LiveKit server."""

    async def list_configured_rooms() -> None:
        try:
            async with LiveKitClient(LiveKitConfig.from_env()) as client:
                available = await client.list_rooms()
            if not available:
                click.echo("No LiveKit rooms.")
                return
            for room in available:
                click.echo(f"{room.name}\t{room.participant_count} participant(s)")
        except LiveKitError as exc:
            raise click.ClickException(str(exc)) from exc

    asyncio.run(list_configured_rooms())


@livekit.group()
def browser() -> None:
    """Serve or open the local VoiceMode browser client."""


@browser.command("serve")
@click.option("--host", default=None, help="Loopback host to bind.")
@click.option("--port", type=click.IntRange(1, 65535), default=None)
def browser_serve(host: str | None, port: int | None) -> None:
    """Serve the packaged browser client on loopback."""

    browser_config = BrowserConfig.from_env(host=host, port=port)
    click.echo(f"Serving VoiceMode LiveKit browser at {browser_config.url}")
    web.run_app(
        create_app(browser_config),
        host=browser_config.host,
        port=browser_config.port,
    )


@browser.command("open")
def browser_open() -> None:
    """Open the browser client with its one-time fragment credential."""

    config = BrowserConfig.from_env()
    token = config.require_token()
    url = f"{config.url}/#token={quote(token, safe='')}"
    if not webbrowser.open(url):
        raise click.ClickException("Could not open the default browser.")
    click.echo(f"Opened VoiceMode LiveKit browser at {config.url}")
