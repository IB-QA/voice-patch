"""Entry points that coding-tool hooks call."""

import sys

import click

from voice_mode.stop_guard import CLIENTS, run


@click.group(help="Commands run by coding-tool hooks.")
@click.help_option("-h", "--help")
def hook() -> None:
    pass


@hook.command("stop-guard")
@click.option("--client", type=click.Choice(CLIENTS), required=True)
def stop_guard(client: str) -> None:
    """Keep the agent going while the user is still on a voice call.

    Reads the client's hook JSON on stdin. Prints a continue instruction only
    when a recording is in progress or a transcript was never collected;
    otherwise prints nothing, so the agent may stop. Always exits 0.
    """
    out = run(client, sys.stdin.read())
    if out:
        click.echo(out)
