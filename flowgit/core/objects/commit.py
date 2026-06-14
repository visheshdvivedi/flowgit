import tzlocal
from datetime import datetime, timezone
from flowgit.core.objects.object import FlowGitObject, ObjectType


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

    def __init__(self, tree, parent=None, author="Unknown", author_email="unknown@unknown.com", author_timestamp=_get_current_timestamp(), committer="Unknown", committer_email="unknown@unknown.com", commiter_timestamp=_get_current_timestamp(), message=""):
        self.tree = tree
        self.parent = parent
        
        self.author = author
        self.author_email = author_email
        self.author_timestamp = author_timestamp

        self.committer = committer
        self.committer_email = committer_email
        self.commiter_timestamp = commiter_timestamp

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
            