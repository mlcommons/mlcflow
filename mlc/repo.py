import os
from . import utils

class Repo:
    def __init__(self, path, meta=None):
        self.path = path
        if meta:
            self.meta = meta
        else:
            self._load_meta()
        
    
    def _load_meta(self):
        yaml_file = os.path.join(self.path, "meta.yaml")

        json_file = os.path.join(self.path, "meta.json")

        if os.path.exists(yaml_file):
            self.repo_meta = utils.read_yaml(yaml_file)
        elif os.path.exists(json_file):
            self.repo_meta = utils.read_json(json_file)
        else:
            logger.info(f"No meta file found in {self.path}")
