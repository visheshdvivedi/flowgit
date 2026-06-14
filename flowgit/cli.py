import os
from pathlib import Path
from typer import Typer, Argument, Option
from typing import Annotated, List

from flowgit.core.objects.object import ObjectType
from flowgit.core.repository import Repository
from flowgit.ui.console import (
    display_command_header,
    display_error_message
)

app = Typer(
    name = "flowgit",
    help = "Version control software built as part of flowverse",
    add_completion = True,
    rich_markup_mode = "rich",
    no_args_is_help = True,
)
repository = Repository(os.getcwd())


@app.command()
def init(
    path: Annotated[str, Option(
        "-p", "--path",
        help="Path where to initialize the git repository. (default: .)"
    )] = "."
):
    """
    Creates an empty git repository, .flowgit with subdirectories for [bold]objects, refs/heads, refs/tags[/bold] and [bold]config[/bold] file.
    """
    display_command_header()
    repository.initalize_flowgit()

@app.command()
def hash_object(
    path: str = Argument(
        help="Path of the file to read"
    ),
    type: Annotated[ObjectType, Option(
        "-t", "--type",
        help="Specify the type of object to be created (default: \"blob\"). Possible values are [bold]commit, tree, blob[/bold] and [bold]tag[/bold]."
    )] = ObjectType.blob,
    write: Annotated[bool, Option(
        "-w",
        help = "Actually write the object into the object database."
    )] = False
):
    """
    Compute object ID and optionally create an object from a file
    """
    display_command_header()

    # ensure file exists
    file_path = Path(path).resolve()
    if not os.path.exists(file_path):
        display_error_message(f"File path {file_path} not found")
        return
    
    # read file content
    content = bytes()
    with open(file_path, "rb") as file:
        content = file.read()

    repository.hash_object(content, type, write)

@app.command()
def cat_file(
    object: str = Argument(
        help="The name of the object to show."
    )
):
    """
    Inspect type, size or content of any stored object by hash
    """
    display_command_header()
    repository.read_object(object)

@app.command()
def maketree(
    entries: Annotated[List[str], Option(
        "-e", "--entry",
        help="A tree entry in format '<mode> <type> <name> <hash>'"
    )]
):
    """
    Build a tree object from a ls-tree-format input
    """
    display_command_header()
    content = "\n".join(entries)
    repository.make_tree(content)

@app.command()
def commit_tree(
    tree: str = Argument(
        help = "An existing tree object."
    ),
    parent: Annotated[str, Option(
        "-p", "--parent",
        help = "Specify the hash of the parent object. (default: "")"
    )] = "",
    message: Annotated[str, Option(
        "-m", "--message",
        help = "Pass on a human readable message. (default: "")"
    )] = "",
):
    """
    Create a commit object from a tree SHA + parent + message
    """
    display_command_header()
    repository.commit_tree(tree, parent, message)

@app.command()
def maketag(
    object: str = Argument(
        help = "The object to be tagged"
    ),
    type: str = Argument(
        help = "The type of the object being tagged"
    ),
    name: str = Argument(
        help = "The name of the tag"
    ),
    message: Annotated[str, Option(
        "-m", "--message",
        help = "Pass on a human readable message. (default: "")"
    )] = "",
):
    """
    Create a new tag object from stdin (validated format)
    """
    display_command_header()
    repository.make_tag(object, type, name, message)