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
