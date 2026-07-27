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
        parent=[], 
        author_tagger: Optional[Tagger] = None,
        committer_tagger: Optional[Tagger] = None,
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

        if len(self.parent):
            for parent in self.parent:
                lines.append(f"parent {parent}")

        lines.extend([
            f"author {self.author} <{self.author_email}> {self.author_timestamp} {_get_timezone_difference()}",
            f"committer {self.committer} <{self.committer_email}> {self.commiter_timestamp} {_get_timezone_difference()}",
            "",
            self.message
        ])

        return "\n".join(lines).encode()
    
    @classmethod
    def deserialize(cls, data: bytes):
        lines = data.split(b"\n")
        output = {
            "tree": None,
            "parent": [],
            "author": None,
            "author_email": None,
            "author_timestamp": None,
            "author_timezone": None,
            "committer": None,
            "committer_email": None,
            "committer_timestamp": None,
            "committer_timezone": None,
            "message": ""
        }
        is_message = False
        for line in lines:
            if is_message:
                output["message"] += line.decode() + "\n"
                continue
            if line == b"":
                is_message = True
                continue
            if line.startswith(b"tree"):
                content = line.split(b" ", 2)[1]
                output['tree'] = content
            if line.startswith(b"parent"):
                content = line.split(b" ", 2)[1]
                output['parent'].append(content)
            if line.startswith(b"commit"):
                content = line.split(b" ", 2)[1]
                output['commit'] = content
            if line.startswith(b"author"):
                words = line.split(b" ")
                output['author'] = words[1]
                output['author_email'] = words[2]
                output['author_timestamp'] = words[3]
                output['author_timezone'] = words[4]
            if line.startswith(b"committer"):
                words = line.split(b" ")
                output['committer'] = words[1]
                output['committer_email'] = words[2]
                output['committer_timestamp'] = words[3]
                output['committer_timezone'] = words[4]

        return output
