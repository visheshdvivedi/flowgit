import os

import pytest

from flowgit.core.objects import read_index
from flowgit.core.repository import Repository


class TestUpdateIndex:

    def test_add_single_new_file_stages_it(self, repo, make_file):
        make_file("a.txt", "aaa")
        added, removed = repo.update_index(["a.txt"], [], False, False)
        assert added == 1
        assert removed == 0

        entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        assert [e.path for e in entries] == ["a.txt"]

    def test_add_unmodified_existing_entry_is_not_recounted(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.update_index(["a.txt"], [], False, False)
        added, removed = repo.update_index(["a.txt"], [], False, False)
        assert added == 0

        entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        assert len(entries) == 1

    def test_add_modified_existing_entry_updates_sha(self, repo, make_file):
        make_file("a.txt", "version 1")
        repo.update_index(["a.txt"], [], False, False)
        first_entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        first_sha = first_entries[0].sha1

        make_file("a.txt", "version 2, much longer content so size differs")
        repo.update_index(["a.txt"], [], False, False)
        second_entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        assert len(second_entries) == 1
        assert second_entries[0].sha1 != first_sha

    def test_remove_existing_entry(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.update_index(["a.txt"], [], False, False)
        added, removed = repo.update_index([], ["a.txt"], False, False)
        assert removed == 1

        entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        assert entries == []

    def test_info_and_list_mutually_exclusive(self, repo):
        result = repo.update_index([], [], True, True)
        assert result is None

    def test_add_works_when_repository_path_differs_from_cwd(self, tmp_path, monkeypatch, fixed_identity):
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repository = Repository(str(repo_dir))
        monkeypatch.chdir(repo_dir)
        repository.initalize_flowgit()

        (repo_dir / "a.txt").write_text("aaa")

        # deliberately do NOT chdir into repo_dir for this call, to prove the
        # bug is fixed: self.path is repo_dir, but cwd is something else
        # entirely.
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        added, removed = repository.update_index(["a.txt"], [], False, False)
        assert added == 1

        # the stored path must stay relative to the repo root, not absolute,
        # even though we had to read the file from an absolute path
        entries = read_index(os.path.join(repository.flowgit_directory, "index"))
        assert [e.path for e in entries] == ["a.txt"]


class TestReadTreeCheckoutIndex:

    def test_read_tree_populates_index_from_tree_sha(self, repo, make_file):
        make_file("a.txt", "aaa")
        make_file("b.txt", "bbb")
        repo.add(["a.txt", "b.txt"])
        tree_sha = repo.write_tree()

        # wipe index, then reload it from the tree
        os.remove(os.path.join(repo.flowgit_directory, "index"))
        repo.read_tree(tree_sha)

        entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        assert sorted(e.path for e in entries) == ["a.txt", "b.txt"]

    def test_read_tree_nested_directories_produce_full_relative_paths(self, repo, make_file):
        make_file("dir/sub/deep.txt", "deep content")
        repo.add(["dir/sub/deep.txt"])
        tree_sha = repo.write_tree()

        os.remove(os.path.join(repo.flowgit_directory, "index"))
        repo.read_tree(tree_sha)

        entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        assert [e.path for e in entries] == ["dir/sub/deep.txt"]

    def test_checkout_index_writes_missing_files_to_disk(self, repo, make_file):
        make_file("a.txt", "original content")
        repo.add(["a.txt"])

        os.remove("a.txt")
        repo.checkout_index([], True, False)

        assert open("a.txt").read() == "original content"

    def test_checkout_index_force_overwrites_existing_modified_file(self, repo, make_file):
        make_file("a.txt", "original content")
        repo.add(["a.txt"])

        make_file("a.txt", "locally changed, not re-added")
        repo.checkout_index([], True, True)

        assert open("a.txt").read() == "original content"

    def test_checkout_index_without_force_skips_existing_file(self, repo, make_file):
        make_file("a.txt", "original content")
        repo.add(["a.txt"])

        make_file("a.txt", "locally changed")
        repo.checkout_index([], True, False)

        assert open("a.txt").read() == "locally changed"
