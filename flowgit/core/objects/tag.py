from dataclasses import dataclass
from typing import Optional
from flowgit.core.objects import FlowGitObject, ObjectType, Tagger


class TagObject(FlowGitObject):
    type = ObjectType.tag

    def __init__(
        self,
        sha: str,
        type: ObjectType,
        name: str,
        tagger: Optional[Tagger],
        message: str
    ):

        self.tag_sha = sha
        self.tag_type = type
        self.tag_name = name
        self.tagger = tagger
        self.tag_message = message

    def serialize(self) -> bytes:
        lines = []
        lines.append(f"object {self.tag_sha}")
        lines.append(f"type {self.tag_type}")
        lines.append(f"tag {self.tag_name}")
        lines.append(f"tagger {self.tagger.name} <{self.tagger.email}> {self.tagger.timestamp}")
        lines.append(" ")
        lines.append(self.tag_message)
        raw_content = "\n".join(lines)
        return raw_content.encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes):
        lines = data.split("\n")
        data = {
            "object": "",
            "type": "",
            "tag": "",
            "tagger": "",
            "message": ""
        }

        # read lines
        for line in lines:
            key, value = line.split(" ")
            if key in data:
                data[key] = value

        if data['tagger']:
            name, email, timestamp = data['tagger'].split(" ")
            email = email.replace("<", "").replace(">", "")
            data['tagger'] = Tagger(name, email, timestamp, "")

        
