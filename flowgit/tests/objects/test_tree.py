import pytest
import hashlib
from flowgit.core.objects import TreeEntry, FlowGitTreeObject, ObjectType

test_sha = hashlib.sha1("content".encode()).hexdigest()
tree_entries = [
    TreeEntry(
        mode=123, type="blob", name="test.txt", oid=test_sha
    )
]
serialize_output = b'173 blob test.txt\x00\x04\x0f\x06\xfdw@\x92G\x8dE\x07t\xf5\xba0\xc5\xdax\xac\xc8'

class TestTreeObject:

    def test_class_type(self):
        tree_object = FlowGitTreeObject()
        assert tree_object.type == ObjectType.tree

    def test_tree_serialize(self):
        tree_object = FlowGitTreeObject()
        tree_object.entries = tree_entries
        output = tree_object.serialize()
        assert output == serialize_output

    def test_tree_deserialize(self):
        tree_entries = FlowGitTreeObject.deserialize(serialize_output)
        assert len(tree_entries) == 1
        entry = tree_entries[0]
        assert entry.mode == tree_entries[0].mode
        assert entry.type == tree_entries[0].type
        assert entry.name == tree_entries[0].name
        assert entry.oid == tree_entries[0].oid

    def test_tree_add(self):
        tree_object = FlowGitTreeObject()
        tree_object.add(123, "blob", "test.txt", test_sha)
        assert len(tree_object.entries) == 1
        entry = tree_object.entries[0]
        assert entry.mode == tree_entries[0].mode
        assert entry.type == tree_entries[0].type
        assert entry.name == tree_entries[0].name
        assert entry.oid == tree_entries[0].oid