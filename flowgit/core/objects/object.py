import zlib
import hashlib
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod

class ObjectType(Enum):
    commit = "commit"
    tree = "tree"
    blob = "blob"
    tag = "tag"


@dataclass
class Tagger:
    name: str
    email: str
    timestamp: str
    timezone: str


class FlowGitObject(ABC):
    type: ObjectType

    @abstractmethod
    def serialize(self) -> bytes:
        pass

    @classmethod
    @abstractmethod
    def deserialize(cls, data: bytes):
        pass

    def raw(self) -> bytes:
        content = self.serialize()
        header = f"{self.type.value} {len(content)}\0".encode()
        return header + content
    
    def oid(self, hexdigest=True) -> str:
        if hexdigest:
            return hashlib.sha1(self.raw()).hexdigest()
        return hashlib.sha1(self.raw())
    
    def compress(self) -> bytes:
        return zlib.compress(self.raw())