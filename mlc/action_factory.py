from .repo_action import RepoAction
from .script_action import ScriptAction
from .cache_action import CacheAction
from .experiment_action import ExperimentAction


# Factory to get the appropriate action class
def get_action(target, parent):
    action_class = actions.get(target)
    return action_class(parent) if action_class else None

actions = {
        'repo': RepoAction,
        'script': ScriptAction,
        'cache': CacheAction,
        'experiment': ExperimentAction
    }
