import pytest

from flowgit.core.objects import FlowGitCommitObject, ObjectType, Tagger


def make_tagger(name="author", email="author@example.com", timestamp="1000000000.0", timezone="+00:00"):
    return Tagger(name=name, email=email, timestamp=timestamp, timezone=timezone)


class TestCommitObject:

    def test_class_type(self):
        commit = FlowGitCommitObject(tree="a" * 40)
        assert commit.type == ObjectType.commit

    def test_serialize_no_parent_omits_parent_line(self):
        tagger = make_tagger()
        commit = FlowGitCommitObject(
            tree="a" * 40,
            parent=[],
            author_tagger=tagger,
            committer_tagger=tagger,
            message="root commit"
        )
        output = commit.serialize().decode()
        lines = output.split("\n")
        assert lines[0] == f"tree {'a' * 40}"
        assert not any(line.startswith("parent") for line in lines)

    def test_serialize_single_parent(self):
        tagger = make_tagger()
        commit = FlowGitCommitObject(
            tree="a" * 40,
            parent=["b" * 40],
            author_tagger=tagger,
            committer_tagger=tagger,
            message="second commit"
        )
        lines = commit.serialize().decode().split("\n")
        assert lines[0] == f"tree {'a' * 40}"
        assert lines[1] == f"parent {'b' * 40}"

    def test_serialize_multiple_parents_in_order(self):
        tagger = make_tagger()
        commit = FlowGitCommitObject(
            tree="a" * 40,
            parent=["b" * 40, "c" * 40],
            author_tagger=tagger,
            committer_tagger=tagger,
            message="merge commit"
        )
        lines = commit.serialize().decode().split("\n")
        assert lines[1] == f"parent {'b' * 40}"
        assert lines[2] == f"parent {'c' * 40}"

    def test_serialize_author_and_committer_lines(self):
        author = make_tagger(name="alice", email="alice@example.com", timestamp="1111111111.0")
        committer = make_tagger(name="bob", email="bob@example.com", timestamp="2222222222.0")
        commit = FlowGitCommitObject(
            tree="a" * 40,
            author_tagger=author,
            committer_tagger=committer,
            message="msg"
        )
        output = commit.serialize().decode()
        assert "author alice <alice@example.com> 1111111111.0" in output
        assert "committer bob <bob@example.com> 2222222222.0" in output

    def test_serialize_blank_line_separates_headers_from_message(self):
        tagger = make_tagger()
        commit = FlowGitCommitObject(tree="a" * 40, author_tagger=tagger, committer_tagger=tagger, message="hello")
        lines = commit.serialize().decode().split("\n")
        assert lines[-2] == ""
        assert lines[-1] == "hello"

    def test_serialize_unicode_author_name_and_message(self):
        tagger = make_tagger(name="Ünïcödé", email="unicode@example.com")
        commit = FlowGitCommitObject(
            tree="a" * 40,
            author_tagger=tagger,
            committer_tagger=tagger,
            message="fix: résumé parsing 日本語"
        )
        raw = commit.serialize()
        assert "Ünïcödé" in raw.decode("utf-8")
        assert "fix: résumé parsing 日本語" in raw.decode("utf-8")

    def test_constructor_uses_current_timestamp_when_no_tagger(self):
        commit = FlowGitCommitObject(tree="a" * 40)
        assert commit.author == "Unknown"
        assert commit.author_email == "unknown@unknown.com"
        assert isinstance(commit.author_timestamp, float)

    def test_constructor_preserves_explicit_tagger_timestamp(self):
        """
        Regression test for the fixed version of BUG-1: FlowGitCommitObject
        used to always overwrite timestamps with _get_current_timestamp(),
        discarding any timestamp carried by the tagger (e.g. one parsed back
        from an existing commit's raw bytes). It now respects a non-empty
        tagger.timestamp and only falls back to "now" when none is given.
        """
        old_timestamp = "1000000000.123456"
        tagger = make_tagger(timestamp=old_timestamp)
        commit = FlowGitCommitObject(tree="a" * 40, author_tagger=tagger, committer_tagger=tagger)
        assert commit.author_timestamp == old_timestamp
        assert commit.commiter_timestamp == old_timestamp

    def test_constructor_falls_back_to_current_timestamp_when_tagger_timestamp_blank(self):
        """
        repository.commit_tree() constructs a fresh Tagger with timestamp=""
        for brand-new commits, relying on the constructor to fill in "now".
        """
        tagger = make_tagger(timestamp="")
        commit = FlowGitCommitObject(tree="a" * 40, author_tagger=tagger, committer_tagger=tagger)
        assert isinstance(commit.author_timestamp, float)
        assert isinstance(commit.commiter_timestamp, float)

    def test_deserialize_extracts_tree_sha(self):
        tagger = make_tagger()
        commit = FlowGitCommitObject(tree="a" * 40, author_tagger=tagger, committer_tagger=tagger, message="m")
        parsed = FlowGitCommitObject.deserialize(commit.serialize())
        assert parsed["tree"] == (b"a" * 40)

    def test_deserialize_extracts_all_parents_in_order(self):
        tagger = make_tagger()
        commit = FlowGitCommitObject(
            tree="a" * 40, parent=["b" * 40, "c" * 40],
            author_tagger=tagger, committer_tagger=tagger, message="m"
        )
        parsed = FlowGitCommitObject.deserialize(commit.serialize())
        assert parsed["parent"] == [b"b" * 40, b"c" * 40]

    def test_deserialize_extracts_author_and_committer_email(self):
        author = make_tagger(name="alice", email="alice@example.com")
        committer = make_tagger(name="bob", email="bob@example.com")
        commit = FlowGitCommitObject(tree="a" * 40, author_tagger=author, committer_tagger=committer, message="m")
        parsed = FlowGitCommitObject.deserialize(commit.serialize())
        assert parsed["author"] == b"alice"
        assert parsed["author_email"] == b"<alice@example.com>"
        assert parsed["committer"] == b"bob"
        assert parsed["committer_email"] == b"<bob@example.com>"

    def test_deserialize_preserves_multiline_message(self):
        tagger = make_tagger()
        commit = FlowGitCommitObject(
            tree="a" * 40, author_tagger=tagger, committer_tagger=tagger,
            message="line one\nline two"
        )
        parsed = FlowGitCommitObject.deserialize(commit.serialize())
        assert parsed["message"].strip("\n") == "line one\nline two"

    def test_deserialize_does_not_spuriously_populate_commit_key_from_committer_line(self):
        tagger = make_tagger(name="bob")
        commit = FlowGitCommitObject(tree="a" * 40, author_tagger=tagger, committer_tagger=tagger, message="m")
        parsed = FlowGitCommitObject.deserialize(commit.serialize())
        assert "commit" not in parsed

    def test_deserialize_multiword_author_name_does_not_corrupt_fields(self):
        tagger = make_tagger(name="Test User", email="test@example.com", timestamp="1000000000.0")
        commit = FlowGitCommitObject(tree="a" * 40, author_tagger=tagger, committer_tagger=tagger, message="m")
        parsed = FlowGitCommitObject.deserialize(commit.serialize())
        assert parsed["author"] == b"Test User"
        assert parsed["author_timestamp"] == b"1000000000.0"

    def test_deserialize_header_with_irregular_spacing_raises_indexerror(self):
        """
        Same root cause as BUG-3/BUG-11, demonstrated directly: a header line
        with an unexpected number of tokens overruns `words[4]`.
        """
        malformed = (
            b"tree " + b"a" * 40 + b"\n"
            b"author onlyname\n"
            b"committer onlyname\n"
            b"\n"
            b"message"
        )
        with pytest.raises(IndexError):
            FlowGitCommitObject.deserialize(malformed)
