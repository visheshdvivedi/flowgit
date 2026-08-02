import os

import pytest

from flowgit.core.objects import ObjectType, TreeEntry, FlowGitTagObject


class TestHashObjectCatFile:

    def test_hash_object_write_then_cat_file_round_trip_text(self, repo, make_file):
        make_file("hello.txt", "hello world\n")
        content = open("hello.txt", "rb").read()
        blob = repo.hash_object(content, ObjectType.blob, True)

        read_back = repo.read_object(blob.oid(), display_info=False)
        assert read_back.data == content

    def test_hash_object_binary_content_round_trip(self, repo):
        binary_content = bytes(range(256))
        blob = repo.hash_object(binary_content, ObjectType.blob, True)

        read_back = repo.read_object(blob.oid(), display_info=False)
        assert read_back.data == binary_content

    def test_hash_object_write_false_does_not_persist(self, repo):
        blob = repo.hash_object(b"not persisted", ObjectType.blob, False)
        assert repo.read_object(blob.oid(), display_info=False) is None

    def test_hash_object_non_blob_type_is_unsupported(self, repo):
        result = repo.hash_object(b"content", ObjectType.commit, True)
        assert result is None

    def test_read_object_unknown_hash_returns_none(self, repo):
        assert repo.read_object("f" * 40, display_info=False) is None


