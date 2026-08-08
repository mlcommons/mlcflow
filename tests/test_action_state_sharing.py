import os
import tempfile
import unittest

from mlc.action import Action
from mlc.cache_action import CacheAction
from mlc.repo_action import RepoAction
from mlc.script_action import ScriptAction


class _StubParent:
    """A non-Action parent, as the apptainer test passes."""

    def __init__(self, repos_path):
        self.repos_path = repos_path


class ActionStateSharingTest(unittest.TestCase):
    """repos/index live on one owner per process, not on each delegate.

    get_action() builds a fresh delegate per dispatch, so any state a delegate
    keeps privately is thrown away when it returns - and any state it read at
    construction time is a snapshot that goes stale as soon as another delegate
    changes something.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_cwd = os.getcwd()
        self.addCleanup(os.chdir, self.previous_cwd)
        os.chdir(self.temp_dir.name)

        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)
        os.environ["MLC_REPOS"] = os.path.join(self.temp_dir.name, "repos")

        self.root = Action()

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def test_delegate_reads_the_owners_repos(self):
        for action_class in (RepoAction, ScriptAction, CacheAction):
            with self.subTest(action_class=action_class.__name__):
                self.assertIs(
                    action_class(self.root).repos, self.root.repos)

    def test_write_through_delegate_reaches_the_owner(self):
        delegate = RepoAction(self.root)
        sentinel = ["replaced-by-delegate"]

        delegate.repos = sentinel

        self.assertIs(self.root.repos, sentinel)
        self.assertIs(delegate.repos, sentinel)

    def test_existing_delegate_is_not_left_holding_a_stale_copy(self):
        # The order that matters in production: a delegate is constructed, then
        # a *different* delegate (a pull) replaces repos, then the first one is
        # used again for a search.
        searcher = ScriptAction(self.root)
        puller = RepoAction(self.root)
        sentinel = ["pulled"]

        puller.repos = sentinel

        self.assertIs(searcher.repos, sentinel)

    def test_index_is_built_once_and_shared(self):
        root_index = self.root.get_index()

        self.assertIs(RepoAction(self.root).get_index(), root_index)
        self.assertIs(ScriptAction(self.root).get_index(), root_index)

    def test_nested_delegates_resolve_to_the_root(self):
        nested = CacheAction(ScriptAction(self.root))
        sentinel = ["nested"]

        nested.repos = sentinel

        self.assertIs(self.root.repos, sentinel)

    def test_delegate_with_non_action_parent_owns_its_state(self):
        # Nothing to delegate to, so the delegate must not leak writes onto an
        # unrelated object or blow up reading its own repos.
        delegate = ScriptAction(_StubParent(self.temp_dir.name))

        self.assertEqual(delegate.repos, [])
        delegate.repos = ["own"]
        self.assertEqual(delegate.repos, ["own"])
        self.assertEqual(self.root.repos, self.root.repos)

    def test_delegate_without_parent_owns_its_state(self):
        delegate = RepoAction(None)

        self.assertIsNone(delegate.parent)
        self.assertIsNotNone(delegate.repos_path)

    def test_registering_a_repo_is_visible_to_later_delegates(self):
        repo_path = os.path.join(self.temp_dir.name, "repos", "some@repo")
        os.makedirs(repo_path)
        uid = "0123456789abcdef"
        with open(os.path.join(repo_path, "meta.yaml"), "w") as f:
            f.write(f"alias: some@repo\nuid: {uid}\n")

        res = RepoAction(self.root).register_repo(
            repo_path, {"alias": "some@repo", "uid": uid, "path": repo_path})
        self.assertEqual(res["return"], 0)

        # A search dispatched after the pull gets a brand new delegate.
        paths = [repo.path for repo in ScriptAction(self.root).repos]
        self.assertIn(repo_path, paths)


if __name__ == "__main__":
    unittest.main()
