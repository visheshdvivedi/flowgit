import os
import configparser

from flowgit.ui.prompt import ask_email, ask_username
from flowgit.ui.console import display_creation_message

class FlowGitConfigManager:
    def __init__(self, flowgit_directory: str):
        self._flowgit_directory = flowgit_directory
        self._config_file_path = os.path.join(self._flowgit_directory, "config")
        self.initialized = os.path.exists(self._config_file_path)
        self.config = configparser.ConfigParser()

        if self.initialized:
            self.config.read(self._config_file_path)

    def initialize_config(self, replace: bool = False):
        if self.initialized and replace:
            self.config.clear()
            
        self.config = configparser.ConfigParser()
        self.config["user"] = {
            "name": ask_username(),
            "email": ask_email()
        }

        with open(self._config_file_path, "w+") as file:
            self.config.write(file)

        display_creation_message(f".flowgit/config")

    def get_config(self):
        return self.config.__dict__['_sections']