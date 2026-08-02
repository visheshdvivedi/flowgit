from __future__ import annotations

import os
import zlib
import shutil
import difflib
import pathspec
import subprocess
from typing import List, Tuple, Dict, Union, Literal
from hashlib import sha1
from pathlib import Path

from flowgit.core.objects import *
from flowgit.core.objects.commit import _get_current_timestamp, _get_timezone_difference
from flowgit.services.config import FlowGitConfigManager
from flowgit.services.index_flag import get_stage_from_index_entry, make_flags
from flowgit.services.algorithm import get_content_difference_difflib
from flowgit.ui.console import (
    display_warning_message, 
    display_creation_message, 
    display_error_message, 
    display_information_message, 
    display_success_message
)

HEAD_MARKER = "<<<<<<<"
MIDDLE_MARKER = "======="
INCOMING_MARKER = ">>>>>>>"

class Repository:

    def __init__(self, path: str, replace: bool = False):
        self.path = path
        self.replace = replace
        self.flowgit_directory = os.path.join(self.path, ".flowgit")
        self.config = FlowGitConfigManager(self.flowgit_directory)

    def _load_flowgit_ignore(self, file_path = ".gitignore"):

        file_path = os.path.join(self.path, file_path)
        if not os.path.exists(file_path):
            return []

        with open(file_path, "r") as file:
            content = file.readlines()
        specs = pathspec.PathSpec.from_lines("gitwildmatch", content)

        # get list of files in working tree
        file_list = set()
        for path, dirs, files in os.walk(self.path):
            if ".flowgit" in path:
                continue
            for file in files:
                file_path = os.path.join(path, file)
                file_path = file_path.replace(self.path + "/", "")
                file_list.add(file_path)
        
        ignored_file_paths = ['.flowgit']
        for file in file_list:
            if specs.match_file(file):
                ignored_file_paths.append(file)
        return ignored_file_paths

    def ignored(self) -> None:

        ignored_files = self._load_flowgit_ignore()
        display_success_message(f"Found '{len(ignored_files)}' ignored files")
        for file in ignored_files:
            display_information_message(f"{file}")


    def _is_valid_hash(self, hash: str) -> bool:
        """
        Returns true if the provided hash object exists, else false
        """

        folder_name = hash[:2]
        file_name = hash[2:]

        full_path = os.path.join(self.flowgit_directory, "objects", folder_name, file_name)
        return os.path.exists(full_path)

    def _get_umerged_index_entries(self) -> List[IndexEntry]:
        """
        Get list of entries from index with stage > 0 (unmerged)
        """

        index_file_path = os.path.join(self.flowgit_directory, "index")
        index_entries = read_index(index_file_path)
        unmerged_entries: List[IndexEntry] = []

        for entry in index_entries:
            stage = get_stage_from_index_entry(entry)
            if stage > 0:
                unmerged_entries.append(entry)

        return unmerged_entries
         
    
    def _get_hash_full_folder_path(self, hash: str) -> str:
        """
        Get full path to the hash file in objects folder, return "" if 
        it doesnt exist
        """

        if not self._is_valid_hash(hash):
            return ""
        
        folder_path = os.path.join(self.flowgit_directory, "objects", hash[:2])
        for file in os.listdir(folder_path):
            if file.startswith(hash[2:]):
                return os.path.join(folder_path, file)
            
        return ""
    
    def _parse_tree_row(self, row: str) -> Tuple[int, str, str, str]:
        """
        Parse a tree row string of format
        '<permission> <type> <hash> <name>'
        and return the four values as a tuple
        """

        permission, type, hash, name = row.split(" ", maxsplit=4)
        if len(permission) != 6 or not permission.isdigit() or permission.isalpha():
            display_error_message(f"Invalid format for mode in tree object content.")
            return
        if len(hash) > 40:
            display_error_message(f"Invalid format for hash tree object content.")
            return
        if not self._is_valid_hash(hash):
            display_error_message(f"Object {hash} does not exist.")
            return
        # permission is parsed as octal digit text (e.g. "100644"); convert
        # to a real int so it matches every other TreeEntry.mode construction
        # path and FlowGitTreeObject.serialize()'s oct(entry.mode) call.
        return int(permission, 8), type, name, hash
    
    def _write_object(self, object: FlowGitObject) -> None:
        """
        Call the compress method within FlowHitObject to write
        its content into a hash object within objects folder
        """

        hash = object.oid()
        compressed_data = object.compress()

        save_path_dir = os.path.join(self.flowgit_directory, "objects", hash[:2])
        save_path = os.path.join(save_path_dir, hash[2:])

        if not os.path.exists(save_path_dir):
            os.makedirs(save_path_dir)

        with open(save_path, "wb+") as file:
            file.write(compressed_data)

        # display_creation_message(f"{save_path}")

    def initalize_flowgit(self) -> None:
        """
        Initialize the .flowgit directory
        """

        # check if valid folder
        if not os.path.isdir(self.path):
            raise NotADirectoryError(f"Folder '{self.path}' not found")

        # skip initialization or remove folder based on create option
        if os.path.isdir(self.flowgit_directory):
            if not self.replace:
                display_warning_message("Skipping flowgit initialization as folder already exists")
                return
            else:
                shutil.rmtree(self.flowgit_directory)
        
        # create flowgit folder
        os.mkdir(self.flowgit_directory)
        display_creation_message(".flowgit/")

        # create config folder
        self.config = FlowGitConfigManager(self.flowgit_directory)
        self.config.initialize_config()

        # create sub directories
        sub_directories = ["objects"]
        for directory in sub_directories:
            sub_path = os.path.join(self.flowgit_directory, directory)
            os.mkdir(sub_path)
            display_creation_message(f".flowgit/{directory}/")

        # create HEAD file
        head_file = os.path.join(self.flowgit_directory, "HEAD")
        with open(head_file, "w+") as file:
            file.write("ref: refs/heads/main")

        # create refs/ and refs/heads/ folder
        refs_folder = os.path.join(self.flowgit_directory, "refs")
        os.mkdir(refs_folder)
        heads_folder = os.path.join(self.flowgit_directory, "refs", "heads")
        os.mkdir(heads_folder)

    def hash_object(self, content: bytes, type: ObjectType, write: bool = False) -> FlowGitBlobObject:
        """
        Creates a blob hash object out of content and type.
        If write is true, writes the file onto the objects folder
        """
        
        # create git blob and get compressed blob and hash
        object = None
        if type == ObjectType.blob:
            object = blob.FlowGitBlobObject(content)
        else:
            display_error_message(f"Currently flowgit doesnt support commit, tree and tag object creation using hash-object")
            return
        if write:
            self._write_object(object)
        else:
            display_creation_message(f"{object.oid()}")

        return object

    def read_object(self, object: str, display_info: bool = True) -> FlowGitBlobObject:
        """
        Reads the object from its hash value
        """
    
        full_file_path = self._get_hash_full_folder_path(object)
        if not full_file_path:
            display_error_message(f"Object with hash {object} not found")
            return
        
        if display_info:
            display_success_message(f"Found {full_file_path}")                
        
        content = bytes()
        with open(full_file_path, "rb") as file:
            content = file.read()

        decompressed_bytes = zlib.decompress(content)
        null_idx = decompressed_bytes.index(b"\x00")
        header = decompressed_bytes[:null_idx].decode()
        type, size = header.split(" ")

        if type == ObjectType.blob.value:
            object = FlowGitBlobObject.deserialize(decompressed_bytes[null_idx+1:])
            try:
                content = object.data.decode("utf-8")
            except UnicodeDecodeError:
                content = f"<binary file {len(object.data)} bytes>"
        
        elif type == ObjectType.tree.value:
            tree_entries = FlowGitTreeObject.deserialize(decompressed_bytes[null_idx+1:])
            object = FlowGitTreeObject()
            object.entries = tree_entries
            content =  "\n".join([f"{e.mode} {e.oid} {e.type} {e.name}" for e in tree_entries])
        
        elif type == ObjectType.commit.value:
            commit_info = FlowGitCommitObject.deserialize(decompressed_bytes[null_idx+1:])
            author_tagger = Tagger(
                name = commit_info['author'].decode(),
                email = commit_info['author_email'].decode().replace(">", "").replace("<", ""),
                timestamp = commit_info['author_timestamp'].decode().replace(">", "").replace("<", ""),
                timezone = commit_info['author_timezone'].decode().replace(">", "").replace("<", "")
            )
            committer_tagger = Tagger(
                name = commit_info['committer'].decode(),
                email = commit_info['committer_email'].decode().replace(">", "").replace("<", ""),
                timestamp = commit_info['committer_timestamp'].decode().replace(">", "").replace("<", ""),
                timezone = commit_info['committer_timezone'].decode().replace(">", "").replace("<", "")
            )
            object = FlowGitCommitObject(
                tree = commit_info['tree'].decode(),
                parent = [parent.decode() for parent in commit_info['parent']],
                author_tagger = author_tagger,
                committer_tagger = committer_tagger,
                message = commit_info['message'] if commit_info['message'] else ""
            )
            content = object.serialize().decode()

        elif type == ObjectType.tag.value:
            tag_info = FlowGitTagObject.deserialize(decompressed_bytes[null_idx+1:])
            object = FlowGitTagObject(
                sha = tag_info['object'],
                type = tag_info['type'],
                name = tag_info['tag'],
                message = tag_info['message'],
                tagger = tag_info['tagger']
            )
            content = object.serialize().decode()

        # display information
        if display_info: 
            display_information_message(f"Type: {type}")
            display_information_message(f"Size: {size}")
            display_information_message(f"Content: \n\n{content}")

        # return object
        return object

    def make_tree_from_entries(self, tree_entries: list[TreeEntry]) -> FlowGitTreeObject:
        """
        Returns a tree object created from list of tree entries
        """
        
        # create tree object
        tree = FlowGitTreeObject()
        for entry in tree_entries:
            tree.add(entry.mode, entry.type, entry.name, entry.oid)
        
        # save the tree object
        hash = tree.oid()
        compressed = tree.compress()
        self._write_object(tree)

        return tree

    def make_tree(self, content: str) -> FlowGitTreeObject:
        """
        Create a tree object based on the content of the tree
        """
        
        # check content format
        if " " not in content:
            display_error_message(f"Invalid format for tree object content.")
            return
        
        # check permission, name and hash
        entries: List[TreeEntry] = []
        lines = content.split("\n")
        for entry in lines:
            out = self._parse_tree_row(entry)
            if not out:
                return
            permission, type, name, hash = out
            entries.append(TreeEntry(permission, type, name, hash))

        return self.make_tree_from_entries(entries)

    def commit_tree(self, tree: str, parents: List[str], message: str) -> FlowGitCommitObject:
        """
        Creates a commit object based on tree sha, parent(s) and commit message
        """

        # check if tree and parents exist or not
        tree_path = self._get_hash_full_folder_path(tree)
        if not tree_path:
            display_error_message(f"Object with hash {tree} not found")
            return
        if len(parents):
            for parent in parents:
                parent_path = self._get_hash_full_folder_path(parent)
                if not parent_path:
                    display_error_message(f"Object with hash {parent} not found")
                    return
            
        config = self.config.get_config()
        author_tagger = Tagger(
            name = config['user']['name'],
            email = config['user']['email'],
            timestamp="",
            timezone=""
        )
        committer_tagger = Tagger(
            name = config['user']['name'],
            email = config['user']['email'],
            timestamp="",
            timezone=""
        )
            
        # create commit object
        commit = FlowGitCommitObject(
            tree=tree,
            parent=parents,
            message=message,
            author_tagger=author_tagger,
            committer_tagger=committer_tagger
        )

        # write commit object
        self._write_object(commit)
        return commit

    def make_tag(self, object: str, type: str, name: str, message: Optional[str]) -> None:
        """
        Create a tag object from sha, type, name and message
        """

        config = self.config.get_config()
        tagger = Tagger(
            name = config['user']['name'],
            email = config['user']['email'],
            timestamp=str(_get_current_timestamp()),
            timezone=_get_timezone_difference()
        )
        tag_object = FlowGitTagObject(
            sha=object, type=type, name=name, message=message, tagger=tagger
        )
        self._write_object(tag_object)

    def create_index_entry_from_file(self, file_path: str, merge_stage: int = 0, relative_path: str = None) -> IndexEntry:
        """
        Create index entry from an existing file.

        `file_path` is the path actually used to read/stat the file from
        disk (may be absolute). `relative_path` is what gets recorded as the
        entry's path and used to compute flags - it must stay relative to
        self.path regardless of where file_path points, since the index
        format (and every reader of it) expects entry.path to be relative to
        the repo root, not to the caller's cwd. Defaults to file_path so
        call sites that already pass a self.path-relative path (assuming
        cwd == self.path) keep working unchanged.
        """

        relative_path = relative_path if relative_path is not None else file_path

        # check if file exists
        if not os.path.exists(file_path):
            display_error_message(f"File {file_path} does not exist")

        # read file content as bytes
        content = bytes()
        with open(file_path, "rb") as f:
            content = f.read()

        # store file content as blob object
        object = self.hash_object(content, ObjectType.blob, True)
        sha1 = object.oid(hexdigest=False).digest()
        display_success_message(f"Added/Updated {relative_path} file")

        # get file stats
        stat = os.stat(file_path)

        # create IndexEntry object
        ctime_s = int(stat.st_ctime)
        ctime_ns = int((stat.st_ctime % 1) * 1_000_000_000)

        mtime_s = int(stat.st_mtime)
        mtime_ns = int((stat.st_mtime % 1) * 1_000_000_000)

        dev = stat.st_dev
        ino = stat.st_ino
        uid = stat.st_uid
        gid = stat.st_gid
        size = stat.st_size

        import stat as s
        raw = stat.st_mode
        if s.S_ISLNK(raw):
            mode = 0o120000 
        elif raw & s.S_IXUSR:
            mode = 0o100755
        else:
            mode = 0o100644    

        index_entry = IndexEntry(
            ctime_s = ctime_s,
            ctime_ns = ctime_ns,
            mtime_s = mtime_s,
            mtime_ns = mtime_ns,
            dev = dev,
            ino = ino,
            uid = uid,
            gid = gid,
            size = size,
            sha1 = sha1,
            mode = mode,
            flags = make_flags(relative_path, merge_stage),
            path = relative_path
        )
        return index_entry

    def create_index_entry_from_sha(self, sha: str, file_path: str, merge_stage: int = 0, mode: int = 0o100644) -> IndexEntry:
        """
        Create index entry from an existing sha blob
        """

        # check if sha exists
        if not self._is_valid_hash(sha):
            display_error_message(f"Object {sha} does not exist")
            raise ValueError(f"Object {sha} does not exist")

        # get blob object
        blob_object = self.read_object(sha, display_info=False)

        # create index entry
        index_entry = IndexEntry(
            ctime_s = 0,
            ctime_ns = 0,
            mtime_s = 0,
            mtime_ns = 0,
            dev = 0,
            ino = 0,
            uid = 0,
            gid = 0,
            size = len(blob_object.data),
            mode = mode,
            sha1 = bytes.fromhex(sha),
            flags = make_flags(file_path, merge_stage),
            path = file_path
        )
        return index_entry
    

    def _is_file_modified(self, entry: IndexEntry, file_path: str) -> bool:
        """
        Returns true if the current file is modified from the provided index entry
        """

        if not os.path.exists(file_path):
            return True

        stat = os.stat(file_path)

        # fast path: size or (second-granularity) mtime differing is a
        # definite modification, no need to read/hash the file
        if stat.st_size != entry.size or int(stat.st_mtime) != entry.mtime_s:
            return True

        # size/mtime alone can't distinguish a same-size edit made within the
        # same wall-clock second as the last staged mtime - confirm by
        # hashing actual content against the staged sha1 before declaring
        # the file unmodified
        with open(file_path, "rb") as file:
            content = file.read()
        current_sha1 = blob.FlowGitBlobObject(content).oid(hexdigest=False).digest()

        return current_sha1 != entry.sha1

    def update_index(self, add: list[str], remove: list[str], info: bool, list: bool):
        """
        Updates the index file by adding/removing files from it
        """

        added_files = 0
        removed_files = 0

        if info and list:
            display_error_message(f"Only one of the two options can be enabled at a time: index-info, list")
            return
        
        if len(add):

            # read existing entries
            index_path = os.path.join(self.flowgit_directory, "index")
            entries: list[IndexEntry] = read_index(index_path)

            # create path -> IndexEntry mapping
            path_entry_mapping = {}
            for entry in entries:
                path_entry_mapping[entry.path] = entry

            for file in add:
                file_full_path = os.path.join(self.path, file)
                if not file in path_entry_mapping or (
                    file in path_entry_mapping and 
                    self._is_file_modified(path_entry_mapping[file], file_full_path)
                ):
                    index_entry = self.create_index_entry_from_file(file_full_path, relative_path=file)
                    path_entry_mapping[file] = index_entry
                    added_files += 1

            # write to index file
            entries = []
            for key in path_entry_mapping:
                entries.append(path_entry_mapping[key])
            write_index(index_path, entries)

        if len(remove):

            # read existing entries
            index_path = os.path.join(self.flowgit_directory, "index")
            entries: list[IndexEntry] = read_index(index_path)

            # create path -> IndexEntry mapping
            path_entry_mapping = {}
            for entry in entries:
                path_entry_mapping[entry.path] = entry

            for file in remove:
                if file in path_entry_mapping:
                    path_entry_mapping.pop(file, None)
                    display_success_message(f"Removed {file} from index")
                    removed_files += 1
            
            # write to index file
            entries = []
            for key in path_entry_mapping:
                entries.append(path_entry_mapping[key])
            write_index(index_path, entries)

        if info:

            index_path = os.path.join(self.flowgit_directory, "index")
            entries = read_index(index_path)
            display_success_message(f"Read {index_path} file")

            for index, entry in enumerate(entries):
                print()
                display_information_message(f"Index entry: {index+1}\n")
                display_information_message(f"ctime_s: {entry.ctime_s}")
                display_information_message(f"ctime_ns: {entry.ctime_ns}")
                display_information_message(f"mtime_s: {entry.mtime_s}")
                display_information_message(f"mtime_ns: {entry.mtime_ns}")
                display_information_message(f"dev: {entry.dev}")
                display_information_message(f"ino: {entry.ino}")
                display_information_message(f"uid: {entry.uid}")
                display_information_message(f"gid: {entry.gid}")
                display_information_message(f"size: {entry.size}")
                display_information_message(f"sha: {entry.sha1.hex()}")
                display_information_message(f"flags: {entry.flags}")
                display_information_message(f"path: {entry.path}")

            
        if list:

            index_path = os.path.join(self.flowgit_directory, "index")
            entries = read_index(index_path)
            display_success_message(f"Read {index_path} file")

            for index, entry in enumerate(entries):
                print()
                display_information_message(f"Index entry: {index+1}\n")
                display_information_message(f"size: {entry.size}")
                display_information_message(f"sha: {entry.sha1.hex()}")
                display_information_message(f"path: {entry.path}") 

        return added_files, removed_files

    def create_recursive_tree_structure(self, entries: list[IndexEntry]) -> dict:
        """
        Create a recursive list of index entries
        """

        root = {}
        for entry in entries:
            parts = entry.path.split("/")
            node = root
            for part in parts[:-1]:
                if part not in node:
                    node[part] = {}
                node = node[part]
            node[parts[-1]] = entry
        return root

    def write_tree_recursive(self, node: dict) -> str:
        """
        Calls itself recursively to create a list of index entries 
        """
        
        tree_entries = []
        for name, value in sorted(node.items()):
            if isinstance(value, dict):
                child_sha = self.write_tree_recursive(value)
                tree_entry = TreeEntry(
                    mode=0o040000,
                    type="tree",
                    name=name,
                    oid=child_sha
                )
                tree_entries.append(tree_entry)
            else:
                tree_entry = TreeEntry(
                    mode=value.mode,
                    type="blob",
                    name=name,
                    oid=value.sha1.hex()
                )
                tree_entries.append(tree_entry)
        tree = self.make_tree_from_entries(tree_entries)
        return tree.oid()

    def write_tree(self) -> str:
        """
        Create tree object from current files in the index
        """
        
        # read index entries
        index_file_path = os.path.join(self.flowgit_directory, "index")
        index_entries = read_index(index_file_path)

        # create a dictionary object storing the tree structure
        root = self.create_recursive_tree_structure(index_entries)
        root_sha = self.write_tree_recursive(root)
        display_creation_message(root_sha)

        # return root sha
        return root_sha

    def update_ref(self, ref_path: str, sha: str) -> None:
        """
        Update commit reference sha for a branch
        """
        
        # validate sha
        if not self._is_valid_hash(sha):
            display_error_message(f"Object {sha} not found")
            return

        full_ref_path = os.path.join(self.flowgit_directory, ref_path)
        if not os.path.exists(full_ref_path):
            os.makedirs(os.path.dirname(full_ref_path), exist_ok=True)
        
        with open(full_ref_path, "w+") as file:
            file.write(sha + "\n")

        display_success_message(f"Updated {ref_path} => {sha}")

    def read_tree_index_entry_recursive(self, sha: str, prefix="") -> list[IndexEntry]:
        """
        Read a tree object and return list of index entries from it
        """

        # validate sha
        if not self._is_valid_hash(sha):
            display_error_message(f"Tree {sha} not found")
            return

        # read tree object
        tree = self.read_object(sha, display_info=False)

        # read entries and add them to IndexEntry list
        index_entries = []
        for entry in tree.entries:
            if entry.type == "blob":
                blob_object = self.read_object(entry.oid, display_info=False)
                file_path = "/".join([prefix, entry.name]) if len(prefix) else entry.name
                index_entries.append(IndexEntry(
                    ctime_s = 0,
                    ctime_ns = 0,
                    mtime_s = 0,
                    mtime_ns = 0,
                    dev = 0,
                    ino = 0,
                    uid = 0,
                    gid = 0,
                    size = len(blob_object.data),
                    mode = int(entry.mode, 8),
                    sha1 = bytes.fromhex(entry.oid),
                    flags = make_flags(file_path, 0),
                    path = file_path
                ))
            elif entry.type == "tree":
                if prefix and entry.name:
                    new_prefix = "/".join([prefix, entry.name])
                else:
                    new_prefix = entry.name
                index_entries.extend(
                    self.read_tree_index_entry_recursive(entry.oid, prefix=new_prefix)
                )

        return index_entries
    
    def read_tree(self, sha: str) -> None:
        """
        Read a tree and write it to index
        """

        # validate sha
        if not self._is_valid_hash(sha):
            display_error_message(f"Tree {sha} not found")
            return

        # read tree object
        tree = self.read_object(sha, display_info=False)

        # read entries and add them to IndexEntry list
        index_entries = self.read_tree_index_entry_recursive(sha)

        # write the index entries in index file
        index_file_path = os.path.join(self.flowgit_directory, "index")
        write_index(index_file_path, index_entries)

        # success message
        display_success_message(f"Index file updated successfully ...")

    def checkout_index(self, files: list[str], all: bool, force: bool):
        """
        Read index file and use it to create/update files
        """

        # read index file entries
        index_file_path = os.path.join(self.flowgit_directory, "index")
        index_entries = read_index(index_file_path)

        # track whether wer need to persist refreshed stat info back to the index
        index_updated = False

        # iterate through the entries, and if file is missing, create it
        for entry in index_entries:

            # if all is not enabled, only check entries which 
            # are in files list
            if not all and entry.path not in files:
                continue

            # check if file path exists or not
            file_path = os.path.join(self.path, entry.path)
            file_path_obj = Path(file_path)

            # if it doesnt exist, create the file
            if not os.path.exists(file_path) or force:

                # validate sha
                sha = entry.sha1.hex()
                if not self._is_valid_hash(sha):
                    display_error_message(f"SHA entry in index file {sha} not found")
                    return

                # read blob object
                blob = self.read_object(sha, display_info=False)

                # if its within a folder, create it
                if "/" in file_path:
                    file_path_obj.parent.mkdir(parents=True, exist_ok=True)

                # write the file content
                with open(file_path, "wb+") as file:
                    file.write(blob.data)

                # refresh this entry's stat metadata to match the file we
                # just wrote, so status() doesnt think its mdoified
                new_stat = os.stat(file_path)
                entry.ctime_s = int(new_stat.st_ctime)
                entry.ctime_ns = int((new_stat.st_ctime % 1) * 1_000_000_000)
                entry.mtime_s = int(new_stat.st_mtime)
                entry.mtime_ns = int((new_stat.st_mtime % 1) * 1_000_000_000)
                entry.dev = new_stat.st_dev
                entry.ino = new_stat.st_ino
                entry.uid = new_stat.st_uid
                entry.gid = new_stat.st_gid
                entry.size = new_stat.st_size
                index_updated = True

                # display_success_message(f"Created {entry.path} file")

        if index_updated:
            write_index(index_file_path, index_entries)


    def checkout(self, commit_sha: str) -> None:
        """
        Update the index and working tree to a previous commit sha
        """

        # check if hash exist or not
        if not self._is_valid_hash(commit_sha):
            display_error_message(f"Object '{commit_sha}' does not exist")
            return

        # read object
        commit_object = self.read_object(commit_sha, display_info=False)

        # read current commit sha
        current_commit_sha = self._resolve_head()
        if not current_commit_sha:
            display_error_message(f"Flowgit cannot identify current commit to switch from")
            return

        # switch between commits
        self._switch_to_commit(current_commit_sha, commit_sha)

        # update HEAD to point to the new commit
        head_path = os.path.join(self.flowgit_directory, "HEAD")
        with open(head_path, "w") as file:
            file.write(commit_sha)

        display_success_message(f"HEAD is now at {commit_sha}")

    def _resolve_head(self) -> str | None:
        """
        Return the content from current HEAD file
        """

        # get head path
        head_path = os.path.join(self.flowgit_directory, "HEAD")
        if not os.path.exists(head_path):
            return None

        content = open(head_path).read().strip()

        if content.startswith("ref: "):
            ref_path = os.path.join(self.flowgit_directory, content[5:])
            if not os.path.exists(ref_path):
                return None
            return open(ref_path).read().strip()
        return content

    def _resolve_head_branch(self) -> Tuple[str, bool] | None:
        """
        Return the name of the branch the current head is pointing to
        """

        # get head path
        head_path = os.path.join(self.flowgit_directory, "HEAD")
        if not os.path.exists(head_path):
            return None, False

        # ref points to a branch
        content = open(head_path).read().strip()
        if content.startswith("ref: "):
            return content[5:].replace("refs/heads/", ""), False

        # ref points to detached commit
        return content, True

    def _list_all_branches(self) -> list[str]:
        """
        List all the branches that exist locally
        """

        # read all files in refs/heads
        refs_heads_folder_path = os.path.join(self.flowgit_directory, "refs", "heads")
        if not os.path.exists(refs_heads_folder_path):
            raise FileNotFoundError(f"No valid '.flowgit/refs/heads' found")

        # return list of all files
        return os.listdir(refs_heads_folder_path)

    def add(self, files: list[str]) -> None:
        """
        Iterate through all the files in the working directory and add them to index 
        """

        # reject if no files entry provided
        if not len(files):
           display_error_message(f"Specify files or '.' to continue")
           return

        # get list of gitignored files
        ignored_paths = self._load_flowgit_ignore()

        # get index file entries
        index_file_path = os.path.join(self.flowgit_directory, "index")
        index_entries = read_index(index_file_path)
        index_entry_mapping = {}
        for entry in index_entries:
            index_entry_mapping[entry.path] = entry

        # get list of files to be added
        file_list = set(files)
        if '.' in files:
            file_list.discard(".")
            for path, dirs, files in os.walk(self.path):
                if ".flowgit" in path:
                    continue
                for file in files:
                    
                    # get relative file path
                    file_path = os.path.join(path, file)
                    file_path = file_path.replace(self.path + "/", "")

                    # ignore file path if its in ignored_paths
                    if file_path in ignored_paths:
                        continue

                    # check index entry
                    if file_path in index_entry_mapping:
                        index_entry = index_entry_mapping[file_path]
                        if self._is_file_modified(index_entry, file_path):
                            file_list.add(file_path)
                    else:
                        file_list.add(file_path)

        # walk index file entries to get list of removed files
        removed_files = []
        for entry in index_entries:
            file_full_path = os.path.join(self.path, entry.path)
            if not os.path.exists(file_full_path):
                removed_files.append(entry.path)

        # run update-index add for all these file paths
        added, removed = self.update_index(file_list, removed_files, False, False)
        display_success_message(f"Added {added} files and removed {removed} files")

    def commit(self, message: str) -> None:
        """
        Read files from index and write it to a commit object and update current branch head
        """

        # check if index currently has stage > 0 entriess
        unmerged_entries = self._get_umerged_index_entries()
        unmerged_paths = set([e.path for e in unmerged_entries])
        if len(unmerged_paths):
            display_warning_message(f"Found '{len(unmerged_paths)}' file(s) still in merge conflicts")
            for path in unmerged_paths:
                display_warning_message(f"{path}")
            display_warning_message(f"Please resolve these merges before proceeding")
            return

        # check to see if merge files exists or not, if they do, make a merge commit
        head_file_content, message_file_content = self._get_merge_file_contents()

        # run write-tree to write all index file entries into a tree object
        tree_sha = self.write_tree()

        # resolve head and get parent
        parent = self._resolve_head()

        # run commit tree to create commit object
        if len(head_file_content) and len(message_file_content):
            commit_obj = self.commit_tree(tree_sha, [parent, head_file_content], message if len(message) else message_file_content)
            self._delete_merge_files() # since the merge commit is made, merge is resolved, so delete the related files
        else:
            commit_obj = self.commit_tree(tree_sha, [parent] if parent else [], message)

        # check where head points to
        curr_branch, detached = self._resolve_head_branch()

        # update ref
        if not detached:
            self.update_ref(f"refs/heads/{curr_branch}", commit_obj.oid())

    def branch(self, new_branch: str, delete_branch: str) -> None:
        """
        Branch related commands, create new/delete existing or list all branches
        """

        if len(new_branch) and len(delete_branch):
            display_error_message(f"Cannot delete and create branch in one command. Please run two separate commands for the same.")
            return

        # read current branch
        curr_branch, detached = self._resolve_head_branch()

        # resolve head commit
        head_sha = self._resolve_head()

        # read all branches
        branches = self._list_all_branches()

        if not len(new_branch) and not len(delete_branch):

            # list all branches
            if detached:
                display_information_message(f"* (HEAD detached at {curr_branch})")
                return
            
            for branch_name in branches:
                if branch_name == curr_branch:
                    display_information_message(f"* {branch_name}")
                else:
                    display_information_message(f"  {branch_name}")


        if len(new_branch):

            # check if branch already exists
            if new_branch in branches:
                display_warning_message(f" Branch '{new_branch}' already exists...skipping creation")
                return
                
            # update ref
            self.update_ref(f"refs/heads/{new_branch}", head_sha)

            # update HEAD to new branch
            head_file_path = os.path.join(self.flowgit_directory, "HEAD")
            with open(head_file_path, "w") as file:
                file.write(f"ref: refs/heads/{new_branch}")
            display_information_message("updated ref to new branch")

        
        if len(delete_branch):

            # check if its in the list of branches
            if delete_branch not in branches:
                display_warning_message(f" Branch '{delete_branch}' does not exist...skipping deletion")
                return

            # check if its the current branch
            if delete_branch == curr_branch:
                display_warning_message(f" Cannot delete current branch. Please switch branches before deletion.")
                return

            # delete branch file
            delete_branch_path = os.path.join(self.flowgit_directory, "refs", "heads", delete_branch)
            os.remove(delete_branch_path)
            display_success_message(f"Deleted branch {delete_branch}")

    def _switch_to_commit(self, current_commit_sha: str, branch_commit_sha: str) -> None:

        # check if sha commit exists
        if not self._is_valid_hash(current_commit_sha):
            display_error_message(f"Object '{current_commit_sha}' does not exist")
            return
        if not self._is_valid_hash(branch_commit_sha):
            display_error_message(f"Object '{branch_commit_sha}' does not exist")
            return

        # get list of paths in current commit
        current_paths = set()
        if current_commit_sha:
            current_commit = self.read_object(current_commit_sha, False)
            current_entries = self.read_tree_index_entry_recursive(current_commit.tree)
            current_paths = {e.path for e in current_entries}

        # get list of paths in branch commit
        branch_commit = self.read_object(branch_commit_sha, False)
        branch_entries = self.read_tree_index_entry_recursive(branch_commit.tree)
        branch_paths = {e.path for e in branch_entries}

        # detect and delete files in current_paths and not in branch_paths
        paths_to_delete = current_paths - branch_paths
        for path in paths_to_delete:
            file_path = os.path.join(self.path, path)
            if os.path.exists(file_path):
                os.remove(file_path)

            # also remove parent folders
            parent = os.path.dirname(file_path)
            while (
                os.path.isdir(parent)
                and not os.listdir(parent)
                and os.path.abspath(parent) != os.path.abspath(self.path)
            ):
                os.rmdir(parent)
                parent = os.path.dirname(parent)

        # load the tree entries into index
        self.read_tree(branch_commit.tree)

        # checkout index
        self.checkout_index([], True, True)
 
    def switch(self, branch_name: str, switch_to_new_branch: bool = True) -> None:
        """
        Switch between branches
        """

        # list all branches and check if this branch exists or not
        branches = self._list_all_branches()
        if branch_name not in branches:
            display_error_message(f"Branch {branch_name} does not exist")
            return

        # get current commit sha
        current_commit_sha = self._resolve_head()
        
        # get branch commit sha
        branch_path = os.path.join(self.flowgit_directory, "refs", "heads", branch_name)
        branch_commit_sha = open(branch_path).read().strip()

        # switch between commits
        self._switch_to_commit(current_commit_sha, branch_commit_sha)

        # update HEAD to new branch
        if switch_to_new_branch:
            head_path = os.path.join(self.flowgit_directory, "HEAD")
            with open(head_path, "w") as file:
                file.write(f"ref: refs/heads/{branch_name}")

            # success message
            display_success_message(f"Switched to '{branch_name}' branch")

    def log(self) -> None:
        """
        List down all the commits within the current branch
        """

        # get current commit sha
        current_commit_sha = self._resolve_head()

        # walk the full commit graph reachable from HEAD, not just the
        # first-parent chain - a merge commit's second (and later) parents
        # need to be followed too, or commits unique to a merged-in branch
        # are never reached. `visited` guards against re-visiting a commit
        # both chains converge on, and against infinite loops.
        visited = set()
        stack = [current_commit_sha] if current_commit_sha else []
        commits = []

        while stack:
            sha = stack.pop()
            if not sha or sha in visited:
                continue
            visited.add(sha)

            commit_object = self.read_object(sha, display_info=False)
            commits.append((sha, commit_object))

            for parent_sha in commit_object.parent:
                if parent_sha not in visited:
                    stack.append(parent_sha)

        # newest first, same as before for a linear history
        commits.sort(key=lambda entry: float(entry[1].author_timestamp), reverse=True)

        for sha, commit_object in commits:

            # display commit info
            if len(commit_object.parent) >= 2:
                display_information_message("[MERGE_COMMIT]")
            display_information_message(f"commit {sha}")
            display_information_message(f"Author: {commit_object.author} <{commit_object.author_email}>")
            display_information_message(f"Date: {int(float(commit_object.author_timestamp))}")
            print()
            if commit_object.message:
                display_information_message(f"\t{commit_object.message}")
            print("\n")

    def _get_staged_changes_status(self) -> tuple[list[str], list[str], list[str]]:
        """
        Get status of staged files. (Files between staged and last commit)
        """

        # read index file entries
        index_file_path = os.path.join(self.flowgit_directory, "index")
        index_entries = read_index(index_file_path)

        # read commit entries
        commit_sha = self._resolve_head()
        if not commit_sha:
            commit_index_entries = []
        else:
            commit_object = self.read_object(commit_sha, display_info=False)
            commit_index_entries = self.read_tree_index_entry_recursive(commit_object.tree)

        # get list of index and commit tree file paths
        index_entry_dict = {}
        commit_entry_dict = {}
        for entry in index_entries:
            index_entry_dict[entry.path] = entry.sha1.hex()
        for entry in commit_index_entries:
            commit_entry_dict[entry.path] = entry.sha1.hex()

        # track files
        new_files = []
        modified_files = []
        deleted_files = []

        # get new files
        for key in index_entry_dict:
            if key not in commit_entry_dict:
                new_files.append(key)
            elif index_entry_dict[key] != commit_entry_dict[key]:
                modified_files.append(key)
            
        # get deleted files
        for key in commit_entry_dict:
            if key not in index_entry_dict:
                deleted_files.append(key)

        # return data
        return new_files, modified_files, deleted_files

    def _get_unstaged_changes_status(self) -> tuple[list[str], list[str], list[str]]:
        """
        Get unstaged file status. (Files between working tree and staging area)
        """

        # read index file entries
        index_file_path = os.path.join(self.flowgit_directory, "index")
        index_entries = read_index(index_file_path)
        index_entry_path_set = set([e.path for e in index_entries])

        # read ignored file
        ignored_paths = self._load_flowgit_ignore()

        index_entry_dict = {}
        for entry in index_entries:
            index_entry_dict[entry.path] = entry.sha1.hex()

        # get list of files in working tree
        file_list = set()
        for path, dirs, files in os.walk(self.path):
            if ".flowgit" in path:
                continue
            for file in files:
                file_path = os.path.join(path, file)
                file_path = file_path.replace(self.path + "/", "")

                if file_path in ignored_paths:
                    continue
                file_list.add(file_path)

        # track files
        untracked_files = []
        modified_files = []
        deleted_files = []

        for entry in index_entries:
            full_file_path = os.path.join(self.path, entry.path)
            if not os.path.exists(full_file_path):
                deleted_files.append(entry.path)
            elif entry.path in file_list and self._is_file_modified(entry, full_file_path):
                modified_files.append(entry.path)

        for path in file_list:
            if path not in index_entry_path_set:
                untracked_files.append(path)

        return untracked_files, modified_files, deleted_files

    def status(self) -> None:
        """
        Get current file status (branch, unstaged files, staged files)
        """

        current_branch, detached = self._resolve_head_branch()
        display_information_message(f"Branch: {current_branch}\n")

        has_uncommited_files = False
        has_unstaged_files = False
        has_untracked_files = False

        new_files, modified_files, deleted_files = self._get_staged_changes_status()
        if len(new_files) or len(modified_files) or len(deleted_files):
            has_uncommited_files = True
            print(f"Changed to be committed: ")
            print(f"  (use \"flowgit restore --staged <file> ...\" to unstage)")
            for file in set(new_files):
                display_success_message(f"    new file: {file}")
            for file in set(modified_files):
                display_warning_message(f"    modified: {file}")
            for file in set(deleted_files):
                display_error_message(f"   deleted: {file}")

            print("\n\n")

        untracked_files, modified_files, deleted_files = self._get_unstaged_changes_status()
        if len(modified_files) or len(deleted_files):
            has_unstaged_files = True
            print(f"Changed not staged for commit: ")
            print(f"  (use \"flowgit add <file>...\" to update what will be committed)")
            for file in set(modified_files):
                display_warning_message(f"    modified: {file}")
            for file in set(deleted_files):
                display_error_message(f"   deleted: {file}")

            print("\n\n")

        if len(untracked_files):
            has_untracked_files = True
            print("\n\nUntracked files:")
            print(f"  (use \"git add <file>...\" to include in what will be committed)")
            for file in set(untracked_files):
                display_warning_message(f"    {file}")

        if not has_uncommited_files and not has_unstaged_files and not has_untracked_files:
            print(f"nothing to commit, working tree clean")


    def restore(self, staged: bool) -> None:
        """
        Restore files from either commit or staged state
        """

        # iterate through files in the index and replace them with index content
        if not staged:

            # read index entries
            index_file_path = os.path.join(self.flowgit_directory, "index")
            index_entries = read_index(index_file_path)        
            
            for entry in index_entries:

                if os.path.exists(entry.path):

                    # read current file content
                    current_file_content = b""
                    with open(entry.path, "rb") as file:
                        current_file_content = file.read()

                    # read index file content
                    file_blob_object = self.read_object(entry.sha1.hex(), display_info=False)
                    index_file_content = file_blob_object.data

                    # if contents dont match, restore it
                    if current_file_content != index_file_content:
                        with open(entry.path, "wb+") as file:
                            file.write(index_file_content)
                        display_warning_message(f"Modified {entry.path}")

                else:

                    # read index file content
                    file_blob_object = self.read_object(entry.sha1.hex(), display_info=False)
                    index_file_content = file_blob_object.data

                    # write content to file
                    with open(entry.path, "wb+") as file:
                        file.write(index_file_content)
                    display_success_message(f"Added {entry.path}")

        # if staged, restore files from last commit
        else:

            # get last commit tree sha
            commit_sha = self._resolve_head()
            if not commit_sha:
                display_error_message(f"No commits yet, nothing to restore from")
                return
            commit_object = self.read_object(commit_sha, display_info = False)
            tree_sha = commit_object.tree

            # get tree index entries
            tree_index_entries = self.read_tree_index_entry_recursive(tree_sha)
            for entry in tree_index_entries:

                if os.path.exists(entry.path):

                    # read current file content
                    current_file_content = b""
                    with open(entry.path, "rb") as file:
                        current_file_content = file.read()

                    # read index file content
                    file_blob_object = self.read_object(entry.sha1.hex(), display_info=False)
                    index_file_content = file_blob_object.data

                    # if contents dont match, restore it
                    if current_file_content != index_file_content:
                        with open(entry.path, "wb+") as file:
                            file.write(index_file_content)
                        display_warning_message(f"Modified {entry.path}")

                else:

                    # read index file content
                    file_blob_object = self.read_object(entry.sha1.hex(), display_info=False)
                    index_file_content = file_blob_object.data

                    # write content to file
                    with open(entry.path, "wb+") as file:
                        file.write(index_file_content)
                    display_success_message(f"Added {entry.path}")


    def _return_diff_content(self, old_file_content: bytes, new_file_content: bytes, filepath: str) -> str:
        """
        Return differences between two file contents
        """

        old_content = old_file_content
        new_content = new_file_content

        try:

            # file is utf-8 decodable
            old_content = old_content.decode()
            new_content = new_content.decode()

            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{filepath}", tofile=f"b/{filepath}")
            output = "".join(list(diff))

            if len(output):
                output = f"diff --flowgit a/{filepath} b/{filepath}\n" + output
            return output

        except UnicodeDecodeError:

            # file is binary, just give generic diff message
            output = f"Binary files a/{filepath} and b/{filepath} differ"
            return output

    def diff(self, staged: bool) -> None:
        """
        Show differences in files locally (either staged or unstaged)
        """

        # iterate through files in the index and replace them with index content
        if not staged:

            # read index entries
            index_file_path = os.path.join(self.flowgit_directory, "index")
            index_entries = read_index(index_file_path)       

            for entry in index_entries:
                if os.path.exists(entry.path) and self._is_file_modified(entry, entry.path):
                    new_content = open(entry.path, "rb").read()
                    file_blob_object = self.read_object(entry.sha1.hex(), display_info=False)
                    old_content = file_blob_object.data
                    diff_output = self._return_diff_content(old_content, new_content, entry.path)
                    if len(diff_output):
                        print(diff_output)

        else:

            # read commit tree entries
            commit_sha = self._resolve_head()
            if not commit_sha:
                display_error_message(f"No commits yet, nothing to diff against")
                return
            commit_object = self.read_object(commit_sha, display_info=False)
            tree_entries = self.read_tree_index_entry_recursive(commit_object.tree)

            for entry in tree_entries:
                if os.path.exists(entry.path) and self._is_file_modified(entry, entry.path):
                    new_content = open(entry.path, "rb").read()
                    file_blob_object = self.read_object(entry.sha1.hex(), display_info=False)
                    old_content = file_blob_object.data
                    diff_output = self._return_diff_content(old_content, new_content, entry.path)
                    if len(diff_output):
                        print(diff_output)

    
    def _find_common_ancestors(self, sha1: str, sha2: str) -> str | None:
        """
        Find common commits between two commit (iterate through their ancestors)
        """

        # collect all ancestors of sha1
        ancestors = set()
        current = sha1
        while current:
            ancestors.add(current)
            commit = self.read_object(current, display_info=False)
            parents_list = commit.parent
            if len(parents_list) == 0:
                current = None
            else:
                current = parents_list[0]

        # walk sha2 chain until we hit one ancestor
        current = sha2
        while current:
            if current in ancestors:
                return current
            commit = self.read_object(current, display_info=False)
            parents_list = commit.parent
            if len(parents_list) == 0:
                current = None
            else:
                current = parents_list[0]

        return None


    def _create_merge_start_files(self, current_branch_name: str, merge_branch_name: str, merge_branch_sha: str) -> None:
        """
        Creates MERGE_HEAD and MERGE_MSG files in cases of true merge
        """
        head_file_path = os.path.join(self.flowgit_directory, "MERGE_HEAD")
        message_file_path = os.path.join(self.flowgit_directory, "MERGE_MSG")

        # create head file
        with open(head_file_path, "w+") as file:
            file.write(merge_branch_sha)

        # create message file
        with open(message_file_path, "w+") as file:
            file.write(f"Merge branch '{merge_branch_name}' into '{current_branch_name}'")


    def _delete_merge_files(self) -> None:
        """
        Deletes MERGE_HEAD and MERGE_MSG files
        """
        head_file_path = os.path.join(self.flowgit_directory, "MERGE_HEAD")
        message_file_path = os.path.join(self.flowgit_directory, "MERGE_MSG")

        for path in [head_file_path, message_file_path]:
            if os.path.exists(path):
                os.remove(path)


    def _get_merge_file_contents(self) -> Tuple[str, str]:
        """
        Reads and returns content from MERGE_HEAD and MERGE_MSG files
        """
        head_file_path = os.path.join(self.flowgit_directory, "MERGE_HEAD")
        message_file_path = os.path.join(self.flowgit_directory, "MERGE_MSG")

        head_file_content = ""
        message_file_content = ""

        if os.path.exists(head_file_path):
            with open(head_file_path, "r") as file:
                head_file_content = file.read()

        if os.path.exists(message_file_path):
            with open(message_file_path, "r") as file:
                message_file_content = file.read()

        return (head_file_content, message_file_content)


    def _handle_true_merge(self, ancestor_sha: str, current_sha: str, merge_sha: str) -> Union[Dict[str, str], List, List]:
        """
        Handles true merge condition between ancestor, current and merge branch
        """

        # get commit objects
        ancestor_commit = self.read_object(ancestor_sha, display_info=False)
        current_commit = self.read_object(current_sha, display_info=False)
        merge_commit = self.read_object(merge_sha, display_info=False)

        # get tree entries
        ancestor_entries = self.read_tree_index_entry_recursive(ancestor_commit.tree)
        current_entries = self.read_tree_index_entry_recursive(current_commit.tree)
        merge_entries = self.read_tree_index_entry_recursive(merge_commit.tree)

        # generate path -> sha dicts for lookup
        ancestor = {e.path: e.sha1.hex() for e in ancestor_entries}
        current = {e.path: e.sha1.hex() for e in current_entries}
        merge = {e.path: e.sha1.hex() for e in merge_entries}

        # get all paths
        all_paths = set(ancestor) | set(current) | set(merge)

        # store results
        updated_paths: Dict[str, str] = {}
        removed_paths = set()
        conflicted_paths = set()

        # check all combinations
        for path in all_paths:

            if path in ancestor:

                in_current = path in current
                in_incoming = path in merge

                # deleted in both sides -> can be safely removed
                if not in_current and not in_incoming:
                    removed_paths.add(path)

                # file existed in current but not
                # in incoming branch
                elif not in_incoming:

                    if current[path] == ancestor[path]:
                        removed_paths.add(path) # unmodified -> delete
                    else:
                        conflicted_paths.add(path) # modified -> conflict

                # delete in current, still in merge
                elif not in_current:
                    if merge[path] == ancestor[path]:
                        removed_paths.add(path)
                    else:
                        conflicted_paths.add(path)

                elif current[path] == ancestor[path] and merge[path] == ancestor[path]:
                    updated_paths[path] = current[path]

                elif current[path] != ancestor[path] and merge[path] == ancestor[path]:
                    updated_paths[path] = current[path]

                elif current[path] == ancestor[path] and merge[path] != ancestor[path]:
                    updated_paths[path] = merge[path]

                else:
                    conflicted_paths.add(path)

            else:

                # new path, not present in the common ancestor
                if path in current and path not in merge:
                    updated_paths[path] = current[path]

                elif path not in current and path in merge:
                    updated_paths[path] = merge[path]

                elif current[path] == merge[path]:
                    updated_paths[path] = current[path]

                else:
                    conflicted_paths.add(path)

        return updated_paths, list(removed_paths), list(conflicted_paths)


    def _check_merging(self) -> bool:
        """
        Returns true if MERGE_HEAD file exists else false
        """
        file_path = os.path.join(self.flowgit_directory, "MERGE_HEAD")
        return os.path.exists(file_path)


    def _add_conflict_markers(self, paths: List[str], current_sha: str, merge_sha: str) -> None:
        """
        Add markers within conflict files
        """

        # get commit objects
        current_commit = self.read_object(current_sha, display_info=False)
        merge_commit = self.read_object(merge_sha, display_info=False)

        # get tree entries
        current_entries = self.read_tree_index_entry_recursive(current_commit.tree)
        merge_entries = self.read_tree_index_entry_recursive(merge_commit.tree)

        # generate path -> sha dicts for lookup
        current = {e.path: e.sha1.hex() for e in current_entries}
        merge = {e.path: e.sha1.hex() for e in merge_entries}

        for path in paths:

            final_content = []

            if path not in current and path in merge:
                new_content = self.read_object(merge[path], display_info=False).data.decode()
                final_content.extend([
                    f"{HEAD_MARKER} current",
                    f"{MIDDLE_MARKER}",
                    new_content,
                    f"{INCOMING_MARKER} incoming"
                ])

            elif path in current and path not in merge:
                old_content = self.read_object(current[path], display_info=False).data.decode()
                final_content.extend([
                    f"{HEAD_MARKER} current",
                    old_content,
                    f"{MIDDLE_MARKER}",
                    f"{INCOMING_MARKER} incoming"
                ])

            else:

                old_blob = self.read_object(current[path], display_info=False)
                new_blob = self.read_object(merge[path], display_info=False)

                old_content = old_blob.data.decode()
                new_content = new_blob.data.decode()

                old_lines = old_content.split("\n")
                new_lines = new_content.split("\n")

                ops = get_content_difference_difflib(old_content, new_content)

                for tag, i1, i2, j1, j2 in ops:
                    if tag == 'equal':
                        final_content.extend(old_lines[i1:i2])
                    elif tag == 'insert':
                        lines = [f"{HEAD_MARKER} current"]
                        lines.append(f"{MIDDLE_MARKER}")
                        lines.extend(new_lines[j1:j2])
                        lines.append(f"{INCOMING_MARKER} incoming")
                        final_content.extend(lines)
                    elif tag == 'delete':
                        lines = [f"{HEAD_MARKER} current"]
                        lines.extend(old_lines[i1:i2])
                        lines.append(f"{MIDDLE_MARKER}")
                        lines.append(f"{INCOMING_MARKER} incoming")
                        final_content.extend(lines)
                    elif tag == 'replace':
                        lines = [f"{HEAD_MARKER} current"]
                        lines.extend(old_lines[i1:i2])
                        lines.append(f"{MIDDLE_MARKER}")
                        lines.extend(new_lines[j1:j2])
                        lines.append(f"{INCOMING_MARKER} incoming")
                        final_content.extend(lines)

            with open(path, "w") as file:
                file.write("\n".join(final_content))


    def _update_conflict_file_indexes(self, paths: List[str], ancestor_sha: str, current_sha: str, merge_sha: str) -> None:
        """
        Update index file entries for these files
        """

        # get commit objects
        ancestor_commit = self.read_object(ancestor_sha, display_info=False)
        current_commit = self.read_object(current_sha, display_info=False)
        merge_commit = self.read_object(merge_sha, display_info=False)

        # get tree entries
        ancestor_entries = self.read_tree_index_entry_recursive(ancestor_commit.tree)
        current_entries = self.read_tree_index_entry_recursive(current_commit.tree)
        merge_entries = self.read_tree_index_entry_recursive(merge_commit.tree)

        # generate path -> IndexEntry dicts for lookup - keeping the whole
        # entry (not just the blob sha) so the real file mode carries
        # through to the conflict-stage entries below
        ancestor = {e.path: e for e in ancestor_entries}
        current = {e.path: e for e in current_entries}
        merge = {e.path: e for e in merge_entries}

        index_entries: List[IndexEntry] = []

        # for each file in paths, get ancestor, current and merge blob sha and create index entries from it
        for path in paths:

            # create index entries
            if path in ancestor:
                entry = ancestor[path]
                ancestor_entry = self.create_index_entry_from_sha(entry.sha1.hex(), path, 1, mode=entry.mode)
                index_entries.append(ancestor_entry)
            if path in current:
                entry = current[path]
                current_entry = self.create_index_entry_from_sha(entry.sha1.hex(), path, 2, mode=entry.mode)
                index_entries.append(current_entry)
            if path in merge:
                entry = merge[path]
                merge_entry = self.create_index_entry_from_sha(entry.sha1.hex(), path, 3, mode=entry.mode)
                index_entries.append(merge_entry)

        index_file_path = os.path.join(self.flowgit_directory, "index")
        all_entries = read_index(index_file_path)
        all_entries.extend(index_entries)

        # remove conflicting path stage 0 entries
        filtered_entries = []
        for entry in all_entries:
            if entry.path in paths:
                stage = get_stage_from_index_entry(entry)
                if stage > 0:
                    filtered_entries.append(entry)
            else:
                filtered_entries.append(entry)

        write_index(index_file_path, filtered_entries)

    def _merge_commits(self, current_commit_sha: str, current_branch_name: str, merge_branch_commit_sha: str, merge_branch_name: str):
        """
        Finds common ancestor -> Performs fast-forward check -> Performs three way merge -> Perforna conflict handling
        """

        # to check for fast-forward or true merge, find common ancestor
        common_ancestor_sha = self._find_common_ancestors(current_commit_sha, merge_branch_commit_sha)
        
        # if common ancestor sha matches current branch latest commit
        # means its a fast forward situation
        if common_ancestor_sha == current_commit_sha:
            self.update_ref(f"refs/heads/{current_branch_name}", merge_branch_commit_sha)
            self._switch_to_commit(current_commit_sha, merge_branch_commit_sha)
            display_success_message(f"'{current_branch_name}' fast forwarded to '{merge_branch_name}'")
            return

        # in case of true merge, find common ancestor
        common_ancestor_sha = self._find_common_ancestors(current_commit_sha, merge_branch_commit_sha)
        
        # if no common ancestor, refuse to merge unrelated histories
        if not common_ancestor_sha:
            display_error_message(f"fatal: refusing to merge unrelated histories")
            return

        # get file updates based on true merge
        self._create_merge_start_files(current_branch_name, merge_branch_name, merge_branch_commit_sha)
        updated_paths, removed_paths, conflicting_paths = self._handle_true_merge(common_ancestor_sha, current_commit_sha, merge_branch_commit_sha)

        current_commit_obj = self.read_object(current_commit_sha, display_info=False)
        merge_commit_obj = self.read_object(merge_branch_commit_sha, display_info=False)
        current_tree_entries = {e.path: e for e in self.read_tree_index_entry_recursive(current_commit_obj.tree)}
        merge_tree_entries = {e.path: e for e in self.read_tree_index_entry_recursive(merge_commit_obj.tree)}

        # read current index
        index_path = os.path.join(self.flowgit_directory, "index")
        index_entries: List[IndexEntry] = read_index(index_path)
        index_path_entry_mapping: Dict[str, IndexEntry] = {}
        for entry in index_entries:
            index_path_entry_mapping[entry.path] = entry

        # store updated index entries
        updated_index_entries_map: Dict[str, IndexEntry] = {}

        # iterate through update/added files
        for path in updated_paths:
            sha = updated_paths[path]
            if self._is_valid_hash(sha):

                # index entry for the path exists, update SHA
                if path in index_path_entry_mapping:
                    index_entry = index_path_entry_mapping[path]
                    index_entry.sha1 = bytes.fromhex(sha)
                    updated_index_entries_map[path] = index_entry

                # if path doesnt exist, add a new entry for it
                else:
                    source_entry = current_tree_entries.get(path) or merge_tree_entries.get(path)
                    mode = source_entry.mode if source_entry else 0o100644
                    index_entry = self.create_index_entry_from_sha(sha, path, mode=mode)
                    updated_index_entries_map[path] = index_entry

        for path in removed_paths:
            if path in index_path_entry_mapping:
                del index_path_entry_mapping[path]

        for path, entry in updated_index_entries_map.items():
            index_path_entry_mapping[path] = entry

        # convert into list of index entries
        final_index_entries = list([index_path_entry_mapping[path] for path in index_path_entry_mapping])

        # write changes to index
        write_index(index_path, final_index_entries)

        for path in removed_paths:
            file_path = os.path.join(self.path, path)
            if os.path.exists(file_path):
                os.remove(file_path)

            # also remove now-empty parent folders
            parent = os.path.dirname(file_path)
            while (
                os.path.isdir(parent)
                and not os.listdir(parent)
                and os.path.abspath(parent) != os.path.abspath(self.path)
            ):
                os.rmdir(parent)
                parent = os.path.dirname(parent)

        # update files from index
        self.checkout_index([], True, True)

        # log conflicting paths
        if len(conflicting_paths):

            display_success_message(f"Found '{len(conflicting_paths)}' conflicting paths")
            for path in conflicting_paths:
                display_information_message(f"Conflicting: {path}")
            display_warning_message(f"Automatic merge failed: fix conflicts and then commit the results")
        
            # now for each conflicting file, update markers
            self._add_conflict_markers(conflicting_paths, current_commit_sha, merge_branch_commit_sha)

            # for each conflicting file, update index to add different stages
            self._update_conflict_file_indexes(conflicting_paths, common_ancestor_sha, current_commit_sha, merge_branch_commit_sha)

        else:

            # if no conflicting paths are found, the three way merge was successful and a merge commit should be automatically be made
            # get current tree sha
            tree_sha = self.write_tree()

            # create commit object from it
            merge_commit_object = self.commit_tree(tree_sha, [current_commit_sha, merge_branch_commit_sha], f"Merge branch '{merge_branch_name}' into '{current_branch_name}'")

            # update HEAD pointer
            self.update_ref(f"refs/heads/{current_branch_name}", merge_commit_object.oid())

            # remove MERGE_HEAD and MERGE_MSG files as the merge was successful
            self._delete_merge_files()

            
    def merge(self, merge_branch: str) -> None:
        """
        Merge two branches
        """

        # check if merging
        if self._check_merging():
            display_error_message("You have not concluded your merge.")
            return

        # get current branch
        current_branch, detached = self._resolve_head_branch()
        if current_branch == merge_branch:
            display_error_message(f"Already on '{current_branch}', cannot merge it to itself")
            return

        # check if merge_branch exists or not
        branches = self._list_all_branches()
        if merge_branch not in branches:
            display_error_message(f"Branch '{merge_branch}' does not exist")
            return

        # get current branch and merge branch latest commit
        current_commit_sha = self._resolve_head()
        merge_branch_path = os.path.join(self.flowgit_directory, "refs", "heads", merge_branch)
        merge_branch_commit_sha = open(merge_branch_path).read().strip()

        # both have same commit, nothing to do
        if current_commit_sha == merge_branch_commit_sha:
            display_success_message("Already up to date.")
            return

        self._merge_commits(current_commit_sha, current_branch, merge_branch_commit_sha, merge_branch)

    def _get_remote_type(self, remote: str) -> Union[str, Literal['filesystem', 'https', '']]:

        # get remote url value from config
        remote_url = self.config.get_value(f"remote \"{remote}\"", "url")
        if not remote_url:
            return "", ""

        # if https in remote url, then remote type is https:
        if "http" in remote_url:
            return remote_url, "https"
        else:
            return remote_url, "filesystem"

    def _fetch_from_filesystem(self, remote: str, url: str, branch: str):
        """
        Fetches from filesystem type url (code on separate folder)
        """

        # check and read refs/heads/<branch>
        ref_path = os.path.join(url, "refs", "heads", branch)
        if not os.path.exists(ref_path):
            pass
    

    def fetch(self, remote: str) -> bool:
        """
        Fetch refs and objects from a remote via the real git binary,
        without touching the working tree or moving any local branch
        """

        # branch name: get current branch
        current_branch_name = self._resolve_head_branch()

        # add refs/remotes/<remote-name>/<branch>
        ref_path = os.path.join(self.flowgit_directory, "refs", "remotes", remote, "main")
        if not os.path.exists(ref_path):
            self.update_ref(f"refs/remotes/{remote}/main", "")

        # check if to pass filesystem fetch or https fetch
        remote_url, remote_type = self._get_remote_type(remote)
        if remote_type == 'filesystem':
            self._fetch_from_filesystem(remote, remote_url, current_branch_name)
        elif remote_type == 'https':
            self._fetch_from_https(remote, remote_url)
        else:
            display_error_message(f"Invalid remote url for remote '{remote}': '{remote_url}'")

    def remote(self, action: str, name: str = "", url: str = "") -> None:
        """
        Manage remotes (add/remove/list), delegated to the real git binary
        """
        if action not in ['add', 'remove', 'list', 'get-url', 'set-url']:
            display_error_message(f"Invalid remote action '{action}'")
            return

        if action == 'add':
            section_name = f"remote \"{name}\""
            if self.config.is_section_exist(section_name):
                display_error_message(f"Remote '{name}' already set, skipping override ...")
                return
            self.config.set_value(section_name, 'url', url)

        elif action == 'remove':
            section_name = f"remote \"{name}\""
            if not self.config.is_section_exist(section_name):
                display_warning_message(f"Remote '{name}' does not exist, skipping removal ...")
                return
            self.config.remove_section(section_name)

        elif action == 'list':
            configurations = self.config.get_config()
            for key in configurations:
                if 'remote' in key:
                    name = key.replace("remote \"", "").replace("\"", "")
                    print(f"{name} -> {configurations[key]['url']}")

        elif action == 'get-url':
            section_name = f"remote \"{name}\""
            value = self.config.get_value(section_name, 'url')
            if value:
                display_success_message(value)
            else:
                display_error_message(f"No url found for remote '{name}'")

        elif action == 'set-url':
            section_name = f"remote \"{name}\""
            self.config.set_value(section_name, 'url', url)
            display_success_message(f"Remote updated successfullys")

    def _clone_tree_object(self, remote_repo: Repository, tree_sha: str): 
        """
        Clone a tree object and call itself recursively
        """

        # create tree object
        tree_object: FlowGitTreeObject = remote_repo.read_object(tree_sha, False)

        # iterate through its entries
        for entry in tree_object.entries:

            # if entry type is blob, copy the entry from remote repo
            # to the current repo
            if entry.type == 'blob':

                # if sha exists, skip creation
                sha = entry.oid
                if self._is_valid_hash(sha):
                    continue

                remote_object: FlowGitBlobObject = remote_repo.read_object(sha, False)
                self._write_object(remote_object)

            # if entry type is tree, then recursively call this method
            # to iterate through the tree
            if entry.type == 'tree':

                # iterate through the objects of the tree
                self._clone_tree_object(remote_repo, entry.oid)

        # clone this tree object also
        self._write_object(tree_object)

    def _clone_commit_object(self, remote_repo: Repository, commit_sha: str):
        """
        Clones a commit object from remote repository to current repository
        """

        # get current commit object
        current_commit_object: FlowGitCommitObject = remote_repo.read_object(commit_sha, False)

        # clone tree object
        self._clone_tree_object(remote_repo, current_commit_object.tree)

        # clone this commit object
        self._write_object(current_commit_object)


    def _clone_branch_from_remote_filesystem(self, url: str, branch: str) -> str:
        """
        Clones all the objects from the remote filesystem based repository's branch.
        Returns the tip commit of the branch
        """

        # create remote repository object
        remote_repository = Repository(url)

        # check if .flowgit directory exist or not
        remote_flowgit_directory = os.path.join(url, ".flowgit")
        if not os.path.exists(remote_flowgit_directory):
            display_error_message(f"Folder '{url}' is not a flowgit tracked repository")
            return

        # display informational message
        display_information_message(f"Cloning objects for branch '{branch}' from remote repository ...")

        # read refs/heads/<branch> value
        branch_ref_file = os.path.join(remote_flowgit_directory, "refs", "heads", branch)
        if not os.path.exists(branch_ref_file):
            display_error_message(f"Branch '{branch}' does not exist on remote repository")
            return
        branch_ref_value = ""
        with open(branch_ref_file, "r") as file:
            branch_ref_value = file.read().strip()

        # iterate through the commit graph
        current_commit_object: FlowGitCommitObject = remote_repository.read_object(branch_ref_value, False)
        start_commit = current_commit_object
        parents = current_commit_object.parent

        # clone commit objects
        self._clone_commit_object(remote_repository, current_commit_object.oid())

        # iterate through its parents
        while len(parents):

            # clone parents
            for parent in parents:
                self._clone_commit_object(remote_repository, parent)

            parent = parents[0]
            commit_object: FlowGitCommitObject = self.read_object(parent, False)
            parents = commit_object.parent

        display_success_message(f"Branch '{branch}' cloned from remote repository successfully.")

        return start_commit.oid()


    def _clone_filesystem_repository(self, url: str, remote_fetch: bool = False, remote_name: str = 'origin', clone_branches: List[str] = []):
        """
        Clones a repository from filesystem onto the current folder
        """

        # check if .flowgit directory exist or not
        remote_flowgit_directory = os.path.join(url, ".flowgit")
        if not os.path.exists(remote_flowgit_directory):
            display_error_message(f"Folder '{url}' is not a flowgit tracked repository")
            return

        # initialize remote repository
        remote_repository = Repository(url)
        if not remote_fetch:
            self.initalize_flowgit()

        branches = clone_branches if len(clone_branches) else remote_repository._list_all_branches()
        for branch in branches:

            # clone remote branch
            branch_tip_commit = self._clone_branch_from_remote_filesystem(url, branch)

            # update ref
            if not remote_fetch:
                self.update_ref(f"refs/heads/{branch}", branch_tip_commit)
            else:
                self.update_ref(f"refs/remotes/{remote_name}/{branch}", branch_tip_commit)

        # run switch to populate files on main branch
        if not remote_fetch:

            # get remote's default branch
            remote_default_branch_name, _ = remote_repository._resolve_head_branch()
            self.switch(remote_default_branch_name)

    def clone(self, url: str):
        """
        Clones a repository from a filesystem or https url to the current folder
        """

        if any(Path(self.path).iterdir()):
            display_error_message("Current folder is non-empty. Please empty it before cloning a repository.")
            return

        if not "http" in url and not any(Path(url).iterdir()):
            display_success_message("Remote folder is empty, unable to clone empty folder.")
            return

        if "http" in url:
            self._clone_https_repository(url)
        else:
            self._clone_filesystem_repository(url)


    def fetch_remote(self, remote: str):
        """
        Fetches the new changes from remote and update in local refs/remotes/origin/<branch>
        """

        # get url from config
        url = self.config.get_value(f"remote \"{remote}\"", 'url')
        if not url:
            display_warning_message(f"No url found for remote '{remote}', set it using:\n\n\tflowgit remote add origin <url>\n")
            return

        # create remote repository object
        remote_repository = Repository(url)

        changed_branches = set()
        for branch in remote_repository._list_all_branches():

            # read branch sha
            remote_ref_path = os.path.join(url, ".flowgit", "refs", "heads", branch)
            with open(remote_ref_path, "r") as file:
                remote_sha = file.read().strip()

            # compare with local ref
            local_ref_path = os.path.join(self.flowgit_directory, "refs", "remotes", remote, branch)
            if not os.path.exists(local_ref_path):
                changed_branches.add(branch)
                continue

            # get local ref commit sha
            with open(local_ref_path, "r") as file:
                local_sha = file.read().strip()

            if local_sha != remote_sha:
                changed_branches.add(branch)

        # for each branch, clone the objects onto remote refs
        self._clone_filesystem_repository(url, True, remote, list(changed_branches))


    def pull_remote(self, remote: str, branch: str):
        """
        Apply changes from fetch
        """

        # get current and remote ref commits
        current_branch_name, detached = self._resolve_head_branch()
        if detached:
            display_error_message("Cannot pull while in a detached HEAD state. Switch to a branch first.")
            return
        current_commit_sha = self._resolve_head()

        self.fetch_remote(remote)
        remote_commit_ref = os.path.join(self.flowgit_directory, "refs", "remotes", remote, branch)
        if not os.path.exists(remote_commit_ref):
            display_error_message(f"Branch '{branch}' does not exist on remote")
            return

        remote_commit_sha = ""
        with open(remote_commit_ref, "r") as file:
            remote_commit_sha = file.read().strip()

        self._merge_commits(current_commit_sha, current_branch_name, remote_commit_sha, f"{remote}/{branch}")

    def push_to_remote(self, remote: str, branch: str):
        """
        Push local changes to remote branch
        """

        # get current branch and sha
        current_branch_name, detached = self._resolve_head_branch()
        current_commit_sha = self._resolve_head()

        # get url from config
        url = self.config.get_value(f"remote \"{remote}\"", 'url')
        if not url:
            display_warning_message(f"No url found for remote '{remote}', set it using:\n\n\tflowgit remote add origin <url>\n")
            return

        # create remote repository
        remote_repository = Repository(url)

        # get remote commit
        remote_commit_ref = os.path.join(url, ".flowgit", "refs", "heads", branch)
        if not os.path.exists(remote_commit_ref):
            remote_repository.branch(branch, "")
        remote_commit_sha = ""
        with open(remote_commit_ref, "r") as file:
            remote_commit_sha = file.read().strip()

        # compare with local remote ref
        local_remote_ref = os.path.join(self.flowgit_directory, "refs", "remotes", remote, branch)
        if not os.path.exists(local_remote_ref):

            # new branch being pushed to remote, allow it
            pass

        else:
            local_remote_sha = ""
            with open(local_remote_ref, "r") as file:
                local_remote_sha = file.read().strip()

            # if local remote and remote sha doesnt match, no fetch was done
            if local_remote_sha != remote_commit_sha:
                display_error_message(f"Please run 'flowgit fetch origin' before running push")
                return

        # perform remote repository operations
        remote_repository._clone_branch_from_remote_filesystem(self.path, branch)
        remote_repository.update_ref(f"refs/heads/{branch}", current_commit_sha)
        remote_repository.switch(branch)
        self.update_ref(f"refs/remotes/{remote}/{branch}", current_commit_sha)