"""Behaviours asserted only by reading the code until now.

Covers register D.2 items T9-T12 (register entries B1-B5, B7, B9):

  T9  index purge is scoped, and matches whole path components only
  T10 a meta `git:` declaration wins over what is on disk
  T11 repo add / pull / rm against a non-git registered repo
  T12 uid-tie precedence in register_repo

Each of these was previously "correct by inspection". The code was in fact
right in every case; what was missing was anything that would notice if it
stopped being.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from mlc import utils
from mlc.index import Index


def _write_repo(path, alias, uid, git=None, make_git_dir=False):
    """Create a minimal registered-repo layout on disk."""
    os.makedirs(path, exist_ok=True)
    meta = {"alias": alias, "uid": uid}
    if git is not None:
        meta["git"] = git
    with open(os.path.join(path, "meta.yaml"), "w") as fh:
        for k, v in meta.items():
            fh.write(f"{k}: {json.dumps(v)}\n")
    if make_git_dir:
        os.makedirs(os.path.join(path, ".git"), exist_ok=True)
    return path


class RemoveRepoFromIndexTest(unittest.TestCase):
    """T9 / B4 / B5: purging one repo must not take its neighbours with it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.index = Index(self.root, [])

    def _seed(self, paths):
        self.index.indices = {
            "script": [{"path": p} for p in paths],
            "cache": [],
            "experiment": [],
        }
        self.index.modified_times = {p: 1 for p in paths}

    def test_a_sibling_with_the_same_prefix_is_not_purged(self):
        """The whole point of the separator check.

        `.../mlcommons@mlperf-automations` is a strict string prefix of
        `.../mlcommons@mlperf-automations1`, so a bare startswith would
        silently evict the second repo's entries while removing the first.
        """
        target = os.path.join(self.root, "mlcommons@mlperf-automations")
        sibling = os.path.join(self.root, "mlcommons@mlperf-automations1")
        self._seed([
            os.path.join(target, "script", "a"),
            os.path.join(sibling, "script", "b"),
        ])

        self.index.remove_repo_from_index(target)

        remaining = [e["path"] for e in self.index.indices["script"]]
        self.assertEqual(remaining, [os.path.join(sibling, "script", "b")])
        self.assertEqual(list(self.index.modified_times),
                         [os.path.join(sibling, "script", "b")])

    def test_the_repo_root_itself_is_purged(self):
        """An entry whose path *is* the repo root must go too, not just
        entries nested under it."""
        target = os.path.join(self.root, "repo-a")
        self._seed([target, os.path.join(target, "script", "x")])

        self.index.remove_repo_from_index(target)

        self.assertEqual(self.index.indices["script"], [])
        self.assertEqual(self.index.modified_times, {})

    def test_an_unrelated_repo_is_untouched(self):
        """T9 / B4: the purge is scoped to the named repo."""
        target = os.path.join(self.root, "repo-a")
        other = os.path.join(self.root, "repo-b")
        self._seed([os.path.join(target, "s"), os.path.join(other, "s")])

        self.index.remove_repo_from_index(target)

        self.assertEqual([e["path"] for e in self.index.indices["script"]],
                         [os.path.join(other, "s")])

    def test_purging_a_repo_with_no_entries_writes_nothing(self):
        """`changed` stays False, so neither index file is rewritten."""
        self._seed([os.path.join(self.root, "repo-a", "s")])

        with mock.patch.object(Index, "_save_indices") as save_idx, \
                mock.patch.object(Index, "_save_modified_times") as save_mt:
            self.index.remove_repo_from_index(
                os.path.join(self.root, "repo-never-registered"))

        save_idx.assert_not_called()
        save_mt.assert_not_called()


