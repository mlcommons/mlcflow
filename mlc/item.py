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
        json_file = os.path.join(self.path, "meta.json")

        if os.path.exists(yaml_file):
            utils.save_yaml(yaml_file, self.meta)
        else:
            # Default to JSON (all cache/experiment entries use meta.json).
            # Previously this branch referenced a non-existent utils.save_
            # helper via a "meta." path that never matched, so metadata writes
            # for meta.json-backed items were silently lost.
            utils.save_json(json_file, meta=self.meta)
