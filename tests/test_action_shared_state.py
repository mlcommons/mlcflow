import os
import tempfile
import unittest

import yaml

from mlc.action import Action
from mlc.action_factory import get_action
from mlc.cache_action import CacheAction
from mlc.repo_action import RepoAction
from mlc.script_action import ScriptAction


class _StubParent:
    """A non-Action parent, as tests/test_script_action_apptainer.py passes."""

    def __init__(self, repos_path=None):
        self.repos_path = repos_path


class ActionSharedStateTest(unittest.TestCase):
    """get_action() builds a throwaway delegate per dispatch, so anything it
    writes to repos/index has to land on the long-lived root that serves the
    next search - not on a private copy that dies with the delegate."""

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

    def _make_repo(self, alias, uid, script_alias, script_uid, tags):
        """A minimal on-disk MLC repo holding a single script."""
        path = os.path.join(self.temp_dir.name, alias)
        script_dir = os.path.join(path, "script", script_alias)
        os.makedirs(script_dir)
        with open(os.path.join(path, "meta.yaml"), "w") as f:
            yaml.safe_dump({"alias": alias, "name": alias, "uid": uid}, f)
        with open(os.path.join(script_dir, "meta.yaml"), "w") as f:
            yaml.safe_dump({
                "alias": script_alias,
                "uid": script_uid,
                "automation_alias": "script",
                "automation_uid": "5b4e0237da074764",
                "tags": list(tags),
            }, f)
        return path

    def test_every_delegate_shares_one_state_object(self):
        delegates = [get_action(t, self.root)
                     for t in ("repo", "script", "cache", "experiment")]

        for delegate in delegates:
            self.assertIs(delegate.state, self.root.state)

    def test_delegate_write_to_repos_is_visible_on_the_root(self):
        repo_action = get_action("repo", self.root)

        # Assignment, not in-place mutation: this is what register_repo() does,
        # and it is what used to rebind a private copy onto the delegate.
        repo_action.repos = repo_action.repos + ["sentinel"]

        self.assertIn("sentinel", self.root.repos)
        self.assertEqual(self.root.repos, repo_action.repos)

    def test_root_write_to_repos_is_visible_on_a_delegate(self):
        script_action = get_action("script", self.root)
        self.root.repos = self.root.repos + ["sentinel"]

        self.assertIn("sentinel", script_action.repos)

    def test_index_built_by_a_delegate_is_the_one_the_root_serves(self):
        # Order matters: the delegate exists before any index does, which is
        # the case register_repo() hits. An index it builds must be the index a
        # later search reads, or the pull's add_repo() call is thrown away.
        repo_action = get_action("repo", self.root)
        self.assertIsNone(self.root.state.index)

        index = repo_action.get_index()

        self.assertIs(self.root.get_index(), index)
        self.assertIs(get_action("script", self.root).get_index(), index)

    def test_local_repo_and_current_repo_path_are_shared(self):
        repo_action = get_action("repo", self.root)
        repo_action.local_repo = "acme,0011223344556677"
        repo_action.current_repo_path = "/somewhere/acme"

        self.assertEqual(self.root.local_repo, "acme,0011223344556677")
        self.assertEqual(self.root.current_repo_path, "/somewhere/acme")

    def test_registering_a_repo_is_visible_to_a_later_search(self):
        """The original bug: `mlc run script` auto-pulls, and the search that
        follows in the same process finds nothing."""
        repo_path = self._make_repo(
            "acme@demo-automations", "aa11bb22cc33dd44",
            "demo-script", "1122334455667788", ("demo", "shared-state"))

        # The pull is dispatched to a fresh delegate that is then dropped...
        repo_action = get_action("repo", self.root)
        res = repo_action.register_repo(
            repo_path,
            {"alias": "acme@demo-automations", "uid": "aa11bb22cc33dd44"})
        self.assertEqual(res["return"], 0, res)
        del repo_action

        # ...and the search that follows is served by the root.
        self.assertIn(repo_path, [r.path for r in self.root.repos])

        found = get_action("script", self.root).search(
            {"tags": "demo,shared-state"})
        self.assertEqual(found["return"], 0, found)
        self.assertEqual([item.path for item in found["list"]],
                         [os.path.join(repo_path, "script", "demo-script")])

    def test_startup_config_is_inherited(self):
        delegate = get_action("script", self.root)

        self.assertEqual(delegate.repos_path, self.root.repos_path)
        self.assertEqual(delegate.local_cache_path, self.root.local_cache_path)
        self.assertIs(delegate.parent, self.root)

    def test_non_action_parent_gets_its_own_state(self):
        """A stub parent carries no state to share, so the delegate owns its
        own rather than blowing up or reaching for a global."""
        delegate = ScriptAction(_StubParent(self.temp_dir.name))

        self.assertIsNot(delegate.state, self.root.state)
        self.assertEqual(delegate.repos_path, self.temp_dir.name)
        self.assertEqual(delegate.repos, [])

    def test_subclasses_do_not_reimplement_the_constructor(self):
        """The state sharing lives in Action.__init__; a subclass that defines
        its own __init__ silently opts out of it."""
        for cls in (RepoAction, ScriptAction, CacheAction):
            self.assertIs(cls.__init__, Action.__init__, cls.__name__)


if __name__ == "__main__":
    unittest.main()
