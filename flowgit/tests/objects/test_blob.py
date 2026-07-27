import pytest
from flowgit.core.objects import FlowGitBlobObject, ObjectType

class TestBlobObject:

    def test_class_type(self):
        blob_object = FlowGitBlobObject("content".encode())
        assert blob_object.type == ObjectType.blob

    def test_blob_serialize(self):
        data = "content"
        blob_object = FlowGitBlobObject(data.encode())
        assert blob_object.serialize() == data.encode()

    def test_blob_deserialize(self):
        data = "content"
        deserialize_object = FlowGitBlobObject.deserialize(data.encode())
        assert deserialize_object.data == data.encode()