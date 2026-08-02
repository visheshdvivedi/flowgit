import os
import subprocess

import pytest

import flowgit.services.config as config_module
from flowgit.core.repository import Repository


@pytest.fixture
def fixed_identity(monkeypatch):
    """
    Prevent FlowGitConfigManager.initialize_config() from blocking on real
    stdin during tests. config.py imports ask_username/ask_email via
    `from flowgit.ui.prompt import ...`, so the names must be patched on
    config_module itself, not on flowgit.ui.prompt.
    """
    # Deliberately a single token: commit.py's deserialize() splits the
    # "author <name> <email> <ts> <tz>" line with a bare line.split(b" ")
    # (no maxsplit), so a multi-word name shifts every subsequent field -
    # see BUG-11. Using "testuser" here keeps that unrelated bug from
    # contaminating every other repository-level test; BUG-11 itself gets
    # its own isolated regression test.
    monkeypatch.setattr(config_module, "ask_username", lambda: "testuser")
    monkeypatch.setattr(config_module, "ask_email", lambda: "test@example.com")


@pytest.fixture
def repo(tmp_path, monkeypatch, fixed_identity):
    """
    An initialized Repository rooted at tmp_path, with cwd chdir'd to match.

    Repository internally mixes self.path-relative and bare-cwd-relative
    paths in several methods (restore(), diff(), update_index()'s add loop,
    _get_unstaged_changes_status()) - it implicitly assumes
    self.path == os.getcwd(). Every fixture that builds a Repository must
    preserve that invariant, or unrelated tests fail for cwd reasons instead
    of the thing actually being tested.
    """
    monkeypatch.chdir(tmp_path)
    repository = Repository(str(tmp_path))
    repository.initalize_flowgit()
    return repository


@pytest.fixture
def make_file(tmp_path):
    def _make_file(relpath, content="", binary=False):
        full_path = tmp_path / relpath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if binary:
            full_path.write_bytes(content)
        else:
            full_path.write_text(content)
        return relpath
    return _make_file


@pytest.fixture
def bare_remote(tmp_path):
    """
    A local bare git repo usable as a real push/fetch/pull target, without
    needing network access. push/fetch/pull/remote are implemented by
    shelling out to the real git binary against .flowgit (now a valid
    git-dir), so testing them for real - rather than mocking subprocess -
    is both possible and far higher-signal.
    """
    remote_path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_path)], check=True, capture_output=True)
    return str(remote_path)


@pytest.fixture
def make_commit(repo, make_file):
    """
    Factory: make_commit({relpath: content, ...}, "message") -> commit sha
    """
    def _make_commit(files: dict, message: str) -> str:
        paths = []
        for relpath, content in files.items():
            make_file(relpath, content)
            paths.append(relpath)
        repo.add(paths)
        repo.commit(message)
        return repo._resolve_head()
    return _make_commit


@pytest.fixture
def remote_repo(tmp_path_factory, fixed_identity):
    """
    A second, fully independent flowgit repo at its own temp directory,
    acting as a filesystem "remote" for fetch/pull/push tests. Uses plain
    os.chdir with an explicit restore (not monkeypatch.chdir) so its own
    init doesn't fight over cwd with whatever the `repo` fixture sets for
    the local side in the same test - by the time this fixture returns, cwd
    is back to whatever it was before, so fixture ordering doesn't matter.
    """
    remote_dir = tmp_path_factory.mktemp("remote")
    remote = Repository(str(remote_dir))

    original_cwd = os.getcwd()
    os.chdir(remote_dir)
    try:
        remote.initalize_flowgit()
    finally:
        os.chdir(original_cwd)

    return remote


@pytest.fixture
def make_remote_commit(remote_repo):
    """
    Factory: make_remote_commit({relpath: content, ...}, "message") -> sha
    Builds a commit directly on remote_repo, bracketing the chdir so it
    doesn't leak into the rest of the test (add()/commit() require
    self.path == os.getcwd()).
    """
    def _make_remote_commit(files: dict, message: str) -> str:
        original_cwd = os.getcwd()
        os.chdir(remote_repo.path)
        try:
            for relpath, content in files.items():
                full_path = os.path.join(remote_repo.path, relpath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w") as f:
                    f.write(content)
            remote_repo.add(list(files.keys()))
            remote_repo.commit(message)
            return remote_repo._resolve_head()
        finally:
            os.chdir(original_cwd)
    return _make_remote_commit


@pytest.fixture
def clone_from_remote(tmp_path_factory, monkeypatch):
    """
    Factory: clone_from_remote(remote_repo) -> a fresh local Repository,
    genuinely cloned from remote_repo (which must already have at least one
    commit), with cwd chdir'd to match. Real shared history, not two
    independently-built commits that only coincidentally hash the same.

    Calls _clone_filesystem_repository() directly rather than the public
    clone() wrapper, since clone() checks Path.cwd() instead of the target
    directory explicitly - calling the internal method sidesteps that,
    exercising the actual clone logic under test either way.
    """
    def _clone(remote_repo: "Repository") -> "Repository":
        local_dir = tmp_path_factory.mktemp("local_clone")
        monkeypatch.chdir(local_dir)
        local = Repository(str(local_dir))
        local._clone_filesystem_repository(remote_repo.path)
        return local
    return _clone
