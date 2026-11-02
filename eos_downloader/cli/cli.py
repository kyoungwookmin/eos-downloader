#!/usr/bin/env python
# coding: utf-8 -*-
# pylint: disable=no-value-for-parameter
# pylint: disable=cyclic-import
# pylint: disable=too-many-arguments
# pylint: disable=unused-argument


"""
ARDL CLI Baseline.
"""

from enum import Enum
from typing import Optional, cast

import typer

from eos_downloader import __version__
from eos_downloader.config import get_default_map
from eos_downloader.cli.debug import commands as debug_commands
from eos_downloader.cli.info import commands as info_commands
from eos_downloader.cli.get import commands as get_commands
from eos_downloader.cli.config import commands as config_commands

from eos_downloader.cli.utils import AliasedTyperGroup

# ==============================================================================
# [ADDED] minfiles 자동 주입을 위한 모듈 및 함수 추가
# ==============================================================================
import subprocess
from pathlib import Path
from loguru import logger

def _inject_minfiles_to_root(image_path: Path) -> None:
    """
    Injects files from /root/eos-scripts/minfiles into the root (/) of the QEMU disk image.
    """
    minfiles_dir = Path("/root/eos-scripts/minfiles")

    if not minfiles_dir.exists() or not any(minfiles_dir.iterdir()):
        logger.info(f"[-] minfiles directory ({minfiles_dir}) does not exist or is empty. Skipping injection.")
        return

    logger.info(f"[+] Injecting minfiles from {minfiles_dir} into disk image root: {image_path}")

    try:
        cmd = [
            "virt-copy-in",
            "-a", str(image_path),
            str(minfiles_dir) + "/.",
            "/"
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"[+] Successfully injected minfiles: {result.stdout.strip()}")

    except subprocess.CalledProcessError as e:
        logger.error(f"[-] Error executing virt-copy-in: {e.stderr}")
    except FileNotFoundError:
        logger.error("[-] Error: 'virt-copy-in' command not found. Please install libguestfs-tools on the host.")
# ==============================================================================
# [ADDED END] minfiles 자동 주입 함수
# ==============================================================================


class LogLevel(str, Enum):
    """Logging levels accepted by the ``--log-level`` option."""

    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


def _version_callback(value: bool) -> None:
    """Print the ardl version and exit (eager ``--version`` handler)."""
    if value:
        typer.echo(f"ardl, version {__version__}")
        raise typer.Exit()


# Root Typer application. The command-prefix aliasing (``ge`` -> ``get``) is
# provided by AliasedTyperGroup.
app = typer.Typer(
    cls=AliasedTyperGroup,
    name="ardl",
    add_completion=False,
    help="Arista Network Download CLI",
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    token: Optional[str] = typer.Option(
        None,
        "--token",
        help="Arista Token from your customer account",
        show_envvar=True,
    ),
    log_level: LogLevel = typer.Option(
        LogLevel.error,
        "--log-level",
        "--log",
        help="Logging level of the command",
        case_sensitive=False,
    ),
    debug_enabled: bool = typer.Option(
        False,
        "--debug-enabled",
        "--debug",
        help="Activate debug mode for ardl cli",
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Arista Network Download CLI"""
    ctx.ensure_object(dict)

    # Normalise the enum back to its plain string value (downstream consumers,
    # e.g. initialize()/configure_logging, expect a lowercase string).
    log_level_value = log_level.value if isinstance(log_level, LogLevel) else log_level

    # Load config file and inject as default_map for subcommands
    default_map = get_default_map()
    if default_map is not None:
        ctx.default_map = default_map

        # Apply root-level config values for options not provided via CLI or env
        # var. Typer vendors its own copy of Click, so ParameterSource enum
        # identity differs from the top-level ``click`` package; compare by
        # member name to stay runtime-agnostic (see design D8).
        for param_name in ("token", "log_level", "debug_enabled"):
            source = ctx.get_parameter_source(param_name)
            if (
                source is not None
                and source.name == "DEFAULT"
                and param_name in default_map
            ):
                if param_name == "token":
                    token = default_map[param_name]
                elif param_name == "log_level":
                    log_level_value = default_map[param_name]
                elif param_name == "debug_enabled":
                    debug_enabled = default_map[param_name]

    ctx.obj["token"] = token
    ctx.obj["log_level"] = log_level_value
    ctx.obj["debug"] = debug_enabled

    # If no command is provided, show help and exit with code 0
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


# ---------------------------------------------------------------------------
# Command groups: each is a Typer sub-application mounted on the root. Using a
# single (vendored) Typer/Click runtime throughout avoids the cross-runtime
# mixing that makes Click/Typer cohabitation impossible (see design D1).
# ---------------------------------------------------------------------------
app.add_typer(
    get_commands.app, name="get", help="Download Arista from Arista website"
)
app.add_typer(
    info_commands.app, name="info", help="List information from Arista website"
)
app.add_typer(
    debug_commands.app, name="debug", help="Debug commands to work with ardl"
)
app.add_typer(
    config_commands.app, name="config", help="Manage ardl configuration."
)


def _build_command() -> AliasedTyperGroup:
    """Compile the Typer application into a runnable command.

    Returns the fully-assembled command (the compiled Typer root with all
    sub-applications). Used both by the ``ardl`` entry point and by the test
    suite (``from eos_downloader.cli.cli import ardl``).
    """
    command = cast(AliasedTyperGroup, typer.main.get_command(app))
    command.name = "ardl"
    return command


# Fully-assembled CLI command. Exposed at module level so tests can import and
# invoke it directly (``from eos_downloader.cli.cli import ardl``).
ardl = _build_command()


# ARDL CLI Execution
def cli() -> None:
    """Load ARDL CLI"""
    # ``auto_envvar_prefix`` is preserved here so that ``ARISTA_*`` environment
    # variables keep resolving options (see design D2). Losing it silently
    # breaks every ARISTA_* variable.
    ardl(obj={}, auto_envvar_prefix="arista")


if __name__ == "__main__":
    cli()
