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
        self.config["core"] = {
            "repositoryformatversion": "0",
            "filemode": "true",
            "bare": "false",
            "logallrefupdates": "true",
            "ignorecase": "true",
            "precomposeunicode": "true",
        }
        self.config["user"] = {
            "name": ask_username(),
            "email": ask_email()
        }

        with open(self._config_file_path, "w+") as file:
            self.config.write(file)

        display_creation_message(f".flowgit/config")

    def _reread_config(self):
        if not os.path.exists(self._config_file_path):
            self.config = configparser.ConfigParser()
            return
        self.config = configparser.ConfigParser()
        self.config.read(self._config_file_path)

    def get_config(self):
        return self.config.__dict__['_sections']

    def get_value(self, section: str, key: str):
        """
        Read a single config value (e.g. get_value("user", "name")).
        Returns None if the section/key isn't set.
        """
        if self.config.has_option(section, key):
            return self.config.get(section, key)
        return None

    def is_section_exist(self, section: str) -> bool:
        """
        Reads the config file to see if the section exist in config or not
        """
        self._reread_config()
        return self.config.has_section(section)

    def set_value(self, section: str, key: str, value: str) -> None:
        """
        Set a single config value, creating the section if needed, and
        persist it to .flowgit/config immediately.
        """

        # reread latest config values
        self._reread_config()
            
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)

        with open(self._config_file_path, "w+") as file:
            self.config.write(file)

    def remove_section(self, section: str) -> None:
        """
        Remove a section from the config and persist it to
        .flowgit/config immediately
        """

        # read latest config values
        self._reread_config()

        if not self.config.has_section(section):
            return
        self.config.remove_section(section)

        with open(self._config_file_path, "w+") as file:
            self.config.write(file)