from .RepoAction import RepoAction
from .ScriptAction import ScriptAction
from .CacheAction import CacheAction


# Factory to get the appropriate action class
def get_action(target, parent):
    action_class = actions.get(target, None)
    return action_class(parent) if action_class else None

actions = {
        'repo': RepoAction,
        'script': ScriptAction,
        'cache': CacheAction
    }