class GitDeclarationTest(unittest.TestCase):
    """T10 / B7: `git:` in meta.yaml is a declaration and wins."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def test_meta_git_false_beats_an_on_disk_git_dir(self):
        """The case that matters in production: packaged mlc-scripts ships
        `git: false` so nothing tries to git-pull inside site-packages. If a
        stray .git ever appears there, the declaration must still win."""
        p = _write_repo(os.path.join(self.root, "pkg"), "pkg", "u1",
                        git=False, make_git_dir=True)
        self.assertTrue(utils.has_git_dir(p))
        self.assertFalse(utils.is_git_repo(p))

    def test_meta_git_true_beats_a_missing_git_dir(self):
        p = _write_repo(os.path.join(self.root, "claims"), "claims", "u2",
                        git=True, make_git_dir=False)
        self.assertFalse(utils.has_git_dir(p))
        self.assertTrue(utils.is_git_repo(p))

    def test_with_no_declaration_the_disk_decides(self):
        checkout = _write_repo(os.path.join(self.root, "co"), "co", "u3",
                               make_git_dir=True)
        plain = _write_repo(os.path.join(self.root, "plain"), "plain", "u4")
        self.assertTrue(utils.is_git_repo(checkout))
        self.assertFalse(utils.is_git_repo(plain))

    def test_a_git_file_counts_as_a_checkout(self):
        """`.git` is a *file* in a worktree or submodule, so testing for a
        directory alone would misclassify both."""
        p = _write_repo(os.path.join(self.root, "wt"), "wt", "u5")
        with open(os.path.join(p, ".git"), "w") as fh:
            fh.write("gitdir: /elsewhere/.git/worktrees/wt\n")
        self.assertTrue(utils.has_git_dir(p))
        self.assertTrue(utils.is_git_repo(p))

    def test_unreadable_meta_falls_back_to_disk_rather_than_raising(self):
        p = os.path.join(self.root, "broken")
        os.makedirs(p)
        with open(os.path.join(p, "meta.yaml"), "w") as fh:
            fh.write("alias: [unclosed\n")
        os.makedirs(os.path.join(p, ".git"))
        self.assertTrue(utils.is_git_repo(p))


if __name__ == "__main__":
    unittest.main()


class _PinnedRoots(unittest.TestCase):
    """Both roots pinned into a scratch dir.

    MLC_REPOS alone is not enough -- the two roots resolve independently, so
    pinning only the repo root would leave these tests writing into the
    developer's real cache. Both are resolved in Action's constructor, so they
    have to be set before it is built.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.join(self.tmp.name, "repos")
        os.makedirs(self.root)

        self._saved = {k: os.environ.get(k)
                       for k in ("MLC_REPOS", "MLC_CACHE")}
        self.addCleanup(self._restore)
        os.environ["MLC_REPOS"] = self.root
        os.environ["MLC_CACHE"] = self.root

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _action(self):
        from mlc.action import Action
        a = Action()
        a.parent = None
        return a

    def _registered(self):
        with open(os.path.join(self.root, "repos.json")) as fh:
            return json.load(fh)


