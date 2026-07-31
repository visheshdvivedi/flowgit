from typing import List
from dataclasses import dataclass
from flowgit.core.objects.object import FlowGitObject, ObjectType


@dataclass
class TreeEntry:
    mode: int
    type: str
    name: str
    oid: str

def mode_to_type(mode) -> str:
    # mode arrives as a real int when built via write_tree_recursive, but as
    # the raw octal-digit string parsed straight off the wire when called
    # from deserialize() - normalize before comparing, or a str mode never
    # equals the int literal below and everything misclassifies as "blob".
    mode_int = int(mode, 8) if isinstance(mode, str) else mode
    if mode_int == 0o040000:
        return "tree"
    return "blob"

class FlowGitTreeObject(FlowGitObject):
    type = ObjectType.tree

    def __init__(self):
        self.entries: List[TreeEntry] = []

    def add(self, mode: int, type: str, name: str, oid: str):
        self.entries.append(
            TreeEntry(mode, type, name, oid)
        )

    def serialize(self) -> bytes:
        result = b""

        for entry in self.entries:
            result += str(oct(entry.mode)[2:]).encode()
            result += b" "
            result += entry.name.encode("utf-8")
            result += b"\x00"
            result += bytes.fromhex(entry.oid)

        return result

    def mode_to_type(self, mode: int) -> str:
        if mode == 0o040000:
            return "tree"
        return "blob"
    
    @classmethod
    def deserialize(cls, data: bytes) -> List[TreeEntry]:
        entries = []
        offset = 0
        while offset < len(data):
            # read mode
            space = data.index(b" ", offset)
            mode = data[offset:space].decode()
            offset = space + 1

            # read name
            null = data.index(b"\x00", offset)
            name = data[offset:null].decode()
            offset = null + 1

            # read 20 raw bytes sha1
            oid = data[offset:offset+20].hex()
            offset += 20

            type = mode_to_type(mode)
            entries.append(TreeEntry(mode=mode, type=type, name=name, oid=oid))

        return entries