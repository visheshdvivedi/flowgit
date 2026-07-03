import os
import struct
import hashlib
from dataclasses import dataclass
from pathlib import Path

@dataclass
class IndexEntry:
    ctime_s: int
    ctime_ns: int
    mtime_s: int
    mtime_ns: int
    dev: int
    ino: int
    mode: int
    uid: int
    gid: int
    size: int
    sha1: bytes
    flags: int
    path: str

    @property
    def sha1_hex(self) -> str:
        return self.sha1.hex()



def read_index(index_file_path: Path):
    """
    Parse .flowgit/index file path and return list of IndexEntry objects.
    """
    if not os.path.exists(index_file_path):
        return []

    content = bytes()
    with open(index_file_path, "rb") as file:
        content = file.read()

    checksum = content[-20:]
    computed_chechsum = hashlib.sha1(content[:-20]).digest()
    if checksum != computed_chechsum:
        raise ValueError("Index file is corrupted (sha-1 mismatch)")

    magic, version, num_entries = struct.unpack_from(">4sII", content, 0)
    if magic != b"DIRC":
        raise ValueError("Not a git index file (bad magic word)")
    if version != 2:
        raise ValueError(f"Unsupported index version: {version}")

    entries = []
    offset = 12

    for _ in range(num_entries):

        entry_start = offset
        (
            ctime_s,
            ctime_ns,
            mtime_s,
            mtime_ns,
            dev,
            ino,
            mode,
            uid,
            gid,
            size
        ) = struct.unpack_from(">IIIIIIIIII", content, offset)
        offset += 40

        sha1 = content[offset:offset+20]
        offset += 20

        flags = struct.unpack_from(">H", content, offset)[0]
        offset += 2

        null = content.index(b"\x00", offset)
        path = content[offset:null].decode()
        offset = null + 1

        entry_len_before_pad = offset - entry_start
        pad = (8 - (entry_len_before_pad % 8)) % 8
        offset += pad

        entries.append(
            IndexEntry(
                ctime_s = ctime_s,
                ctime_ns = ctime_ns,
                mtime_s = mtime_s,
                mtime_ns = mtime_ns,
                dev = dev,
                ino = ino,
                mode = mode,
                uid = uid,
                gid = gid,
                size = size,
                sha1 = sha1,
                flags = flags,
                path = path
            )
        )

    return entries



def write_index(index_file_path: str, entries: list[IndexEntry]) -> None:
    """
    Write list of IndexEntry objects back to the index file.
    """

    entries = sorted(entries, key=lambda x: x.path)
    body = struct.pack(">4sII", b"DIRC", 2, len(entries))

    for e in entries:
        path_bytes = e.path.encode()
        path_len = min(len(path_bytes), 0xFFF)
        flags = (e.flags & 0xF000) | path_len

        fixed = struct.pack(
            ">IIIIIIIIII",
            e.ctime_s,
            e.ctime_ns,
            e.mtime_s,
            e.mtime_ns,
            e.dev,
            e.ino,
            e.mode,
            e.uid,
            e.gid,
            e.size,
        )
        fixed += e.sha1
        fixed += struct.pack(">H", flags)
        fixed += path_bytes + b"\x00"

        entry_len = len(fixed)
        pad = (8 - (entry_len % 8)) % 8
        fixed += b"\x00" * pad

        body += fixed

    checksum = hashlib.sha1(body).digest()
    with open(index_file_path, "wb+") as file:
        file.write(bytes(body) + checksum)