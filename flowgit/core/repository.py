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
        return permission, name, hash
    
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

    def read_object(self, object: str):
    
        full_file_path = self._get_hash_full_folder_path(object)
        if not full_file_path:
            display_error_message(f"Object with hash {object} not found")
            return
        
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
        elif type == ObjectType.tree.value:
            tree_entries = FlowGitTreeObject.deserialize(decompressed_bytes[null_idx+1:])
            content =  "\n".join([f"{e.mode} {e.oid} {e.name}" for e in tree_entries])
        
        # display information
        display_information_message(f"Type: {type}")
        display_information_message(f"Size: {size}")
        display_information_message(f"Content: \n\n{content}")

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
            permission, name, hash = out
            entries.append(TreeEntry(permission, name, hash))
        
        # create tree object
        tree = FlowGitTreeObject()
        for entry in entries:
            tree.add(entry.mode, entry.name, entry.oid)
        
        # save the tree object
        hash = tree.oid()
        compressed = tree.compress()
        self._write_object(tree)

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

