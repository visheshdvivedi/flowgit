import time

import pytest


class TestLogOrdering:

    def test_log_walks_linear_history_via_head(self, repo, make_commit):
        first_sha = make_commit({"a.txt": "v1"}, "first")
        second_sha = make_commit({"a.txt": "v2, distinct size"}, "second")

        seen = []
        parent = repo._resolve_head()
        while parent:
            commit_object = repo.read_object(parent, display_info=False)
            seen.append(parent)
            parent = commit_object.parent[0] if commit_object.parent else None

        assert seen == [second_sha, first_sha]

    def test_log_message_and_author_are_correct(self, repo, make_commit):
        sha = make_commit({"a.txt": "content"}, "a meaningful message")
        commit_object = repo.read_object(sha, display_info=False)
        assert commit_object.message.strip("\n") == "a meaningful message"
        assert commit_object.author == "testuser"
        assert commit_object.author_email == "test@example.com"

    def test_log_preserves_original_commit_timestamp_on_reread(self, repo, make_commit, monkeypatch):
        """
        Positive regression test: this used to be BUG-1 (every re-read commit
        got a fabricated 'now' timestamp). commit.py's constructor was fixed
        to respect a tagger's explicit timestamp, so this should now pass.
        """
        import flowgit.core.objects.commit as commit_module

        monkeypatch.setattr(commit_module, "_get_current_timestamp", lambda: 1000000000.0)
        sha = make_commit({"a.txt": "content"}, "old commit")

        monkeypatch.setattr(commit_module, "_get_current_timestamp", lambda: 9999999999.0)
        commit_object = repo.read_object(sha, display_info=False)

        assert float(commit_object.author_timestamp) == 1000000000.0

    def test_log_int_float_conversion_survives_reread_timestamp(self, repo, make_commit):
        """
        Regression test tying together the BUG-1 fix and repository.log()'s
        int(float(...)) conversion: reading a commit back and formatting its
        timestamp the way log() does should not raise.
        """
        sha = make_commit({"a.txt": "content"}, "message")
        commit_object = repo.read_object(sha, display_info=False)
        # this is exactly what repository.log() does with the field
        int(float(commit_object.author_timestamp))


class TestLogMergeCommits:

    def test_log_reaches_commits_unique_to_merged_in_branch(self, repo, make_commit, capsys):
        """
        Regression test for the fixed version of BUG-16: log() used to walk
        only parent_list[0], so a merge commit's second parent - and every
        commit unique to the branch merged in - was silently never shown.
        log() now walks the full commit graph reachable from HEAD, so both
        sides of a merge appear in its output.
        """
        # Both files exist from the base commit onward, so the merge only
        # ever updates already-tracked paths - this sidesteps BUG-19
        # (merging in a genuinely new file crashes) so BUG-16 can be
        # tested in isolation.
        make_commit({"shared.txt": "base", "main-file.txt": "base main file"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        feature_sha = make_commit({"shared.txt": "changed on feature, distinct length"}, "feature-only commit")

        repo.switch("main")
        make_commit({"main-file.txt": "changed on main, a distinct length too"}, "main-only commit")

        repo.merge("feature")

        repo.log()
        captured = capsys.readouterr()
        assert feature_sha in captured.out
        assert "feature-only commit" in captured.out

    def test_log_announces_merge_commit(self, repo, make_commit, capsys):
        make_commit({"shared.txt": "base", "main-file.txt": "base main file"}, "base commit")
        repo.branch("feature", "")

        repo.switch("feature")
        make_commit({"shared.txt": "changed on feature, distinct length"}, "feature-only commit")

        repo.switch("main")
        make_commit({"main-file.txt": "changed on main, a distinct length too"}, "main-only commit")

        repo.merge("feature")

        repo.log()
        captured = capsys.readouterr()
        assert "[MERGE_COMMIT]" in captured.out
