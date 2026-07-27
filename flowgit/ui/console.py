import os

from rich.text import Text
from rich.panel import Panel
from rich.style import Style
from rich.console import Group
from rich import print as rprint
from rich.padding import Padding

from flowgit.ui.colors import Colors

def _clear_console():
    os.system(
        'cls' if os.name == 'nt' else 'clear'
    )


def display_warning_message(message: str):
    mark = "⚠️"
    rprint(f"{mark}  {message}")

def display_creation_message(message: str):
    string = f"[bold][{Colors.GREEN.value}]:heavy_check_mark:[/{Colors.GREEN.value}] [white]Created[/white] [{Colors.DARK_BLUE.value}]{message}[/{Colors.DARK_BLUE.value}] [white][/white][/bold]"
    rprint(string)

def display_error_message(message: str):
    string = f"[bold][{Colors.RED.value}]:cross_mark: {message}[/{Colors.RED.value}][/bold]"
    rprint(string)

def display_success_message(message: str):
    string = f"[bold][{Colors.GREEN.value}]:heavy_check_mark:[/{Colors.GREEN.value}] {message} [white][/white][/bold]"
    rprint(string)

def display_information_message(message: str):
    string = f"[bold][{Colors.GREEN.value}]:information:[/{Colors.GREEN.value}] {message} [white][/white][/bold]"
    rprint(string)

def display_command_header():
    _clear_console()
    panel_group = Group(
        Padding(Text("flowgit", style=Style(color=Colors.DARK_BLUE)), (0, 0, 1, 0)),
        Text("FlowGit v1.0.0 - Custom version control software", style=Style(color=Colors.WHITE))
    )
    rprint(Panel(panel_group, border_style=Style(color=Colors.DARK_BLUE)))