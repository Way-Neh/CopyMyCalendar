#!/usr/bin/env python3
"""
sync.py - Direct Mac Calendar to Gmail (In-App) Sync Tool (Machine Local Time as Reference).
Uses unique calendarIdentifier for 100% reliable matching.
"""

import os
import sys
import glob

# Auto-inject project virtual environment site-packages if present
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_site_packages = glob.glob(os.path.join(_PROJECT_DIR, "venv", "lib", "python*", "site-packages"))
for _sp in _site_packages:
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import time
import logging
import argparse
import yaml
from pathlib import Path
from datetime import datetime, timedelta

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm

from mac_calendar import MacCalendarClient
from sync_engine import SyncStateStore, SyncEngine, SYNC_LOG_FILE
from launchd_manager import LaunchdManager

logger = logging.getLogger("sync")
console = Console()
CONFIG_FILE = "config.yaml"


def load_config(config_path: str = CONFIG_FILE) -> dict:
    """Load configuration from YAML file."""
    if not os.path.exists(config_path):
        if os.path.exists("config.yaml.example"):
            with open("config.yaml.example", "r") as f:
                return yaml.safe_load(f)
        return {
            "source_calendar_name": "Work",
            "source_calendar_id": "",
            "target_calendar_name": "Gmail - Work",
            "target_calendar_id": "",
            "rolling_days_past": 365,
            "rolling_days_future": 730,
            "sync_interval_minutes": 15,
            "state_db_file": "sync_state.db"
        }
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def save_config(config_data: dict, config_path: str = CONFIG_FILE):
    """Save configuration to YAML file."""
    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)


def get_all_available_calendars(include_event_counts: bool = True) -> list:
    """Retrieve all calendars available across EventKit (macOS Calendar) and Microsoft Outlook."""
    calendars = []
    
    # 1. EventKit
    try:
        client = MacCalendarClient()
        cals = client.get_calendars(include_event_counts=include_event_counts)
        calendars.extend(cals)
    except Exception as e:
        logger_name = logging.getLogger("sync")
        logger_name.debug(f"EventKit access note: {e}")

    # 2. Microsoft Outlook
    try:
        from outlook_calendar import OutlookCalendarClient
        out_client = OutlookCalendarClient()
        if out_client.is_available():
            out_cals = out_client.get_calendars(include_event_counts=include_event_counts)
            calendars.extend(out_cals)
    except Exception as e:
        logger_name = logging.getLogger("sync")
        logger_name.debug(f"Outlook access note: {e}")

    return calendars


