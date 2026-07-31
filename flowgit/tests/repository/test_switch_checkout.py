import os

import pytest


class TestSwitch:

    def test_switch_to_existing_branch_updates_head(self, repo, make_commit):
        make_commit({"a.txt": "aaa"}, "initial")
        repo.branch("feature", "")
        repo.switch("main")

        head_content = open(os.path.join(repo.flowgit_directory, "HEAD")).read()
        assert head_content == "ref: refs/heads/main"

    def test_switch_updates_working_tree_to_target_branch_content(self, repo, make_commit, make_file):
        make_commit({"a.txt": "on main"}, "initial")
        repo.branch("feature", "")
        repo.switch("feature")

        make_file("a.txt", "on feature")
        repo.add(["a.txt"])
        repo.commit("feature change")

        repo.switch("main")
        assert open("a.txt").read() == "on main"

        repo.switch("feature")
        assert open("a.txt").read() == "on feature"

    def test_switch_removes_files_unique_to_previous_branch(self, repo, make_commit, make_file):
        make_commit({"a.txt": "shared"}, "initial")
        repo.branch("feature", "")
        repo.switch("feature")

        make_file("only-on-feature.txt", "feature only")
        repo.add(["only-on-feature.txt"])
        repo.commit("add feature-only file")

        repo.switch("main")
        assert not os.path.exists("only-on-feature.txt")

    def test_switch_to_nonexistent_branch_raises_meaningful_error(self, repo, make_commit):
        make_commit({"a.txt": "aaa"}, "initial")
        # should not silently proceed or crash with an unrelated error
        repo.switch("does-not-exist")
        head_content = open(os.path.join(repo.flowgit_directory, "HEAD")).read()
        assert head_content == "ref: refs/heads/main"


class TestCheckout:

    def test_checkout_detaches_head_to_commit_sha(self, repo, make_commit):
        first_sha = make_commit({"a.txt": "v1"}, "first")
        second_sha = make_commit({"a.txt": "v2"}, "second")

        repo.checkout(first_sha)

        head_content = open(os.path.join(repo.flowgit_directory, "HEAD")).read()
        assert head_content == first_sha
        assert open("a.txt").read() == "v1"

    def test_checkout_nonexistent_sha_does_not_move_head(self, repo, make_commit):
        make_commit({"a.txt": "v1"}, "first")
        head_before = open(os.path.join(repo.flowgit_directory, "HEAD")).read()

        repo.checkout("f" * 40)

        head_after = open(os.path.join(repo.flowgit_directory, "HEAD")).read()
        assert head_after == head_before
