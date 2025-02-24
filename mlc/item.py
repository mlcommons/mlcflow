import os
from .logger import logger
from . import utils

class Item:
    def __init__(self, path, repo):
        self.meta = None
        self.path = path
        self.repo = repo
        self._load_meta()


    def _load_meta(self):
        yaml_file = os.path.join(self.path, "meta.yaml")
        json_file = os.path.join(self.path, "meta.json")

        if os.path.exists(yaml_file):
            self.meta = utils.read_yaml(yaml_file)
        elif os.path.exists(json_file):
            self.meta = utils.read_json(json_file)
        else:
            logger.info(f"No meta file found in {self.path} for {self.meta}")

    def _save_meta(self):
        yaml_file = os.path.join(self.path, "meta.yaml")
        _file = os.path.join(self.path, "meta.")

        if os.path.exists(yaml_file):
            utils.save_yaml(yaml_file, self.meta)
        elif os.path.exists(_file):
            utils.save_(_file, self.meta)
