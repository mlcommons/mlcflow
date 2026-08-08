class MLCState:
    """Mutable state shared by every Action instance in a process.

    Action subclasses are throwaway delegates - get_action() builds a fresh one
    per dispatch and drops it when the call returns - but the state they mutate
    has to outlive them, since the long-lived root (`default_parent`) is what
    serves every later search()/find()/rm().

    Delegates hold a *reference* to one of these, never a copy, which is what
    makes a repo registered by RepoAction visible to a later ScriptAction
    search in the same process.

    Everything here is a product of load_repos_and_meta(), so the fields stay
    consistent with each other by being refreshed together.
    """

    def __init__(self):
        self.repos = []           # list of Repo objects
        self.index = None         # Index, built lazily by Action.get_index()
        self.local_repo = None    # "local,<uid>" of the local repo
        self.current_repo_path = None  # registered repo containing cwd, if any