class NonGitRepoTest(_PinnedRoots):
    """T11 / B1-B3: a registered folder that is not a checkout."""

    def test_add_repo_on_a_plain_folder_does_not_claim_it_is_git(self):
        """B2. Stamping git: True on a plain directory would make every later
        path believe it can git-pull there."""
        folder = os.path.join(self.tmp.name, "plain-folder")
        os.makedirs(folder)

        from mlc.repo_action import RepoAction
        r = RepoAction(self._action()).add({"repo": folder})
        self.assertEqual(r["return"], 0, r.get("error"))

        meta = utils.read_yaml(os.path.join(folder, "meta.yaml"))
        self.assertIn("git", meta)
        self.assertFalse(meta["git"])
        self.assertFalse(utils.is_git_repo(folder))

    def test_pull_declines_on_a_registered_non_git_repo(self):
        """B1. `mlc pull repo <alias>` on a plain folder must say so plainly
        rather than letting git fail with 'repository does not exist'."""
        folder = os.path.join(self.tmp.name, "plain-folder")
        os.makedirs(folder)

        from mlc.repo_action import RepoAction
        repo_action = RepoAction(self._action())
        self.assertEqual(repo_action.add({"repo": folder})["return"], 0)

        alias = os.path.basename(folder)
        r = RepoAction(self._action()).pull({"repo": alias})

        self.assertEqual(r["return"], 1)
        self.assertIn("not a git checkout", r["error"])
        self.assertIn(folder, r["error"])
        # The message has to point somewhere, or it is just a refusal.
        self.assertIn("mlc rm repo", r["error"])

    def test_declining_the_rm_prompt_unregisters_but_keeps_the_folder(self):
        """B3. No checkout means `git status` cannot vouch for the contents,
        so deleting on a guess is the worse failure."""
        folder = _write_repo(os.path.join(
            self.root, "kept"), "kept", "aaaa1111")
        marker = os.path.join(folder, "work.txt")
        with open(marker, "w") as fh:
            fh.write("uncommittable\n")

        from mlc.repo_action import RepoAction
        self.assertEqual(
            RepoAction(self._action()).add({"repo": folder})["return"], 0)
        self.assertIn(folder, self._registered())

        with mock.patch("builtins.input", return_value="no"):
            r = RepoAction(self._action()).rm({"repo": "kept"})

        self.assertEqual(r["return"], 0, r.get("error"))
        self.assertTrue(os.path.isdir(folder),
                        "folder must survive a declined rm")
        self.assertTrue(os.path.isfile(marker))
        self.assertNotIn(folder, self._registered())


class UidTiePrecedenceTest(_PinnedRoots):
    """T12 / B9: which repo wins when two claim the same uid."""

    TIED_UID = "beefbeefbeefbeef"

    def _two_tied_repos(self):
        first = _write_repo(
            os.path.join(self.root, "first"), "first", self.TIED_UID)
        second = _write_repo(
            os.path.join(self.root, "second"), "second", self.TIED_UID)
        return first, second

    def test_an_explicit_registration_displaces_the_incumbent(self):
        """The half that had no coverage. An explicit `mlc add repo` is the
        user asking for this repo by name, so it wins and the incumbent is
        unregistered -- not silently left alongside a duplicate uid."""
        first, second = self._two_tied_repos()

        from mlc.repo_action import RepoAction
        self.assertEqual(
            RepoAction(self._action()).add({"repo": first})["return"], 0)
        self.assertIn(first, self._registered())

        repo_action = RepoAction(self._action())
        repo_action.register_repo(
            second, utils.read_yaml(os.path.join(second, "meta.yaml")))

        registered = self._registered()
        self.assertIn(second, registered)
        self.assertNotIn(first, registered)

    def test_ignore_on_conflict_keeps_the_incumbent(self):
        """The auto-pull half. Registration order is the user's explicit
        action; a repo arriving automatically must not displace it."""
        first, second = self._two_tied_repos()

        from mlc.repo_action import RepoAction
        self.assertEqual(
            RepoAction(self._action()).add({"repo": first})["return"], 0)

        repo_action = RepoAction(self._action())
        r = repo_action.register_repo(
            second,
            utils.read_yaml(os.path.join(second, "meta.yaml")),
            ignore_on_conflict=True)

        self.assertTrue(r.get("conflict"))
        registered = self._registered()
        self.assertIn(first, registered)
        self.assertNotIn(second, registered)

    def test_re_registering_the_same_path_is_a_no_op(self):
        first, _ = self._two_tied_repos()

        from mlc.repo_action import RepoAction
        self.assertEqual(
            RepoAction(self._action()).add({"repo": first})["return"], 0)
        before = self._registered()

        repo_action = RepoAction(self._action())
        repo_action.register_repo(
            first, utils.read_yaml(os.path.join(first, "meta.yaml")))

        self.assertEqual(self._registered(), before)
