from dataclasses import dataclass
from typing import Optional
from flowgit.core.objects import FlowGitObject, ObjectType, Tagger


class FlowGitTagObject(FlowGitObject):
    type = ObjectType.tag

    def __init__(
        self,
        sha: str,
        type: ObjectType,
        name: str,
        message: str,
        tagger: Optional[Tagger]
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
        lines.append(f"tagger {self.tagger.name} <{self.tagger.email}> {self.tagger.timestamp} {self.tagger.timezone}")
        lines.append("")
        lines.append(self.tag_message)
        raw_content = "\n".join(lines)
        return raw_content.encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes):
        lines = data.decode().split("\n")
        output = {
            "object": "",
            "type": "",
            "tag": "",
            "tagger": "",
            "message": ""
        }

        # read lines
        is_message = False
        for line in lines:
            if is_message:
                output['message'] += line + "\n"
                continue
            if line.strip() == "":
                is_message = True
                continue

            key, value = line.split(" ", 1)
            if key == 'object':
                output['object'] = value
            elif key == 'type':
                output['type'] = value
            elif key == 'tag':
                output['tag'] = value
            elif key == 'tagger':
                output['tagger'] = value

        if output['tagger']:
            splits = output['tagger'].split(" ")
            if len(splits) == 4:
                name, email, timestamp, timezone = output['tagger'].split(" ", 4)
                email = email.replace("<", "").replace(">", "")
                output['tagger'] = Tagger(name, email, timestamp, timezone)
            elif len(splits) == 5:
                name = splits[0] + ' ' + splits[1]
                email = splits[2]
                timestamp = splits[3]
                timezone = splits[4]
                email = email.replace("<", "").replace(">", "")
                output['tagger'] = Tagger(name, email, timestamp, timezone)

        output['message'] = output['message'].strip()
        return output