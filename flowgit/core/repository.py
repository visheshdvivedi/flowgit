import os
import zlib
from typing import List
from hashlib import sha1
from pathlib import Path

from flowgit.core.objects import *
from flowgit.services.config import FlowGitConfigManager
from flowgit.ui.console import (
    display_warning_message, 
    display_creation_message, 
    display_error_message, 
    display_information_message, 
    display_success_message
)

class Repository:

    def __init__(self, path: str, replace: bool = False):
        self.path = path
        self.replace = replace
        self.flowgit_directory = os.path.join(self.path, ".flowgit")
        self.config = FlowGitConfigManager(self.flowgit_directory)

    def _is_valid_hash(self, hash: str) -> bool:
        folder_name = hash[:2]
        file_name = hash[2:]

        folder_path = os.path.join(self.flowgit_directory, "objects", folder_name)
        if not os.path.exists(folder_path):
            return False
    
        for file in os.listdir(folder_path):
            if file.startswith(file_name):
                return True
            
        return False
    
    def _get_hash_full_folder_path(self, hash: str) -> str:

        if not self._is_valid_hash(hash):
            return ""
        
        folder_path = os.path.join(self.flowgit_directory, "objects", hash[:2])
        for file in os.listdir(folder_path):
            if file.startswith(hash[2:]):
                return os.path.join(folder_path, file)
            
        return ""
    
    def _parse_tree_row(self, row: str):
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
        return permission, type, name, hash
    
    def _write_object(self, object: FlowGitObject):

        hash = object.oid()
        compressed_data = object.compress()

        save_path_dir = os.path.join(self.flowgit_directory, "objects", hash[:2])
        save_path = os.path.join(save_path_dir, hash[2:])

        if not os.path.exists(save_path_dir):
            os.makedirs(save_path_dir)

        with open(save_path, "wb+") as file:
            file.write(compressed_data)

        display_creation_message(f"{save_path}")

    def initalize_flowgit(self):

        # check if valid folder
        if not os.path.isdir(self.path):
            raise NotADirectoryError(f"Folder '{self.path}' not found")

        # skip initialization or remove folder based on create option
        if os.path.isdir(self.flowgit_directory):
            if not self.replace:
                display_warning_message("Skipping flowgit initialization as folder already exists")
                return
            else:
                os.remove(self.flowgit_directory)
        
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

        # create main head
        main_head_file = os.path.join(self.flowgit_directory, "refs", "heads", "main")
        with open(main_head_file, "w+") as file:
            file.write("")

    def hash_object(self, content: bytes, type: ObjectType, write: bool = False):
        
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

    def read_object(self, object: str, display_info: bool = True):
    
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
            object = FlowGitBlobObject(decompressed_bytes[null_idx+1:])
            content = object.data.decode()
        elif type == ObjectType.tree.value:
            object = FlowGitTreeObject()
            tree_entries = FlowGitTreeObject.deserialize(decompressed_bytes[null_idx+1:])
            object.entries = tree_entries
            content =  "\n".join([f"{e.mode} {e.oid} {e.name}" for e in tree_entries])
        elif type == ObjectType.commit.value:
            content = decompressed_bytes[null_idx+1:].decode()

        # display information
        if display_info: 
            display_information_message(f"Type: {type}")
            display_information_message(f"Size: {size}")
            display_information_message(f"Content: \n\n{content}")

        # return object
        return object

    
    def make_tree_from_entries(self, tree_entries: list[TreeEntry]):
        
        # create tree object
        tree = FlowGitTreeObject()
        for entry in tree_entries:
            tree.add(entry.mode, entry.type, entry.name, entry.oid)
        
        # save the tree object
        hash = tree.oid()
        compressed = tree.compress()
        self._write_object(tree)

        return tree


    def make_tree(self, content: str):
        
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

    def commit_tree(self, tree: str, parent: str, message: str):

        # check if tree and parent exist or not
        tree_path = self._get_hash_full_folder_path(tree)
        if not tree_path:
            display_error_message(f"Object with hash {tree} not found")
            return
        if parent:
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
            parent=parent,
            message=message,
            author_tagger=author_tagger,
            committer_tagger=committer_tagger
        )

        # write commit object
        self._write_object(commit)


    def make_tag(self, object: str, type: str, name: str, message: Optional[str]):
        config = self.config.get_config()
        tagger = Tagger(
            name = config['user']['name'],
            email = config['user']['email'],
            timestamp="",
            timezone=""
        )
        tag_object = TagObject(
            object, type, name, tagger, message
        )
        self._write_object(tag_object)


    def create_index_entry_from_file(self, index_file_path: str, file_path: str) -> IndexEntry:
        
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
            flags = min(len(file_path), 0xFFF),
            path = file_path
        )
        return index_entry


    def update_index(self, add: list[str], remove: list[str], info: bool, list: bool):

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
                index_entry = self.create_index_entry_from_file(index_path, file)
                path_entry_mapping[file] = index_entry

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


    def create_recursive_tree_structure(self, entries: list[IndexEntry]):
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

    def write_tree(self):
        
        # read index entries
        index_file_path = os.path.join(self.flowgit_directory, "index")
        index_entries = read_index(index_file_path)

        # create a dictionary object storing the tree structure
        root = self.create_recursive_tree_structure(index_entries)
        root_sha = self.write_tree_recursive(root)
        display_creation_message(root_sha)


    def update_ref(self, ref_path: str, sha: str) -> None:
        
        # validate sha
        if not self._is_valid_hash(sha):
            display_error_message(f"Object {sha} not found")
            return

        ref_path = os.path.join(self.flowgit_directory, ref_path)
        if not os.path.exists(ref_path):
            os.makedirs(os.path.dirname(ref_path), exist_ok=True)
        
        with open(ref_path, "w+") as file:
            file.write(sha + "\n")

        display_success_message(f"Updated {ref_path} => {sha}")


    def read_tree_index_entry_recursive(self, sha: str, prefix="") -> list[IndexEntry]:

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
                blob_content = blob_object.data.decode()
                index_entries.append(IndexEntry(
                    ctime_s = 0,
                    ctime_ns = 0,
                    mtime_s = 0,
                    mtime_ns = 0,
                    dev = 0,
                    ino = 0,
                    uid = 0,
                    gid = 0,
                    size = len(blob_content),
                    mode = int(entry.mode),
                    sha1 = bytes.fromhex(entry.oid),
                    flags = 0,
                    path = "/".join([prefix, entry.name]) if len(prefix) else entry.name
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