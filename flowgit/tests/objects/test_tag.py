import pytest

from flowgit.core.objects import FlowGitTagObject, ObjectType, Tagger

test_sha = "a90f2e3ecf0c58fb09a8a3b801e8939ee83469ff"
test_file_name = "README.md"
test_tagger = Tagger(
    name = "testuser",
    email = "testuser@test.com",
    timestamp = "123456789",
    timezone = ""
)
test_serialize_output = "\n".join([
    f"object {test_sha}",
    "type blob",
    f"tag {test_file_name}",
    "tagger testuser <testuser@test.com> 123456789 ",
    "",
    "tag message",
])


def make_tag(message="tag message", tagger=test_tagger, name=test_file_name):
    return FlowGitTagObject(
        sha=test_sha,
        type="blob",
        name=name,
        message=message,
        tagger=tagger
    )


class TestTagObject:

    def test_class_type(self):
        assert make_tag().type == ObjectType.tag

    def test_serialize_produces_expected_format(self):
        data = make_tag().serialize()
        assert data.decode() == test_serialize_output

    def test_deserialize_extracts_object_sha(self):
        data = FlowGitTagObject.deserialize(test_serialize_output.encode())
        assert data['object'] == test_sha

    def test_deserialize_extracts_type(self):
        data = FlowGitTagObject.deserialize(test_serialize_output.encode())
        assert data['type'] == "blob"

    def test_deserialize_extracts_tagger_as_tagger_object(self):
        data = FlowGitTagObject.deserialize(test_serialize_output.encode())
        assert isinstance(data['tagger'], Tagger)
        assert data['tagger'].name == "testuser"
        assert data['tagger'].email == "testuser@test.com"
        assert data['tagger'].timestamp == "123456789"

    def test_serialize_deserialize_round_trip_with_non_colliding_message(self):
        """
        One genuinely working case: a single-word tagger name and a message
        that doesn't happen to start with a recognized header keyword
        ("object"/"type"/"tag"/"tagger"). Confirms the module isn't 100%
        broken - the tag name/sha/type/tagger fields round-trip fine here.
        """
        tag = make_tag(message="Release version 1.0", name="v1.0")
        parsed = FlowGitTagObject.deserialize(tag.serialize())
        assert parsed['object'] == test_sha
        assert parsed['tag'] == "v1.0"
        assert parsed['tagger'].name == "testuser"

    def test_deserialize_message_body_is_captured(self):
        tag = make_tag(message="Release version 1.0", name="v1.0")
        parsed = FlowGitTagObject.deserialize(tag.serialize())
        assert parsed['message'].strip("\n") == "Release version 1.0"

    def test_deserialize_message_starting_with_header_keyword_does_not_corrupt_tag_name(self):
        data = FlowGitTagObject.deserialize(test_serialize_output.encode())
        assert data['tag'] == test_file_name

    def test_deserialize_multiword_tagger_name_does_not_raise(self):
        tagger = Tagger(name="Test User", email="test@example.com", timestamp="123456789", timezone="")
        tag = make_tag(tagger=tagger, message="Release version 1.0", name="v1.0")
        parsed = FlowGitTagObject.deserialize(tag.serialize())
        assert parsed['tagger'].name == "Test User"

    def test_deserialize_single_word_name_preserves_real_timezone(self):
        """
        Regression test: the single-word-tagger-name branch of deserialize()
        used to parse `timezone` off the wire and then discard it, hardcoding
        Tagger(..., "") instead of using the parsed value. Not caught before
        since the only single-word-name fixture in this file used an empty
        timezone, which happened to match the hardcoded "" either way.
        """
        tagger = Tagger(name="testuser", email="testuser@test.com", timestamp="123456789", timezone="+0530")
        tag = make_tag(tagger=tagger, message="Release version 1.0", name="v1.0")
        parsed = FlowGitTagObject.deserialize(tag.serialize())
        assert parsed['tagger'].timezone == "+0530"

    def test_deserialize_handles_true_blank_line_separator(self):
        raw = "\n".join([
            f"object {test_sha}",
            "type blob",
            f"tag {test_file_name}",
            "tagger testuser <testuser@test.com> 123456789",
            "",
            "tag message",
        ]).encode()
        data = FlowGitTagObject.deserialize(raw)
        assert data['object'] == test_sha
