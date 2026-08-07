from .action import Action, default_parent
from .logger import logger
import os
from . import utils

class ExperimentAction(Action):
    def show(self, args):
        logger.info(f"Showing experiment with identifier: {args.details}")
        return {'return': 0}

    def list(self, args):
        logger.info("Listing all experiments.")
        return {'return': 0}

