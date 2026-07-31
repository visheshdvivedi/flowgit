import os

import pytest


class TestFastForwardMerge:

    def test_fast_forward_moves_branch_ref_no_merge_commit(self, repo, make_commit):
        first_sha = make_commit({"a.txt": "version one"}, "first")
        repo.branch("feature", "")
        repo.switch("feature")
        second_sha = make_commit({"a.txt": "version-two-longer"}, "second on feature")

        repo.switch("main")
        repo.merge("feature")

        main_sha = repo._resolve_head()
        assert main_sha == second_sha

    def test_fast_forward_updates_working_tree(self, repo, make_commit):
        make_commit({"a.txt": "version one"}, "first")
        repo.branch("feature", "")
        repo.switch("feature")
        make_commit({"a.txt": "version-two-longer"}, "second on feature")

        repo.switch("main")
        repo.merge("feature")

        assert open("a.txt").read() == "version-two-longer"

    def test_merge_already_up_to_date_is_a_noop(self, repo, make_commit):
        sha = make_commit({"a.txt": "version one"}, "first")
        repo.branch("feature", "")
        repo.merge("feature")

        assert repo._resolve_head() == sha


class TestTrueMergeNoConflict:

    def test_true_merge_creates_commit_with_both_parents(self, repo, make_commit, make_file):
        base_sha = make_commit({"base.txt": "base"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        feature_sha = make_commit({"feature.txt": "feature content"}, "feature commit")

        repo.switch("main")
        main_sha = make_commit({"main.txt": "main content"}, "main commit")

        repo.merge("feature")

        merged_sha = repo._resolve_head()
        merge_commit = repo.read_object(merged_sha, display_info=False)
        assert set(merge_commit.parent) == {main_sha, feature_sha}

    def test_true_merge_combines_non_overlapping_changes(self, repo, make_commit):
        make_commit({"base.txt": "base"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        make_commit({"feature.txt": "feature content"}, "feature commit")

        repo.switch("main")
        make_commit({"main.txt": "main content"}, "main commit")

        repo.merge("feature")

        assert open("base.txt").read() == "base"
        assert open("main.txt").read() == "main content"
        assert open("feature.txt").read() == "feature content"

    def test_true_merge_succeeds_when_only_modifying_preexisting_shared_file(self, repo, make_commit):
        """
        Contrast case for BUG-19: when the merge only changes a file that's
        already tracked on the current branch (nothing genuinely new
        introduced), the index-update path takes the "path already has an
        entry" branch instead of reading from a working-tree file that
        might not exist - so this specific shape of non-conflicting merge
        works correctly today.
        """
        make_commit({"shared.txt": "base content", "untouched.txt": "same everywhere"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        make_commit({"shared.txt": "changed only on feature, much longer"}, "feature edit")

        repo.switch("main")
        # main advances history without touching shared.txt, so this is a
        # genuine (non-fast-forward) three-way merge, not a fast-forward.
        make_commit({"untouched.txt": "same everywhere", "main-only.txt": "irrelevant to the conflict"}, "main advance")

        repo.merge("feature")

        assert open("shared.txt").read() == "changed only on feature, much longer"

    def test_true_merge_unrelated_histories_refuses(self, repo, make_commit):
        make_commit({"a.txt": "on main"}, "main root")

        # build a second, entirely independent root commit + branch, sharing
        # no common ancestor with main
        tree_sha = repo.write_tree()  # reuses whatever's currently staged/committed's tree structure is irrelevant here
        unrelated_commit = repo.commit_tree(tree_sha, [], "unrelated root")
        repo.update_ref("refs/heads/unrelated", unrelated_commit.oid())

        repo.merge("unrelated")

        # should refuse, not merge or crash - HEAD should not have moved
        assert repo._resolve_head() != unrelated_commit.oid()

    def test_true_merge_removes_file_deleted_on_incoming_branch(self, repo, make_commit):
        """
        Regression test for two bugs found while fixing BUG-19: the loop
        folding merge results into the final index used to (a) mutate
        index_path_entry_mapping while iterating over it whenever
        removed_paths was non-empty (RuntimeError: dictionary changed size
        during iteration) and (b) only apply updated_index_entries_map to
        paths that already existed in the mapping, silently dropping
        genuinely new paths. This scenario exercises the removal path,
        which no other test previously touched.
        """
        make_commit({"a.txt": "to be deleted", "b.txt": "stays untouched"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        os.remove("a.txt")
        repo.add(["."])
        repo.commit("delete a.txt on feature")

        repo.switch("main")
        make_commit({"b.txt": "changed on main, a distinct length"}, "main edit")

        repo.merge("feature")

        assert not os.path.exists("a.txt")
        assert open("b.txt").read() == "changed on main, a distinct length"


class TestTrueMergeWithConflict:

    def test_conflict_sets_merge_head_and_merge_msg(self, repo, make_commit):
        make_commit({"a.txt": "base"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        make_commit({"a.txt": "feature version"}, "feature edit")

        repo.switch("main")
        make_commit({"a.txt": "main version"}, "main edit")

        repo.merge("feature")

        assert os.path.exists(os.path.join(repo.flowgit_directory, "MERGE_HEAD"))
        assert os.path.exists(os.path.join(repo.flowgit_directory, "MERGE_MSG"))

    def test_conflict_writes_marker_content(self, repo, make_commit):
        make_commit({"a.txt": "base"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        make_commit({"a.txt": "feature version"}, "feature edit")

        repo.switch("main")
        make_commit({"a.txt": "main version"}, "main edit")

        repo.merge("feature")

        content = open("a.txt").read()
        assert "<<<<<<<" in content
        assert "=======" in content
        assert ">>>>>>>" in content
        assert "main version" in content
        assert "feature version" in content

    def test_conflict_index_has_multistage_entries(self, repo, make_commit):
        from flowgit.core.objects import read_index
        from flowgit.services.index_flag import get_stage_from_index_entry

        make_commit({"a.txt": "base"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        make_commit({"a.txt": "feature version"}, "feature edit")

        repo.switch("main")
        make_commit({"a.txt": "main version"}, "main edit")

        repo.merge("feature")

        entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        conflict_entries = [e for e in entries if e.path == "a.txt"]
        stages = {get_stage_from_index_entry(e) for e in conflict_entries}
        assert stages == {1, 2, 3}

    def test_second_merge_while_unresolved_is_refused(self, repo, make_commit):
        make_commit({"a.txt": "base"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        make_commit({"a.txt": "feature version"}, "feature edit")

        repo.switch("main")
        make_commit({"a.txt": "main version"}, "main edit")

        repo.merge("feature")  # produces a conflict, MERGE_HEAD now exists
        head_before = open(os.path.join(repo.flowgit_directory, "HEAD")).read()

        repo.merge("feature")  # should refuse, not compound the mess
        head_after = open(os.path.join(repo.flowgit_directory, "HEAD")).read()
        assert head_before == head_after

    def test_conflict_stage_entries_do_not_get_bogus_symlink_mode(self, repo, make_commit):
        from flowgit.core.objects import read_index

        make_commit({"a.txt": "base"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        make_commit({"a.txt": "feature version"}, "feature edit")

        repo.switch("main")
        make_commit({"a.txt": "main version"}, "main edit")

        repo.merge("feature")

        entries = read_index(os.path.join(repo.flowgit_directory, "index"))
        conflict_entries = [e for e in entries if e.path == "a.txt"]
        assert all(e.mode != 0o120000 for e in conflict_entries)
