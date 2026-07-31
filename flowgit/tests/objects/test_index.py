import struct
import hashlib

import pytest

from flowgit.core.objects import IndexEntry, read_index, write_index


def make_entry(path="file.txt", sha1=b"\x11" * 20, flags=0, mode=0o100644, size=10):
    return IndexEntry(
        ctime_s=1000, ctime_ns=0,
        mtime_s=1000, mtime_ns=0,
        dev=1, ino=2, mode=mode, uid=501, gid=20, size=size,
        sha1=sha1, flags=flags, path=path
    )


class TestIndexRoundTrip:

    def test_write_then_read_single_entry(self, tmp_path):
        index_path = tmp_path / "index"
        entry = make_entry(path="hello.txt", sha1=b"\xab" * 20, size=42)
        write_index(str(index_path), [entry])

        entries = read_index(str(index_path))
        assert len(entries) == 1
        got = entries[0]
        assert got.path == "hello.txt"
        assert got.sha1 == b"\xab" * 20
        assert got.size == 42
        assert got.ctime_s == 1000
        assert got.mode == 0o100644

    def test_write_then_read_zero_entries(self, tmp_path):
        index_path = tmp_path / "index"
        write_index(str(index_path), [])
        entries = read_index(str(index_path))
        assert entries == []

    def test_write_then_read_multiple_entries_sorted_by_path(self, tmp_path):
        index_path = tmp_path / "index"
        entries_in = [
            make_entry(path="zebra.txt"),
            make_entry(path="apple.txt"),
            make_entry(path="mango.txt"),
        ]
        write_index(str(index_path), entries_in)

        entries_out = read_index(str(index_path))
        assert [e.path for e in entries_out] == ["apple.txt", "mango.txt", "zebra.txt"]

    def test_read_index_missing_file_returns_empty_list(self, tmp_path):
        assert read_index(str(tmp_path / "does-not-exist")) == []

    def test_non_ascii_path_round_trip(self, tmp_path):
        index_path = tmp_path / "index"
        path = "café/日本語.txt"
        write_index(str(index_path), [make_entry(path=path)])

        entries = read_index(str(index_path))
        assert entries[0].path == path

    def test_indexentry_sha1_hex_property(self):
        entry = make_entry(sha1=b"\xde\xad\xbe\xef" * 5)
        assert entry.sha1_hex == "deadbeef" * 5

    def test_flags_top_nibble_preserved_lower_bits_recomputed(self, tmp_path):
        """
        write_index() always recomputes the low 12 bits of flags from the
        real path length, but should preserve whatever's in the top nibble
        (0xF000) - e.g. the merge-stage bits packed by services/index_flag.py.
        """
        index_path = tmp_path / "index"
        stage_bits = 0b10 << 12  # stage 2, arbitrary garbage in the low bits
        entry = make_entry(path="conflict.txt", flags=stage_bits | 0xFFF)
        write_index(str(index_path), [entry])

        got = read_index(str(index_path))[0]
        assert (got.flags & 0xF000) == stage_bits
        assert (got.flags & 0x0FFF) == len("conflict.txt")

    @pytest.mark.parametrize("path_len", [1, 9])
    def test_path_length_exactly_at_padding_boundary(self, tmp_path, path_len):
        index_path = tmp_path / "index"
        path = "a" * path_len
        write_index(str(index_path), [make_entry(path=path)])
        entries = read_index(str(index_path))
        assert entries[0].path == path

    @pytest.mark.parametrize("path_len", [2, 10])
    def test_path_length_one_past_padding_boundary(self, tmp_path, path_len):
        index_path = tmp_path / "index"
        path = "a" * path_len
        write_index(str(index_path), [make_entry(path=path)])
        entries = read_index(str(index_path))
        assert entries[0].path == path


class TestIndexCorruption:

    def test_read_index_corrupted_checksum_raises(self, tmp_path):
        index_path = tmp_path / "index"
        write_index(str(index_path), [make_entry()])

        raw = bytearray(index_path.read_bytes())
        raw[-1] ^= 0xFF  # flip a bit in the trailing checksum
        index_path.write_bytes(bytes(raw))

        with pytest.raises(ValueError, match="corrupted"):
            read_index(str(index_path))

    def test_read_index_bad_magic_raises(self, tmp_path):
        index_path = tmp_path / "index"
        body = struct.pack(">4sII", b"NOPE", 2, 0)
        checksum = hashlib.sha1(body).digest()
        index_path.write_bytes(body + checksum)

        with pytest.raises(ValueError, match="magic"):
            read_index(str(index_path))

    def test_read_index_unsupported_version_raises(self, tmp_path):
        index_path = tmp_path / "index"
        body = struct.pack(">4sII", b"DIRC", 3, 0)
        checksum = hashlib.sha1(body).digest()
        index_path.write_bytes(body + checksum)

        with pytest.raises(ValueError, match="version"):
            read_index(str(index_path))

    def test_read_index_truncated_file_raises(self, tmp_path):
        """
        Header claims 1 entry but the file is cut off before that entry's
        fixed-size fields even fit - should fail loudly, not return
        silently-wrong data.
        """
        index_path = tmp_path / "index"
        body = struct.pack(">4sII", b"DIRC", 2, 1) + b"\x00" * 5  # nowhere near a full entry
        checksum = hashlib.sha1(body).digest()
        index_path.write_bytes(body + checksum)

        with pytest.raises((struct.error, ValueError)):
            read_index(str(index_path))
