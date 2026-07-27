from flowgit.core.objects.index import IndexEntry

def get_stage_from_index_entry(entry: IndexEntry) -> int:
    return (entry.flags >> 12) & 0b11

def make_flags(path: str, stage: int) -> int:
    name_len = min(len(path.encode()), 0xFFF)
    return (stage << 12) | name_len