def cmd_list_calendars(args):
    """List all available calendars in macOS Calendar app and Microsoft Outlook with unique IDs and event counts."""
    console.print("[bold blue]Connecting to macOS Calendar Store & Microsoft Outlook...[/bold blue]")
    calendars = get_all_available_calendars(include_event_counts=True)

    if not calendars:
        console.print("[bold red]No calendars found in macOS Calendar or Microsoft Outlook.[/bold red]")
        return 1

    table = Table(title="Available Calendars (macOS Calendar & Outlook)", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Account / Source", style="cyan")
    table.add_column("Calendar Title", style="bold green")
    table.add_column("Events (±1 yr)", style="bold yellow")
    table.add_column("Unique Identifier (ID)", style="dim")

    for i, cal in enumerate(calendars, 1):
        count = cal.get('event_count_1yr')
        count_str = f"{count} events" if count is not None else "Ready"
        table.add_row(str(i), cal["source"], cal["title"], count_str, cal["identifier"])

    console.print(table)
    return 0


def cmd_setup(args):
    """Interactive setup wizard using unique calendar identifiers."""
    console.print(Panel.fit("[bold green]Mac Calendar -> Gmail (In-App) Sync Setup Wizard[/bold green]"))

    console.print("[dim]Scanning calendars across macOS Calendar and Microsoft Outlook...[/dim]")
    calendars = get_all_available_calendars(include_event_counts=True)

    if not calendars:
        console.print("[bold red]No calendars found in Mac Calendar app or Microsoft Outlook.[/bold red]")
        return 1

    table = Table(title="Available Calendars (macOS Calendar & Microsoft Outlook)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Account / Source", style="cyan")
    table.add_column("Calendar Name", style="bold green")
    table.add_column("Events Found (±1 yr)", style="bold yellow")
    table.add_column("Unique ID", style="dim")

    for i, cal in enumerate(calendars, 1):
        count = cal.get('event_count_1yr')
        count_str = f"{count} events" if count is not None else "Ready"
        table.add_row(str(i), cal["source"], cal["title"], count_str, cal["identifier"][:18] + "...")
    console.print(table)

    # 1. Select Source Calendar
    src_choice = IntPrompt.ask(
        "\nSelect the NUMBER (#) for your [bold cyan]SOURCE[/bold cyan] calendar",
        default=1,
        choices=[str(i) for i in range(1, len(calendars) + 1)]
    )
    selected_src = calendars[int(src_choice) - 1]
    source_cal = selected_src["title"]
    source_acc = selected_src["source"]
    source_id = selected_src["identifier"]
    console.print(f"[green]Selected SOURCE calendar:[/green] [bold]{source_cal}[/bold] (Account: [cyan]{source_acc}[/cyan], Events: [yellow]{selected_src.get('event_count_1yr', 0)}[/yellow])")
    console.print(f"[dim]Unique ID: {source_id}[/dim]")

    # 2. Select Target Calendar (Gmail)
    tgt_choice = IntPrompt.ask(
        "Select the NUMBER (#) for your [bold cyan]TARGET GMAIL[/bold cyan] calendar",
        default=2 if len(calendars) > 1 else 1,
        choices=[str(i) for i in range(1, len(calendars) + 1)]
    )
    selected_tgt = calendars[int(tgt_choice) - 1]
    target_cal = selected_tgt["title"]
    target_acc = selected_tgt["source"]
    target_id = selected_tgt["identifier"]
    console.print(f"[green]Selected TARGET GMAIL calendar:[/green] [bold]{target_cal}[/bold] (Account: [cyan]{target_acc}[/cyan])")
    console.print(f"[dim]Unique ID: {target_id}[/dim]")

    if source_id == target_id:
        console.print("[bold yellow]Warning: Source and Target calendars are the same! Make sure you select different calendars.[/bold yellow]")

    # 3. Rolling window
    days_past = IntPrompt.ask("Rolling days in the past to sync (e.g. 365 = 1 year)", default=365)
    days_future = IntPrompt.ask("Rolling days into the future to sync (e.g. 730 = 2 years)", default=730)

    # 4. Sync interval
    interval = IntPrompt.ask("Background sync interval (in minutes)", default=15)

    config = {
        "source_calendar_id": source_id,
        "source_calendar_name": source_cal,
        "source_calendar_account": source_acc,
        "target_calendar_id": target_id,
        "target_calendar_name": target_cal,
        "target_calendar_account": target_acc,
        "rolling_days_past": days_past,
        "rolling_days_future": days_future,
        "sync_interval_minutes": interval,
        "state_db_file": "sync_state.db"
    }
    save_config(config)
    console.print(f"\n[bold green]Configuration successfully saved to {CONFIG_FILE} with Unique Calendar IDs![/bold green]")
    console.print("You can now run sync with: [bold cyan]python3 sync.py --sync --all-time[/bold cyan]")
    return 0


def cmd_clear_target(args):
    """Delete all events from the target calendar and clear mapping store."""
    config = load_config()
    target_id = getattr(args, "target_id", None) or config.get("target_calendar_id")
    target_name = config.get("target_calendar_name", "Target")
    db_file = config.get("state_db_file", "sync_state.db")

    if not target_id:
        console.print("[bold red]Error: No target_calendar_id configured. Please run 'python3 sync.py --setup' first.[/bold red]")
        return 1

    console.print(f"[bold red]WARNING:[/] This will delete [bold]ALL events[/bold] from target calendar: '[bold yellow]{target_name}[/bold yellow]' [ID: {target_id}] and reset sync state.")

    if not args.yes:
        confirmed = Confirm.ask(f"Are you sure you want to delete ALL events in '{target_name}'?", default=False)
        if not confirmed:
            console.print("[yellow]Operation cancelled.[/yellow]")
            return 0

    console.print(f"[bold blue]Deleting all events from target calendar '{target_name}'...[/bold blue]")
    try:
        mac_client = MacCalendarClient()
        state_store = SyncStateStore(db_file)
        engine = SyncEngine(
            mac_client=mac_client,
            state_store=state_store,
            source_calendar_id=config.get("source_calendar_id", ""),
            target_calendar_id=target_id,
            source_calendar_name=config.get("source_calendar_name", "Source"),
            target_calendar_name=target_name
        )

        deleted_count = engine.clear_target_calendar()
        console.print(f"[bold green]Successfully deleted {deleted_count} events from '{target_name}'.[/bold green]")
        console.print(f"[dim]Mapping store '{db_file}' has been reset.[/dim]")
        return 0
    except Exception as e:
        console.print(f"[bold red]Error clearing target calendar:[/bold red] {e}")
        return 1


def cmd_find(args):
    """Search for a specific event title across ALL calendars on the Mac and Outlook using machine local time."""
    keyword = args.find or (args.keyword if hasattr(args, "keyword") else "")
    console.print(f"[bold blue]Searching across ALL Mac & Outlook calendars for events containing:[/] '[bold green]{keyword}[/]'...")

    now = datetime.now().astimezone()
    start_date = now - timedelta(days=3650)
    end_date = now + timedelta(days=3650)
    matches = []

    # Search EventKit
    try:
        client = MacCalendarClient()
        matches.extend(client.search_all_calendars(keyword, start_date, end_date))
    except Exception as e:
        logger_name = logging.getLogger("sync")
        logger_name.debug(f"EventKit search error: {e}")

    # Search Outlook
    try:
        from outlook_calendar import OutlookCalendarClient
        out_client = OutlookCalendarClient()
        if out_client.is_available():
            matches.extend(out_client.search_all_calendars(keyword, start_date, end_date))
    except Exception as e:
        logger_name = logging.getLogger("sync")
        logger_name.debug(f"Outlook search error: {e}")

    if not matches:
        console.print(f"[yellow]No events found matching '{keyword}' across any calendar on this Mac or Outlook.[/yellow]")
        return 0

    table = Table(title=f"Search Results for '{keyword}' ({len(matches)} found)")
    table.add_column("Account / Source", style="cyan")
    table.add_column("Calendar Name", style="bold yellow")
    table.add_column("Unique ID", style="dim")
    table.add_column("Local Time", style="green")
    table.add_column("Event Title", style="bold white")

    for ev in matches:
        start_str = ev["start"].strftime("%Y-%m-%d %H:%M") if ev.get("start") else "N/A"
        table.add_row(
            ev.get("calendar_source", "Local"),
            ev.get("calendar_name", "Unknown"),
            ev.get("calendar_id", "")[:18] + "...",
            start_str,
            ev["title"]
        )

    console.print(table)
    return 0


def cmd_dump_events(args):
    """Dump all events in source calendar ID to a file formatted with local machine time."""
    config = load_config()
    source_id = config.get("source_calendar_id")
    source_name = config.get("source_calendar_name", "Source")
    days_past = 3650 if args.all_time else (args.days_past or config.get("rolling_days_past", 365))
    days_future = 3650 if args.all_time else (args.days_future or config.get("rolling_days_future", 730))

    if not source_id:
        console.print("[bold red]Error: No source_calendar_id configured. Please run 'python3 sync.py --setup' first.[/bold red]")
        return 1

    output_file = "events_dump.txt"
    console.print(f"[bold blue]Dumping all events from '{source_name}' [ID: {source_id}] to '{output_file}'...[/bold blue]")

    if str(source_id).startswith("outlook:") or (str(source_id).isdigit() and len(str(source_id)) < 8):
        from outlook_calendar import OutlookCalendarClient
        client = OutlookCalendarClient()
    else:
        client = MacCalendarClient()

    now = datetime.now().astimezone()
    start_date = now - timedelta(days=days_past)
    end_date = now + timedelta(days=days_future)

    try:
        events = client.get_events_by_calendar_id(
            calendar_id=source_id,
            start_date=start_date,
            end_date=end_date
        )
    except Exception as e:
        console.print(f"[bold red]Error dumping events:[/bold red] {e}")
        return 1

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"=== EVENT DUMP FOR CALENDAR: '{source_name}' [ID: {source_id}] (Machine Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}) ===\n")
        f.write(f"Total events found: {len(events)}\n")
        f.write(f"Window: {start_date.strftime('%Y-%m-%d %H:%M')} to {end_date.strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"{'START LOCAL TIME':<22} | {'END LOCAL TIME':<22} | {'TITLE'}\n")
        f.write(f"{'-'*75}\n")
        for ev in events:
            s = ev["start"].strftime("%Y-%m-%d %H:%M") if ev.get("start") else "N/A"
            e = ev["end"].strftime("%Y-%m-%d %H:%M") if ev.get("end") else "N/A"
            f.write(f"{s:<22} | {e:<22} | {ev['title']}\n")

    console.print(f"[bold green]Dump complete![/] Found [bold]{len(events)}[/bold] events. Saved to [bold cyan]{output_file}[/bold cyan]")
    return 0


def cmd_sync(args):
    """Run a single synchronization pass using unique calendar IDs."""
    config = load_config()
    source_id = getattr(args, "source_id", None) or config.get("source_calendar_id")
    source_name = config.get("source_calendar_name", "Source")
    target_id = getattr(args, "target_id", None) or config.get("target_calendar_id")
    target_name = config.get("target_calendar_name", "Target")

    if not source_id or not target_id:
        console.print("[bold red]Error: source_calendar_id or target_calendar_id not configured.[/bold red]")
        console.print("Please run [bold cyan]python3 sync.py --setup[/bold cyan] to select your calendars.")
        return 1

    if source_id == target_id:
        console.print("[bold red]Error: Source and Target calendars cannot have the same unique ID.[/bold red]")
        return 1

    if getattr(args, "all_time", False):
        days_past = 3650
        days_future = 3650
    else:
        days_past = getattr(args, "days_past", None) or config.get("rolling_days_past", 365)
        days_future = getattr(args, "days_future", None) or config.get("rolling_days_future", 730)

    db_file = config.get("state_db_file", "sync_state.db")
    now = datetime.now().astimezone()
    is_dry_run = getattr(args, "dry_run", False)

    console.print(f"[{now.strftime('%Y-%m-%d %H:%M:%S %Z')}] Syncing: Source '[cyan]{source_name}[/]' -> Target '[cyan]{target_name}[/]'")
    console.print(f"Source ID: [dim]{source_id}[/dim]")
    console.print(f"Target ID: [dim]{target_id}[/dim]")
    console.print(f"Time Window: [dim]-{days_past}d to +{days_future}d[/dim]")

    if is_dry_run:
        console.print("[yellow bold][DRY RUN MODE - No changes will be written to target calendar][/yellow bold]")

    try:
        mac_client = MacCalendarClient()
        state_store = SyncStateStore(db_file)

        engine = SyncEngine(
            mac_client=mac_client,
            state_store=state_store,
            source_calendar_id=source_id,
            target_calendar_id=target_id,
            source_calendar_name=source_name,
            target_calendar_name=target_name,
            days_past=days_past,
            days_future=days_future
        )

        stats = engine.sync(dry_run=is_dry_run)

        table = Table(title=f"Sync Results ({now.strftime('%Y-%m-%d %H:%M:%S %Z')})")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="bold green")

        table.add_row("Total Source Events in Window", str(stats["total_source_events"]))
        table.add_row("New Events Created in Target", str(stats["created"]))
        table.add_row("Modified Events Updated in Target", str(stats["updated"]))
        table.add_row("Deleted Events Removed from Target", str(stats["deleted"]))
        table.add_row("Unchanged Events", str(stats["unchanged"]))

        console.print(table)
        console.print(f"[dim]Detailed audit log written to: [bold cyan]{stats['log_file']}[/bold cyan][/dim]")
        console.print("[bold green]Sync completed successfully![/bold green]")
        return 0
    except Exception as e:
        console.print(f"[bold red]Sync error:[/bold red] {e}")
        return 1


