import os

import pytest


class TestAddCommit:

    def test_add_single_file_stages_it(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        new_files, modified_files, deleted_files = repo._get_staged_changes_status()
        assert new_files == ["a.txt"]

    def test_add_dot_stages_all_files_recursively(self, repo, make_file):
        make_file("a.txt", "aaa")
        make_file("dir/b.txt", "bbb")
        repo.add(["."])
        new_files, _, _ = repo._get_staged_changes_status()
        assert sorted(new_files) == ["a.txt", "dir/b.txt"]

    def test_commit_creates_commit_and_moves_branch_ref(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        repo.commit("first commit")

        head_sha = repo._resolve_head()
        assert head_sha is not None
        commit_obj = repo.read_object(head_sha, display_info=False)
        assert commit_obj.message.strip("\n") == "first commit"
        assert commit_obj.parent == []

    def test_second_commit_has_first_as_parent(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        repo.commit("first")
        first_sha = repo._resolve_head()

        make_file("a.txt", "aaa updated")
        repo.add(["a.txt"])
        repo.commit("second")
        second_sha = repo._resolve_head()

        commit_obj = repo.read_object(second_sha, display_info=False)
        assert commit_obj.parent == [first_sha]
        assert second_sha != first_sha


class TestStatus:

    def test_status_reports_untracked_file(self, repo, make_file):
        make_file("a.txt", "aaa")
        _, modified, deleted = repo._get_staged_changes_status()
        untracked, _, _ = repo._get_unstaged_changes_status()
        assert untracked == ["a.txt"]

    def test_status_reports_staged_new_file(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        new_files, _, _ = repo._get_staged_changes_status()
        assert new_files == ["a.txt"]

    def test_status_reports_modified_staged_file_vs_last_commit(self, repo, make_file):
        make_file("a.txt", "version 1, padded so the size differs from v2")
        repo.add(["a.txt"])
        repo.commit("initial")

        make_file("a.txt", "totally different second version")
        repo.add(["a.txt"])
        _, modified_files, _ = repo._get_staged_changes_status()
        assert modified_files == ["a.txt"]

    def test_add_restages_same_size_edit_within_same_second(self, repo, make_file):
        make_file("a.txt", "version 1")
        repo.add(["a.txt"])
        repo.commit("initial")

        make_file("a.txt", "version 2")  # same byte length as "version 1"
        repo.add(["a.txt"])
        _, modified_files, _ = repo._get_staged_changes_status()
        assert modified_files == ["a.txt"]

    def test_status_clean_working_tree_reports_nothing(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        repo.commit("initial")

        new_files, modified_files, deleted_files = repo._get_staged_changes_status()
        untracked, unstaged_modified, unstaged_deleted = repo._get_unstaged_changes_status()
        assert not (new_files or modified_files or deleted_files)
        assert not (untracked or unstaged_modified or unstaged_deleted)

    def test_unstaged_status_respects_repository_path_not_just_cwd(self, repo, make_file, tmp_path, monkeypatch):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        repo.commit("initial")

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        untracked, modified, deleted = repo._get_unstaged_changes_status()
        assert deleted == []


class TestDiffRestore:

    def test_diff_unstaged_shows_change(self, repo, make_file, capsys):
        make_file("a.txt", "line one\n")
        repo.add(["a.txt"])
        repo.commit("initial")

        make_file("a.txt", "line one\nline two\n")
        repo.diff(staged=False)
        captured = capsys.readouterr()
        assert "line two" in captured.out

    def test_restore_unstaged_reverts_to_index_version(self, repo, make_file):
        make_file("a.txt", "original")
        repo.add(["a.txt"])

        make_file("a.txt", "locally modified")
        repo.restore(staged=False)

        assert open("a.txt").read() == "original"

    def test_restore_staged_reverts_to_last_commit_version(self, repo, make_file):
        make_file("a.txt", "committed version")
        repo.add(["a.txt"])
        repo.commit("initial")

        make_file("a.txt", "working tree edit")
        repo.add(["a.txt"])  # stage the edit too
        repo.restore(staged=True)

        assert open("a.txt").read() == "committed version"

    def test_restore_staged_on_repo_with_no_commits_does_not_crash(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        repo.restore(staged=True)
        # nothing to restore from yet - the file should be untouched, not crash
        assert open("a.txt").read() == "aaa"

    def test_diff_staged_on_repo_with_no_commits_does_not_crash(self, repo, make_file, capsys):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        repo.diff(staged=True)
