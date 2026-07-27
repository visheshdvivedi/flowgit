import pytest
import zlib

from flowgit.core.objects import FlowGitObject, ObjectType

class OneMethodParent(FlowGitObject):
    def serialize(self):
        print("serialize")
        pass

class TestParentWithoutType(FlowGitObject):
    def serialize(self):
        return "content".encode()
    def deserialize(self, data: bytes):
        return data.decode()


class TestParent(FlowGitObject):
    type = ObjectType.blob

    def serialize(self):
        return "content".encode()
    def deserialize(self, data: bytes):
        return data.decode()

class TestParentDiffType(FlowGitObject):
    type = ObjectType.commit

    def serialize(self):
        return "content".encode()
    def deserialize(self, data: bytes):
        return data.decode()


class TestParentEmptyContent(FlowGitObject):
    def serialize(self):
        return "".encode()
    def deserialize(self, data: bytes):
        return data.decode()

class TestObject:

    def test_object_creation(self):
        with pytest.raises(TypeError):
            test_object = FlowGitObject()

    def test_one_abstract_method_instantiation(self):
        with pytest.raises(TypeError):
            test_object = OneMethodParent()

    def test_both_abstract_method_instantiation(self):
        test_object = TestParent()

    def test_default_object_type(self):
        test_object = TestParentWithoutType()
        assert test_object.type == ObjectType.blob

    def test_raw_method_response(self):
        test_object = TestParent()

        raw_content = test_object.raw()
        assert len(raw_content) == 14

        raw_content_string = raw_content.decode()
        assert raw_content_string == 'blob 7\0content'

    def test_empty_content_object(self):
        test_object = TestParentEmptyContent()

        raw_content = test_object.raw()
        assert len(raw_content) == 7

        raw_content_string = raw_content.decode()
        assert raw_content_string == 'blob 0\0'

    def test_oid_response(self):
        test_object = TestParent()

        sha = test_object.oid()
        assert len(sha) == 40
        assert sha == "6b584e8ece562ebffc15d38808cd6b98fc3d97ea"

        obj = test_object.oid(hexdigest=False)
        assert len(obj.digest()) == 20
        assert obj.digest() == b'kXN\x8e\xceV.\xbf\xfc\x15\xd3\x88\x08\xcdk\x98\xfc=\x97\xea'

    def test_oid_response_different_type(self):
        test_commit_object = TestParentDiffType()

        sha = test_commit_object.oid()
        assert len(sha) == 40
        assert sha == "8dabe13dbd732218b362574ea7c9598dd0825868"

        obj = test_commit_object.oid(hexdigest=False)
        assert len(obj.digest()) == 20
        assert obj.digest() == b'\x8d\xab\xe1=\xbds"\x18\xb3bWN\xa7\xc9Y\x8d\xd0\x82Xh'


    def test_decompression(self):
        test_object = TestParent()
        compressed = test_object.compress()
        assert zlib.compress("blob 7\0content".encode()) == compressed

    def test_serialize_and_deserialize(self):
        test_object = TestParent()
        assert test_object.deserialize(test_object.serialize()) == 'content'