class TestTreeAndCommit:

    def test_write_tree_from_entries_produces_valid_tree(self, repo, make_file):
        make_file("a.txt", "aaa")
        make_file("b.txt", "bbb")
        repo.add(["a.txt", "b.txt"])
        tree_sha = repo.write_tree()

        tree_obj = repo.read_object(tree_sha, display_info=False)
        names = sorted(e.name for e in tree_obj.entries)
        assert names == ["a.txt", "b.txt"]

    def test_write_tree_nested_directories(self, repo, make_file):
        make_file("dir/nested.txt", "nested content")
        make_file("top.txt", "top content")
        repo.add(["dir/nested.txt", "top.txt"])
        tree_sha = repo.write_tree()

        tree_obj = repo.read_object(tree_sha, display_info=False)
        names = sorted(e.name for e in tree_obj.entries)
        assert names == ["dir", "top.txt"]
        dir_entry = next(e for e in tree_obj.entries if e.name == "dir")
        assert dir_entry.type == "tree"

        sub_tree = repo.read_object(dir_entry.oid, display_info=False)
        assert [e.name for e in sub_tree.entries] == ["nested.txt"]

    def test_commit_tree_creates_commit_with_correct_tree_and_parent(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        tree_sha = repo.write_tree()

        commit = repo.commit_tree(tree_sha, [], "first commit")
        assert commit.tree == tree_sha
        assert commit.parent == []

        second_commit = repo.commit_tree(tree_sha, [commit.oid()], "second commit")
        assert second_commit.parent == [commit.oid()]

    def test_commit_tree_rejects_nonexistent_tree_sha(self, repo):
        result = repo.commit_tree("f" * 40, [], "message")
        assert result is None

    def test_commit_tree_rejects_nonexistent_parent_sha(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        tree_sha = repo.write_tree()
        result = repo.commit_tree(tree_sha, ["f" * 40], "message")
        assert result is None


class TestMakeTreeCliPath:

    def test_make_tree_from_cli_style_entry_string(self, repo):
        blob = repo.hash_object(b"file content", ObjectType.blob, True)
        row = f"100644 blob {blob.oid()} file.txt"
        tree = repo.make_tree(row)
        assert tree is not None

    def test_write_tree_recursive_uses_int_mode_and_round_trips_correctly(self, repo, make_file):
        """
        Contrast case for BUG-6: the *other* tree-construction path
        (write_tree_recursive, used by add/commit) builds TreeEntry.mode as a
        real int from IndexEntry.mode, and correctly round-trips through
        serialize()/deserialize() without hitting the oct() crash.
        """
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        tree_sha = repo.write_tree()
        tree_obj = repo.read_object(tree_sha, display_info=False)
        entry = tree_obj.entries[0]
        # after deserialize, tree.py's own (separate, documented) mode-type
        # inconsistency means this comes back as a string - but it should at
        # least be parseable back to the original int mode.
        assert int(entry.mode, 8) == 0o100644


class TestMakeTag:

    def test_make_tag_creates_tag_object(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        tree_sha = repo.write_tree()
        commit = repo.commit_tree(tree_sha, [], "message")

        repo.make_tag(commit.oid(), "commit", "v1.0", "release message")

    def test_make_tag_populates_real_timestamp_and_timezone(self, repo, make_file):
        """
        A tag with a blank tagger timestamp/timezone isn't a valid git tag
        object - make_tag() used to always pass timestamp="" / timezone="",
        which would fail integrity checks against a real git binary.
        """
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        tree_sha = repo.write_tree()
        commit = repo.commit_tree(tree_sha, [], "message")

        repo.make_tag(commit.oid(), "commit", "v1.0", "release message")

        tag_sha = None
        for folder in os.listdir(os.path.join(repo.flowgit_directory, "objects")):
            folder_path = os.path.join(repo.flowgit_directory, "objects", folder)
            for filename in os.listdir(folder_path):
                candidate = folder + filename
                obj = repo.read_object(candidate, display_info=False)
                if isinstance(obj, FlowGitTagObject):
                    tag_sha = candidate
                    break

        assert tag_sha is not None
        tag_obj = repo.read_object(tag_sha, display_info=False)
        assert tag_obj.tagger.timestamp != ""
        assert tag_obj.tagger.timezone != ""


class TestObjectRoundTripFidelity:
    """
    For every object type: create it, note the sha it was stored under, read
    it back via read_object() (which deserializes and reconstructs a fresh
    object from the raw bytes), then re-derive that reconstructed object's
    own oid. If serialize()/deserialize() aren't perfectly symmetric for
    every field, the recomputed oid silently diverges from the sha the
    object is actually stored under - exactly the failure mode clone's
    integrity check runs into, caught here per-object-type in isolation.
    """

    def test_blob_round_trip_preserves_oid(self, repo):
        blob = repo.hash_object(b"some file content for round trip testing", ObjectType.blob, True)
        original_sha = blob.oid()

        read_back = repo.read_object(original_sha, display_info=False)
        assert read_back.oid() == original_sha

    def test_tree_round_trip_preserves_oid(self, repo, make_file):
        make_file("a.txt", "aaa")
        make_file("dir/nested.txt", "nested content")
        repo.add(["a.txt", "dir/nested.txt"])
        tree_sha = repo.write_tree()

        # the top-level tree, and the nested subtree it references, both get
        # deserialized independently - check both, since a bug could affect
        # one construction path but not the other
        top_level = repo.read_object(tree_sha, display_info=False)
        assert top_level.oid() == tree_sha

        dir_entry = next(e for e in top_level.entries if e.name == "dir")
        sub_tree = repo.read_object(dir_entry.oid, display_info=False)
        assert sub_tree.oid() == dir_entry.oid

    def test_commit_round_trip_preserves_oid(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        tree_sha = repo.write_tree()
        commit = repo.commit_tree(tree_sha, [], "a commit message\nwith multiple lines\nfor round trip testing")
        original_sha = commit.oid()

        read_back = repo.read_object(original_sha, display_info=False)
        assert read_back.oid() == original_sha

    def test_tag_round_trip_preserves_oid(self, repo, make_file):
        make_file("a.txt", "aaa")
        repo.add(["a.txt"])
        tree_sha = repo.write_tree()
        commit = repo.commit_tree(tree_sha, [], "message")
        repo.make_tag(commit.oid(), "commit", "v1.0", "a tag message for round trip testing")

        tag_sha = None
        for folder in os.listdir(os.path.join(repo.flowgit_directory, "objects")):
            folder_path = os.path.join(repo.flowgit_directory, "objects", folder)
            for filename in os.listdir(folder_path):
                candidate = folder + filename
                obj = repo.read_object(candidate, display_info=False)
                if isinstance(obj, FlowGitTagObject):
                    tag_sha = candidate
                    break

        assert tag_sha is not None
        read_back = repo.read_object(tag_sha, display_info=False)
        assert read_back.oid() == tag_sha
