from typing import List
from dataclasses import dataclass
from flowgit.core.objects.object import FlowGitObject, ObjectType


@dataclass
class TreeEntry:
    mode: str
    type: str
    name: str
    oid: str


class FlowGitTreeObject(FlowGitObject):
    type = ObjectType.tree

    def __init__(self):
        self.entries: List[TreeEntry] = []

    def add(self, mode, type, name, oid):
        self.entries.append(
            TreeEntry(mode, type, name, oid)
        )

    def serialize(self) -> bytes:
        result = []

        for entry in self.entries:
            entry_bytes = bytes()
            entry_bytes += str(entry.mode).encode("utf-8")
            entry_bytes += b" "
            entry_bytes += entry.type.encode("utf-8")
            entry_bytes += b" "
            entry_bytes += entry.name.encode("utf-8")
            entry_bytes += b"\x00"
            entry_bytes += bytes.fromhex(entry.oid)
            result.append(entry_bytes)

        return b"\n".join(result)

    def mode_to_type(self, mode: int) -> str:
        if mode == 0o040000:
            return "tree"
        return "blob"
    
    @classmethod
    def deserialize(cls, data: bytes) -> List[TreeEntry]:
        lines = data.split(b"\n")
        output: List[TreeEntry] = []
        for line in lines:
            null_idx = line.index(b"\x00")
            header = line[:null_idx].decode()
            hash = line[null_idx+1:].hex()
            mode, type, name = header.split(" ")
            output.append(
                TreeEntry(mode=mode, type=type, name=name, oid=hash)
            )
        return output