def cmd_daemon(args):
    """Run continuously in the foreground/background at the configured interval."""
    config = load_config()
    interval_minutes = getattr(args, "interval", None) or config.get("sync_interval_minutes", 15)
    interval_seconds = max(60, interval_minutes * 60)

    now = datetime.now().astimezone()
    console.print(Panel.fit(
        f"[bold green]Calendar Sync Daemon Started[/bold green]\n"
        f"Machine Reference Time: [bold yellow]{now.strftime('%Y-%m-%d %H:%M:%S %Z')}[/bold yellow]\n"
        f"Sync Interval: Every [bold]{interval_minutes}[/bold] minutes\n"
        f"Source Calendar: [bold cyan]{config.get('source_calendar_name', 'Work')}[/bold cyan] [ID: {config.get('source_calendar_id', '')}]\n"
        f"Target Calendar: [bold cyan]{config.get('target_calendar_name', 'Gmail - Work')}[/bold cyan] [ID: {config.get('target_calendar_id', '')}]\n"
        f"Press [bold red]Ctrl+C[/bold red] to stop.",
        title="Daemon Active"
    ))

    while True:
        try:
            cmd_sync(args)
        except Exception as e:
            console.print(f"[bold red]Daemon error during sync:[/bold red] {e}")

        next_time = (datetime.now().astimezone() + timedelta(seconds=interval_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        console.print(f"\n[dim]Next sync scheduled in {interval_minutes} minutes (around {next_time}). Sleeping...[/dim]\n")
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            console.print("\n[yellow]Daemon stopped by user.[/yellow]")
            break
    return 0


def cmd_log(args):
    """Display the recent events audit log."""
    if os.path.exists(SYNC_LOG_FILE):
        with open(SYNC_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        tail_lines = lines[-args.lines:] if len(lines) > args.lines else lines
        console.print("".join(tail_lines))
    else:
        console.print(f"[yellow]No log file found at {SYNC_LOG_FILE} yet. Run python3 sync.py --sync first.[/yellow]")
    return 0


def cmd_reset_state(args):
    """Reset the local sync mapping database."""
    config = load_config()
    db_file = config.get("state_db_file", "sync_state.db")
    if os.path.exists(db_file):
        os.remove(db_file)
        console.print(f"[bold green]Reset complete:[/] Removed '{db_file}'. Next sync will perform a fresh re-scan.")
    else:
        console.print("[yellow]No sync state file found to reset.[/yellow]")
    return 0


def cmd_install_service(args):
    """Install and start the macOS launchd background agent."""
    config = load_config()
    interval = config.get("sync_interval_minutes", 15)
    python_path = sys.executable
    project_dir = os.path.abspath(os.path.dirname(__file__))

    manager = LaunchdManager(project_dir=project_dir, python_path=python_path, interval_minutes=interval)
    try:
        plist_path = manager.install()
        console.print(f"[bold green]LaunchAgent successfully installed and loaded![/bold green]")
        console.print(f"Plist Location: [dim]{plist_path}[/dim]")
        console.print(f"Sync Interval: Every [bold]{interval}[/bold] minutes")
        console.print(f"Logs: [dim]{manager.stdout_log}[/dim]")
        return 0
    except Exception as e:
        console.print(f"[bold red]Failed to install background service:[/bold red] {e}")
        return 1


def cmd_uninstall_service(args):
    """Uninstall the macOS launchd background agent."""
    python_path = sys.executable
    project_dir = os.path.abspath(os.path.dirname(__file__))
    manager = LaunchdManager(project_dir=project_dir, python_path=python_path)
    if manager.uninstall():
        console.print("[bold green]Background sync service uninstalled successfully.[/bold green]")
    else:
        console.print("[yellow]Background service was not installed.[/yellow]")
    return 0


def cmd_status(args):
    """Show service and sync status."""
    config = load_config()
    db_file = config.get("state_db_file", "sync_state.db")
    state_store = SyncStateStore(db_file)
    last_sync = state_store.get_meta("last_sync_time") or "Never"
    saved_src = f"{config.get('source_calendar_name', 'None')} [ID: {config.get('source_calendar_id', '')}]"
    saved_tgt = f"{config.get('target_calendar_name', 'None')} [ID: {config.get('target_calendar_id', '')}]"

    python_path = sys.executable
    project_dir = os.path.abspath(os.path.dirname(__file__))
    manager = LaunchdManager(project_dir=project_dir, python_path=python_path)
    status = manager.get_status()

    table = Table(title="Sync & Background Service Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold")

    table.add_row("Source Calendar", saved_src)
    table.add_row("Target Gmail Calendar", saved_tgt)
    table.add_row("Last Sync Timestamp", str(last_sync))
    table.add_row("Launchd Agent Installed", "[green]Yes[/green]" if status["installed"] else "[red]No[/red]")
    table.add_row("Launchd Agent Loaded", "[green]Yes[/green]" if status["loaded"] else "[red]No[/red]")
    table.add_row("Audit Log", SYNC_LOG_FILE)
    table.add_row("Service Stdout Log", status["log_path"])

    console.print(table)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Sync between calendars inside macOS Calendar app (Source -> Gmail)")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # list-calendars
    subparsers.add_parser("list-calendars", help="List all macOS calendars available with event counts and IDs")

    # setup
    subparsers.add_parser("setup", help="Interactive configuration wizard using unique IDs")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Run sync between Source and Target calendars")
    sync_parser.add_argument("--source-id", type=str, help="Override source calendar unique ID")
    sync_parser.add_argument("--target-id", type=str, help="Override target calendar unique ID")
    sync_parser.add_argument("--days-past", type=int, help="Override rolling past days")
    sync_parser.add_argument("--days-future", type=int, help="Override rolling future days")
    sync_parser.add_argument("--all-time", action="store_true", help="Sync all events across 10 years past & future")
    sync_parser.add_argument("--dry-run", action="store_true", help="Calculate diff without applying changes")

    # daemon
    daemon_parser = subparsers.add_parser("daemon", help="Run sync continuously in the background")
    daemon_parser.add_argument("--interval", type=int, help="Interval in minutes between syncs (default: 15)")
    daemon_parser.add_argument("--all-time", action="store_true", help="Sync all events across 10 years past & future")

    # clear-target
    clear_parser = subparsers.add_parser("clear-target", help="Delete ALL events in target calendar ID")
    clear_parser.add_argument("-y", "--yes", action="store_true", help="Confirm deletion without prompting")

    # find
    find_parser = subparsers.add_parser("find", help="Search for an event across ALL calendars on Mac")
    find_parser.add_argument("keyword", type=str, help="Event title keyword to search for")

    # dump-events
    dump_parser = subparsers.add_parser("dump-events", help="Dump all events in source calendar to a file")
    dump_parser.add_argument("--all-time", action="store_true", help="Dump all events across 10 years")

    # log
    log_parser = subparsers.add_parser("log", help="Display recent events audit log")
    log_parser.add_argument("-n", "--lines", type=int, default=100, help="Number of lines to show")

    # reset-state
    subparsers.add_parser("reset-state", help="Reset local sync state database")

    # install-service
    subparsers.add_parser("install-service", help="Install macOS launchd background agent")

    # uninstall-service
    subparsers.add_parser("uninstall-service", help="Uninstall macOS launchd background agent")

    # status
    subparsers.add_parser("status", help="Check current sync status and background agent")

    # app / gui
    subparsers.add_parser("app", help="Launch native macOS menu bar app")
    subparsers.add_parser("gui", help="Launch native macOS menu bar app")

    # Direct flag support
    parser.add_argument("--list-calendars", action="store_true", help="List all macOS calendars")
    parser.add_argument("--setup", action="store_true", help="Run setup wizard")
    parser.add_argument("--app", action="store_true", help="Launch native macOS menu bar app")
    parser.add_argument("--gui", action="store_true", help="Launch native macOS menu bar app")
    parser.add_argument("--sync", action="store_true", help="Run sync")
    parser.add_argument("--daemon", action="store_true", help="Run sync daemon in loop")
    parser.add_argument("--interval", type=int, help="Interval in minutes for daemon")
    parser.add_argument("--clear-target", action="store_true", help="Delete ALL events in target calendar")
    parser.add_argument("-y", "--yes", action="store_true", help="Confirm deletion without prompting")
    parser.add_argument("--days-past", type=int, help="Override rolling past days")
    parser.add_argument("--days-future", type=int, help="Override rolling future days")
    parser.add_argument("--all-time", action="store_true", help="Sync all events across 10 years past & future")
    parser.add_argument("--find", type=str, help="Search for event across all Mac calendars")
    parser.add_argument("--dump-events", action="store_true", help="Dump all events in source calendar to text file")
    parser.add_argument("--log", action="store_true", help="View recent audit log")
    parser.add_argument("-n", "--lines", type=int, default=100, help="Lines to show for --log")
    parser.add_argument("--reset-state", action="store_true", help="Reset local sync state database")
    parser.add_argument("--dry-run", action="store_true", help="Preview sync changes without modifying target calendar")
    parser.add_argument("--install-service", action="store_true", help="Install background daemon")
    parser.add_argument("--uninstall-service", action="store_true", help="Uninstall background daemon")
    parser.add_argument("--status", action="store_true", help="Show status")

    args = parser.parse_args()

    if args.app or args.gui or args.command in ("app", "gui"):
        from gui_app import main as gui_main
        return gui_main()
    elif args.list_calendars or args.command == "list-calendars":
        return cmd_list_calendars(args)
    elif args.setup or args.command == "setup":
        return cmd_setup(args)
    elif args.clear_target or args.command == "clear-target":
        return cmd_clear_target(args)
    elif args.find or args.command == "find":
        if args.command == "find":
            args.find = args.keyword
        return cmd_find(args)
    elif args.dump_events or args.command == "dump-events":
        return cmd_dump_events(args)
    elif args.log or args.command == "log":
        return cmd_log(args)
    elif args.reset_state or args.command == "reset-state":
        return cmd_reset_state(args)
    elif args.daemon or args.command == "daemon":
        return cmd_daemon(args)
    elif args.install_service or args.command == "install-service":
        return cmd_install_service(args)
    elif args.uninstall_service or args.command == "uninstall-service":
        return cmd_uninstall_service(args)
    elif args.status or args.command == "status":
        return cmd_status(args)
    elif args.sync or args.command == "sync":
        return cmd_sync(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
