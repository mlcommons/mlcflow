from .action import Action, default_parent
from .logger import logger
import os
import shutil
from . import utils


class ExperimentAction(Action):
    """
    ################################################################################
    Experiment Action
    ################################################################################
    Currently, the following actions are supported for Experiment:
    1. find/search
    2. show
    3. list
    4. rm

    """

    def __init__(self, parent=None):
        self.parent = parent
        self.__dict__.update(vars(parent))

    def search(self, i):
        """
    ################################################################################
    Target: Experiment
    Action: Find (Alias: Search)
    ################################################################################

    The `find` (or `search`) action retrieves experiments by tags or uid.

    Syntax:

    mlc find experiment --tags=<tags>

    Example Command:

    mlc find experiment --tags=detect,os

        """
        i['target_name'] = "experiment"
        return self.parent.search(i)

    find = search

    def rm(self, i):
        """
    ################################################################################
    Target: Experiment
    Action: Remove (rm)
    ################################################################################

    The `rm` action removes one or more experiments.

    Syntax:

    mlc rm experiment --tags=<tags>
    mlc rm experiment

    Options:
        -f: Force remove without confirmation.
        --all: Remove all matching experiments without individual prompts.

    To remove all experiments:

    mlc rm experiment -f

    Example Commands:

    mlc rm experiment --tags=detect,os
    mlc rm experiment --tags=detect,os -f
    mlc rm experiment -f

        """
        i['target_name'] = "experiment"
        if not i.get('tags') and not i.get('item') and not i.get('details'):
            i['fetch_all'] = True
        return self.parent.rm(i)

    def show(self, args):
        """
    ################################################################################
    Target: Experiment
    Action: Show
    ################################################################################

    Shows experiment entries with their metadata and run folders.

    Syntax:

    mlc show experiment --tags=<tags>

    Example Command:

    mlc show experiment --tags=detect,os

        """
        self.action_type = "experiment"
        res = self.search(args)
        if res['return'] > 0:
            return res

        if not res['list']:
            logger.info("No experiments found.")
            return {'return': 0}

        for item in res['list']:
            print(f"Location: {item.path}")
            print(f"  Tags: {','.join(item.meta.get('tags', []))}")
            print(f"  UID: {item.meta.get('uid', '?')}")
            print(f"  Script: {item.meta.get('script_alias', '?')}")
            # List run folders
            if os.path.isdir(item.path):
                runs = sorted([
                    d for d in os.listdir(item.path)
                    if d.startswith('run_') and os.path.isdir(os.path.join(item.path, d))
                ])
                if runs:
                    print(f"  Runs ({len(runs)}):")
                    for run in runs:
                        print(f"    - {run}")
            print("......................................................")

        return {'return': 0}

    def list(self, args):
        """
    ################################################################################
    Target: Experiment
    Action: List
    ################################################################################

    Lists all experiment entries along with their paths.

    Example Command:

    mlc list experiment

        """
        self.action_type = "experiment"
        run_args = {"fetch_all": True}

        res = self.search(run_args)
        if res['return'] > 0:
            return res

        if not res['list']:
            logger.info("No experiments found.")
            return {'return': 0}

        logger.info(f"Found {len(res['list'])} experiment(s):")
        print("......................................................")
        for item in res['list']:
            tags = ','.join(item.meta.get('tags', []))
            script = item.meta.get('script_alias', '?')
            print(f"  Script: {script}")
            print(f"  Tags: {tags}")
            print(f"  Location: {item.path}")
            print("......................................................")

        return {'return': 0}
