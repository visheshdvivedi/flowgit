import os
import shutil

import pytest


class TestUpdateRef:

    def test_update_ref_creates_ref_file_with_sha(self, repo, make_commit):
        sha = make_commit({"a.txt": "aaa"}, "initial")
        repo.update_ref("refs/heads/feature", sha)

        ref_path = os.path.join(repo.flowgit_directory, "refs", "heads", "feature")
        assert open(ref_path).read().strip() == sha

    def test_update_ref_rejects_nonexistent_sha(self, repo):
        repo.update_ref("refs/heads/feature", "f" * 40)
        ref_path = os.path.join(repo.flowgit_directory, "refs", "heads", "feature")
        assert not os.path.exists(ref_path)


class TestBranch:

    def test_branch_create_points_to_current_head(self, repo, make_commit):
        sha = make_commit({"a.txt": "aaa"}, "initial")
        repo.branch("feature", "")

        ref_path = os.path.join(repo.flowgit_directory, "refs", "heads", "feature")
        assert open(ref_path).read().strip() == sha

    def test_branch_create_switches_head_to_new_branch(self, repo, make_commit):
        make_commit({"a.txt": "aaa"}, "initial")
        repo.branch("feature", "")

        head_content = open(os.path.join(repo.flowgit_directory, "HEAD")).read()
        assert head_content == "ref: refs/heads/feature"

    def test_branch_create_duplicate_name_is_skipped_not_raised(self, repo, make_commit):
        make_commit({"a.txt": "aaa"}, "initial")
        repo.branch("feature", "")
        repo.branch("main", "")  # main already exists - should warn and no-op, not raise
        branches = repo._list_all_branches()
        assert branches.count("main") == 1

    def test_branch_delete_removes_ref_file(self, repo, make_commit):
        make_commit({"a.txt": "aaa"}, "initial")
        repo.branch("feature", "")
        repo.switch("main")
        repo.branch("", "feature")

        ref_path = os.path.join(repo.flowgit_directory, "refs", "heads", "feature")
        assert not os.path.exists(ref_path)

    def test_branch_delete_nonexistent_is_skipped_not_raised(self, repo, make_commit):
        make_commit({"a.txt": "aaa"}, "initial")
        repo.branch("", "does-not-exist")  # should just warn, not raise

    def test_branch_delete_current_branch_is_guarded(self, repo, make_commit):
        make_commit({"a.txt": "aaa"}, "initial")
        repo.branch("", "main")  # main is current branch - should refuse, not delete

        ref_path = os.path.join(repo.flowgit_directory, "refs", "heads", "main")
        assert os.path.exists(ref_path)

    def test_list_all_branches_missing_refs_heads_raises_meaningful_error(self, repo, make_commit):
        make_commit({"a.txt": "aaa"}, "initial")
        shutil.rmtree(os.path.join(repo.flowgit_directory, "refs", "heads"))

        with pytest.raises(Exception) as exc_info:
            repo._list_all_branches()
        assert not isinstance(exc_info.value, NameError)
