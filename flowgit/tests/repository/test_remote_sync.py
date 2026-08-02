import os

from flowgit.core.repository import Repository


class TestRemoteConfig:

    def test_remote_add_stores_url(self, repo, remote_repo):
        repo.remote('add', 'origin', remote_repo.path)
        assert repo.config.get_value('remote "origin"', 'url') == remote_repo.path

    def test_remote_add_duplicate_name_is_rejected(self, repo, remote_repo):
        repo.remote('add', 'origin', remote_repo.path)
        repo.remote('add', 'origin', '/some/other/path')
        # the original url must survive, not get silently overwritten
        assert repo.config.get_value('remote "origin"', 'url') == remote_repo.path

    def test_remote_remove_removes_it(self, repo, remote_repo):
        repo.remote('add', 'origin', remote_repo.path)
        repo.remote('remove', 'origin')
        assert not repo.config.get_value('remote "origin"', 'url')

    def test_remote_remove_nonexistent_is_skipped_not_raised(self, repo):
        repo.remote('remove', 'origin')  # never added - should warn, not crash


class TestFetchRemote:

    def test_fetch_creates_remote_tracking_ref_without_touching_local_state(
        self, repo, remote_repo, make_commit, make_remote_commit
    ):
        local_sha = make_commit({"a.txt": "local content"}, "local commit")
        repo.remote('add', 'origin', remote_repo.path)
        remote_sha = make_remote_commit({"b.txt": "remote content"}, "remote commit")

        repo.fetch_remote('origin')

        tracking_ref_path = os.path.join(repo.flowgit_directory, "refs", "remotes", "origin", "main")
        assert os.path.exists(tracking_ref_path)
        assert open(tracking_ref_path).read().strip() == remote_sha

        # fetch must never touch the local branch or working tree
        assert repo._resolve_head() == local_sha
        assert not os.path.exists("b.txt")

    def test_fetch_copies_remote_objects_locally(self, repo, remote_repo, make_commit, make_remote_commit):
        make_commit({"a.txt": "local content"}, "local commit")
        repo.remote('add', 'origin', remote_repo.path)
        remote_sha = make_remote_commit({"b.txt": "remote content"}, "remote commit")

        repo.fetch_remote('origin')

        # the fetched commit is now readable locally, even though it's not
        # checked out or on any local branch yet
        fetched_commit = repo.read_object(remote_sha, display_info=False)
        assert fetched_commit is not None
        assert fetched_commit.message.strip("\n") == "remote commit"


class TestPullRemote:

    def test_pull_fast_forwards_local_branch_and_working_tree(
        self, remote_repo, make_remote_commit, clone_from_remote
    ):
        base_sha = make_remote_commit({"a.txt": "base content"}, "base commit")

        local = clone_from_remote(remote_repo)
        assert local._resolve_head() == base_sha
        local.remote('add', 'origin', remote_repo.path)

        update_sha = make_remote_commit({"a.txt": "updated content"}, "update commit")
        local.pull_remote('origin', 'main')

        assert local._resolve_head() == update_sha
        assert open(os.path.join(local.path, "a.txt")).read() == "updated content"

    def test_pull_merges_into_current_branch_not_named_argument(
        self, remote_repo, make_remote_commit, clone_from_remote
    ):
        """
        Regression test: pull_remote used to merge into refs/heads/<branch>
        (the argument passed in) rather than whatever's actually checked
        out - fixed to always resolve the real current branch first.
        """
        make_remote_commit({"a.txt": "base"}, "base commit")

        local = clone_from_remote(remote_repo)
        local.remote('add', 'origin', remote_repo.path)

        local.branch("feature", "")
        local.switch("feature")

        update_sha = make_remote_commit({"a.txt": "remote update"}, "remote update")

        # pulling "main" from origin while checked out on "feature" must
        # merge into feature, not silently rewrite main's ref/files
        local.pull_remote('origin', 'main')

        current_branch, _ = local._resolve_head_branch()
        assert current_branch == "feature"
        assert local._resolve_head() == update_sha
        assert open(os.path.join(local.path, "a.txt")).read() == "remote update"


class TestPushToRemote:

    def test_push_transfers_new_local_commits_to_remote(
        self, remote_repo, make_remote_commit, clone_from_remote
    ):
        """
        The core correctness check: after push, the remote's own
        refs/heads/<branch> and object store actually reflect the pushed
        commit - not just "push ran without raising an error."
        """
        make_remote_commit({"a.txt": "base content"}, "base commit")

        local = clone_from_remote(remote_repo)
        local.remote('add', 'origin', remote_repo.path)
        local.fetch_remote('origin')

        with open(os.path.join(local.path, "b.txt"), "w") as f:
            f.write("pushed content")
        local.add(["b.txt"])
        local.commit("local advance")
        new_sha = local._resolve_head()

        local.push_to_remote('origin', 'main')

        # the remote's own branch ref must point at the pushed commit
        remote_branch_ref = os.path.join(remote_repo.flowgit_directory, "refs", "heads", "main")
        assert open(remote_branch_ref).read().strip() == new_sha

        # and the remote must be able to read that commit from its own
        # object store - this is what actually breaks if the push copies
        # objects in the wrong direction
        remote_commit_obj = remote_repo.read_object(new_sha, display_info=False)
        assert remote_commit_obj is not None
        assert remote_commit_obj.message.strip("\n") == "local advance"

    def test_push_updates_local_remote_tracking_ref(
        self, remote_repo, make_remote_commit, clone_from_remote
    ):
        make_remote_commit({"a.txt": "base content"}, "base commit")

        local = clone_from_remote(remote_repo)
        local.remote('add', 'origin', remote_repo.path)
        local.fetch_remote('origin')

        with open(os.path.join(local.path, "b.txt"), "w") as f:
            f.write("advance")
        local.add(["b.txt"])
        local.commit("advance")
        new_sha = local._resolve_head()

        local.push_to_remote('origin', 'main')

        tracking_ref_path = os.path.join(local.flowgit_directory, "refs", "remotes", "origin", "main")
        assert open(tracking_ref_path).read().strip() == new_sha
