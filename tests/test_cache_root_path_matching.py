"""A7 / C6: the cache root is found by the *first* path component called
`local`, not by the one that actually introduces the cache.

Harmless while the root is `~/MLC/repos`, which contains no other `local`.
Since MLC_CACHE became independently configurable any root containing a
`local` component -- `/usr/local/share/mlc` is the obvious one -- makes the
match land on the wrong component.

The two call sites fail differently, which is why both are here:

  docker_utils.get_host_path / get_container_path  -- actively wrong. They
      return a truncated host path and a container path that points nowhere,
      so a docker run mounts the whole cache root, or worse the wrong tree,
      instead of the single cache entry.

  cache_utils.fix_cache_paths  -- silently inert. Its `path_parts[idx+1] ==
      "cache"` guard notices the mismatch and gives up, so stale cache paths
      are simply never rewritten.

These are marked expectedFailure: they describe the behaviour C6 should
produce. When C6 lands they turn into unexpected successes and must be
un-marked.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "automation"))

from script.docker_utils import get_container_path, get_host_path  # noqa: E402


ENTRY = "abc123"


def _cache_file(root):
    return os.sep.join([root, "local", "cache", ENTRY, "data.txt"])


def _cache_entry(root):
    return os.sep.join([root, "local", "cache", ENTRY])


class HostPathTest(unittest.TestCase):

    def test_the_ordinary_root_still_works(self):
        """The regression guard for any fix: this is the common case and it
        is currently correct."""
        root = os.sep.join(["", "home", "u", "MLC", "repos"])
        self.assertEqual(get_host_path(_cache_file(root)), _cache_entry(root))

    @unittest.expectedFailure
    def test_a_root_containing_local_resolves_to_the_cache_entry(self):
        """`/usr/local/share/mlc` -> the match lands on `/usr/local`, and the
        host path collapses to the cache root itself. A docker run would mount
        every cache entry rather than the one asked for."""
        root = os.sep.join(["", "usr", "local", "share", "mlc"])
        self.assertEqual(get_host_path(_cache_file(root)), _cache_entry(root))

    @unittest.expectedFailure
    def test_a_root_whose_local_is_deeper_also_resolves(self):
        root = os.sep.join(["", "data", "local", "mlc"])
        self.assertEqual(get_host_path(_cache_file(root)), _cache_entry(root))


class ContainerPathTest(unittest.TestCase):

    def test_the_ordinary_root_still_works(self):
        root = os.sep.join(["", "home", "u", "MLC", "repos"])
        mnt, _ = get_container_path(_cache_file(root))
        self.assertEqual(mnt, f"/home/mlcuser/MLC/repos/local/cache/{ENTRY}")

    @unittest.expectedFailure
    def test_a_root_containing_local_maps_to_a_real_container_path(self):
        """Currently yields /home/mlcuser/MLC/repos/local/share/mlc -- a path
        assembled from the wrong three components, pointing at nothing."""
        root = os.sep.join(["", "usr", "local", "share", "mlc"])
        mnt, _ = get_container_path(_cache_file(root))
        self.assertEqual(mnt, f"/home/mlcuser/MLC/repos/local/cache/{ENTRY}")


if __name__ == "__main__":
    unittest.main()
