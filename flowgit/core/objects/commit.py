import tzlocal
from typing import Optional
from datetime import datetime, timezone
from flowgit.core.objects.object import FlowGitObject, ObjectType, Tagger

def _get_current_timestamp():
    return datetime.now(timezone.utc).timestamp()

def _get_timezone_difference():
    local_offset = datetime.now().astimezone().utcoffset()
    total_minutes = int(local_offset.total_seconds() / 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"{sign}{hours:02d}:{minutes:02d}"

class FlowGitCommitObject(FlowGitObject):
    type = ObjectType.commit

    def __init__(self, 
        tree, 
        parent=None, 
        author_tagger=Optional[Tagger],
        committer_tagger=Optional[Tagger],
        message=""
    ):
        self.tree = tree
        self.parent = parent
        
        if author_tagger:
            self.author = author_tagger.name
            self.author_email = author_tagger.email
        else:
            self.author = "Unknown"
            self.author_email = "unknown@unknown.com"

        if committer_tagger:
            self.committer = committer_tagger.name
            self.committer_email = committer_tagger.email
        else:
            self.committer = "Unknown"
            self.committer_email = "unknown@unknown.com"
        

        self.author_timestamp = _get_current_timestamp()
        self.commiter_timestamp = _get_current_timestamp()

        self.message = message

    def serialize(self) -> bytes:
        lines = []
        lines.append(f"tree {self.tree}")

        if self.parent:
            lines.append(f"parent {self.parent}")

        lines.extend([
            f"author {self.author} <{self.author_email}> {self.author_timestamp} {_get_timezone_difference()}",
            f"committer {self.committer} <{self.committer_email}> {self.commiter_timestamp} {_get_timezone_difference()}",
            "",
            self.message
        ])

        return "\n".join(lines).encode()
    
    @classmethod
    def deserialize(cls, data: bytes):
        lines = data.split("\n")
        output = {
            "tree": None,
            "parent": None,
            "author": None,
            "author_email": None,
            "author_timestamp": None,
            "committer": None,
            "committer_email": None,
            "committer_timestamp": None,
            "message": None
        }
        line = lines[0]
        is_message = False
        while len(line.strip()) > 0:
            if is_message:
                output["message"] += line + "\n"
                continue

            for keyword in ['tree', 'parent']:
                if line.startswith(keyword):
                    content = line.split(" ", 2)[1]
                    output[keyword] = content
                    continue

            if line.startswith("author"):
                words = line.split(" ")
                output['author'] = words[1]
                output['author_email'] = words[2]
                output['author_timestamp'] = words[3]
            if line.startswith("committer"):
                words = line.split(" ")
                output['committer'] = words[1]
                output['author_email'] = words[2]
                output['author_timestamp'] = words[3]

        return output
