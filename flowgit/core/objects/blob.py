from flowgit.core.objects.object import FlowGitObject, ObjectType

class FlowGitBlobObject(FlowGitObject):
    type = ObjectType.blob

    def __init__(self, data: bytes):
        self.data = data

    def serialize(self) -> bytes:
        return self.data
    
    @classmethod
    def deserialize(cls, data: bytes):
        return cls(data)