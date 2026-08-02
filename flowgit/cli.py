import os
from pathlib import Path
from typer import Typer, Argument, Option
from typing import Annotated, List, Optional

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
def ignored():
    """
    Return list of ignored files as per .gitignore
    """
    display_command_header()
    repository.ignored()

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
    parents: Annotated[List[str], Option(
        "-p", "--parent",
        help="Specify the parent(s) for the commit"
    )] = [],
    message: Annotated[str, Option(
        "-m", "--message",
        help = "Pass on a human readable message. (default: "")"
    )] = "",
):
    """
    Create a commit object from a tree SHA + parent(s) + message
    """
    display_command_header()
    repository.commit_tree(tree, parents, message)

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


@app.command()
def update_index(
    add: Annotated[List[str], Option(
        "-a", "--add",
        help="Add new files to the index"
    )] = [],
    remove: Annotated[List[str], Option(
        "-r", "--remove",
        help="Remove existing files from the index"
    )] = [],
    info: Annotated[bool, Option(
        "--index-info",
        help = "Read index information from stdin",
    )] = False,
    list_entries: Annotated[bool, Option(
        "--list",
        help = "List entries from the index file"
    )] = False
):
    """
    Modifies the index. Each file mentioned is updated into the index and any unmerged or needs updating state is cleared.
    """
    display_command_header()
    repository.update_index(add, remove, info, list_entries)


@app.command()
def write_tree():
    """
    Creates a tree object using the current index. The name of the new tree object is printed to standard output.
    """
    display_command_header()
    repository.write_tree()


@app.command()
def update_ref(
    ref_path: str = Argument(
        help = "Path to the reference where to write"
    ),
    sha: str = Argument(
        help = "SHA of the commit object"
    )
):
    """
    Update reference to a specific branch
    """
    display_command_header()
    repository.update_ref(ref_path, sha)


@app.command()
def read_tree(
    sha: str = Argument(
        help = "SHA of the tree object to populate the index from"
    )
):
    """
    Reads the files from the tree object and adds the files to the index
    """
    display_command_header()
    repository.read_tree(sha)


@app.command()
def checkout_index(
    files: Annotated[Optional[List[str]], Argument(
        help="Specific files to checkout from the index"
    )] = None,
    all: Annotated[bool, Option(
        "-a", "--all",
        help = "Write out all entries in the index file"
    )] = False,
    force: Annotated[bool, Option(
        "-f", "--force",
        is_flag=True,
        help = "overwrite existing files, by default skips files that already exists"
    )] = False
):
    """
    Writes files from the index to the current directory
    """
    display_command_header()
    repository.checkout_index(files or [], all, force)


@app.command()
def checkout(
    hash: str = Argument(
        help = "The hash of the commit to checkout back to"
    )
):
    """
    Return back to previous commit
    """
    display_command_header()
    repository.checkout(hash)


@app.command()
def add(
    files: list[str] = Argument(
        help = "Files to the added to staging"
    )
):
    """
    Adds files to staging index file
    """
    display_command_header()
    repository.add(files)


@app.command()
def commit(
    message: Annotated[str, Option(
        "-m", "--message",
        help = "Message to specify in the commit"
    )] = ""
):
    """
    Creates a commit for all files in staging
    """
    display_command_header()
    repository.commit(message)


@app.command()
def branch(
    new_branch_name: Annotated[Optional[str], Argument(
        help = "Name of the branch to create"
    )] = "",
    delete_branch_name: Annotated[str, Option(
        "-d", "--delete",
        help = "Specify the branch to delete"
    )] = ""
):
    """
    Allows to list, create or delete branches
    """
    display_command_header()
    repository.branch(new_branch_name, delete_branch_name)


@app.command()
def switch(
    branch_name: str = Argument(
        help = "The name of the branch to switch to"
    )
):
    """
    Switch between different branches
    """
    display_command_header()
    repository.switch(branch_name)


@app.command()
def log():
    """
    Display commit history for current branch
    """
    display_command_header()
    repository.log()


@app.command()
def status():
    """
    Display current branch status
    """
    display_command_header()
    repository.status()


@app.command()
def restore(
    staged: Annotated[bool, Option(
        "-s", "--staged",
        is_flag=True,
        help = "To restore working tree from last commit"
    )] = False
):
    """
    Restore working tree to either index or last commit
    """
    display_command_header()
    repository.restore(staged)


@app.command()
def diff(
    staged: Annotated[bool, Option(
        "-s", "--staged",
        is_flag=True,
        help = "To restore working tree from last commit"
    )] = False
):
    """
    Compares file contents line by line to show changes
    """
    display_command_header()
    repository.diff(staged)


@app.command()
def merge(
    branch_name: str = Argument(
        help = "The name of the branch to switch to"
    )
):
    """
    Merge changes from the provided branch to the current branch
    """
    display_command_header()
    repository.merge(branch_name)


@app.command()
def remote(
    action: Annotated[str, Argument(
        help = "add | remove | list | get-url | set-url"
    )] = "list",
    name: Annotated[str, Argument(
        help = "Remote name"
    )] = "",
    url: Annotated[str, Argument(
        help = "Remote URL (required for 'add')"
    )] = "",
):
    """
    Manage remotes: add, remove, or list
    """
    display_command_header()
    repository.remote(action, name, url)


@app.command(name="config")
def config_command(
    key: str = Argument(
        help = "Config key in '<section>.<key>' format, e.g. 'user.name'"
    ),
    value: Annotated[Optional[str], Argument(
        help = "Value to set; omit to read the current value"
    )] = None,
):
    """
    Get or set a flowgit config value (e.g. user.name, user.email)
    """
    display_command_header()

    if "." not in key:
        display_error_message("Config key must be in '<section>.<key>' format, e.g. 'user.name'")
        return

    section, config_key = key.split(".", 1)

    if value is None:
        current = repository.config.get_value(section, config_key)
        if current is None:
            display_error_message(f"'{key}' is not set")
        else:
            print(current)
    else:
        repository.config.set_value(section, config_key, value)


@app.command(name="clone")
def clone_repository(
    url: str = Argument(
        help = "Filesystem or https url of the repository to clone"
    ),
):
    """
    Clones a repository from its filesystem path or HTTPs path
    """
    display_command_header()
    repository.clone(url)


@app.command(name="fetch")
def fetch_remote(
    remote: Annotated[str, Argument(
        help = "The remote to fetch from"
    )] = "origin"
):
    """
    Fetches the new changes from remote and update in local refs/remotes/origin/<branch>
    """
    display_command_header()
    repository.fetch_remote(remote)


@app.command(name="pull")
def pull_remote(
    remote: Annotated[str, Argument(
        help = "The remote to pull from"
    )] = "origin",
    branch: Annotated[str, Argument(
        help = "The branch to pull"
    )] = "main"
):
    """
    Apply the changes fetched from fetch locally
    """
    display_command_header()
    repository.pull_remote(remote, branch)


@app.command(name="push")
def push_remote(
    remote: Annotated[str, Argument(
        help = "The remote to pull from"
    )] = "origin",
    branch: Annotated[str, Argument(
        help = "The branch to pull"
    )] = "main"
):
    """
    Push the local commited changes to remote repository
    """
    display_command_header()
    repository.push_to_remote(remote, branch)