import os

import pytest

from flowgit.core.repository import Repository


class TestInit:

    def test_initalize_flowgit_creates_expected_directory_structure(self, repo):
        assert os.path.isdir(os.path.join(repo.flowgit_directory, "objects"))
        assert os.path.isdir(os.path.join(repo.flowgit_directory, "refs", "heads"))
        assert os.path.isfile(os.path.join(repo.flowgit_directory, "HEAD"))
        assert os.path.isfile(os.path.join(repo.flowgit_directory, "config"))

    def test_initalize_flowgit_default_head_points_to_main(self, repo):
        head_content = open(os.path.join(repo.flowgit_directory, "HEAD")).read()
        assert head_content == "ref: refs/heads/main"

    def test_initalize_flowgit_writes_config_with_identity(self, repo):
        config = repo.config.get_config()
        assert config['user']['name'] == "testuser"
        assert config['user']['email'] == "test@example.com"

    def test_initalize_flowgit_without_replace_is_a_noop_on_existing_repo(self, repo, tmp_path):
        # calling again on an already-initialized repo, without replace=True,
        # should just warn and return rather than raising or wiping anything
        repo.initalize_flowgit()
        assert os.path.isdir(repo.flowgit_directory)
        assert os.path.isfile(os.path.join(repo.flowgit_directory, "HEAD"))

    def test_initalize_flowgit_raises_on_nonexistent_path(self, tmp_path, fixed_identity):
        missing = tmp_path / "does-not-exist"
        repository = Repository(str(missing))
        with pytest.raises(NotADirectoryError):
            repository.initalize_flowgit()

    def test_initalize_flowgit_replace_true_reinitializes_existing_repo(self, repo, tmp_path, monkeypatch, fixed_identity):
        monkeypatch.chdir(tmp_path)
        repository = Repository(str(tmp_path), replace=True)
        repository.initalize_flowgit()
        assert os.path.isdir(repository.flowgit_directory)
