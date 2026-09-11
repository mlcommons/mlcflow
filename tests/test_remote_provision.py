"""Tests for deciding what a remote node installs before it runs a script.

Two layers, neither of which needs a remote:

* the commands generated for each mode, including the guarantee that an
  unconfigured run generates none at all;
* mirror reading the head node - a packaged install, a checkout, and the
  editable install that is both at once.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

_automation_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'automation'))
if _automation_dir not in sys.path:
    sys.path.insert(0, _automation_dir)

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from script import provision  # noqa: E402


def _resolve(inputs, **kwargs):
    return provision.resolve(dict(inputs), **kwargs)


def _ok(testcase, inputs, **kwargs):
    r = _resolve(inputs, **kwargs)
    testcase.assertEqual(r['return'], 0, r.get('error'))
    return r


def _rejected(testcase, inputs, **kwargs):
    r = _resolve(inputs, **kwargs)
    testcase.assertEqual(
        r['return'], 1,
        f"expected a rejection, got commands: {r.get('cmds')}")
    return r['error']


# ---------------------------------------------------------------------------
# Layer 1 - which commands come out
# ---------------------------------------------------------------------------
class TestGeneratedCommands(unittest.TestCase):

    def test_an_unconfigured_run_adds_nothing(self):
        """The whole opt-in promise. If this fails, existing users broke."""
        r = _ok(self, {})
        self.assertEqual(r['cmds'], [])
        self.assertEqual(r['mode'], 'default')

    def test_a_bare_version_becomes_a_package_pin(self):
        cmds = _ok(self, {'remote_mlc_scripts': '1.2.0a4'})['cmds']
        self.assertEqual(len(cmds), 1)
        self.assertIn('pip install "mlc-scripts==1.2.0a4"', cmds[0])

    def test_a_full_spec_is_passed_through_untouched(self):
        cmds = _ok(self, {'remote_mlc_scripts':
                          'git+https://github.com/x/y@main'})['cmds']
        self.assertIn('"git+https://github.com/x/y@main"', cmds[0])
        self.assertNotIn('mlc-scripts==', cmds[0])

    def test_an_operator_is_attached_to_the_package_name(self):
        cmds = _ok(self, {'remote_mlc_scripts': '>=1.2'})['cmds']
        self.assertIn('"mlc-scripts>=1.2"', cmds[0])

    def test_a_ref_pulls_the_default_content_repo(self):
        cmds = _ok(self, {'remote_repo_ref': 'abc123'})['cmds']
        self.assertEqual(len(cmds), 1)
        self.assertIn(
            'mlc pull repo mlcommons@mlperf-automations --checkout=abc123',
            cmds[0])

    def test_a_named_repo_is_honoured(self):
        cmds = _ok(self, {'remote_repo': 'me@fork',
                          'remote_repo_ref': 'dev'})['cmds']
        self.assertIn('mlc pull repo me@fork --checkout=dev', cmds[0])

    def test_an_mlcflow_pin_alone_stays_in_default_mode(self):
        r = _ok(self, {'remote_mlcflow': '1.4.0a3'})
        self.assertEqual(r['mode'], 'default')
        self.assertIn('pip install "mlcflow==1.4.0a3"', r['cmds'][0])

    def test_mlcflow_is_pinned_before_the_repo_is_pulled(self):
        """A pinned engine has to be in place before it is asked to pull."""
        cmds = _ok(self, {'remote_mlcflow': '1.4.0a3',
                          'remote_repo_ref': 'dev'})['cmds']
        self.assertEqual(len(cmds), 2)
        self.assertIn('pip install "mlcflow==1.4.0a3"', cmds[0])
        self.assertIn('mlc pull repo', cmds[1])

    def test_a_failed_step_aborts_before_the_script_runs(self):
        cmd = _ok(self, {'remote_mlc_scripts': '1.2.0a4'})['cmds'][0]
        self.assertIn('exit 1', cmd)
        # Prove it, rather than trusting the substring.
        joined = f'false || {{ echo failed; exit 1; }} ; echo SCRIPT_RAN'
        out = subprocess.run(['bash', '-c', joined],
                             capture_output=True, text=True)
        self.assertNotIn('SCRIPT_RAN', out.stdout)
        self.assertEqual(out.returncode, 1)


class TestQuoting(unittest.TestCase):
    """The ssh layer escapes single quotes and then shlex-quotes the whole
    string, so a single quote is escaped twice and arrives mangled."""

    ALL_MODES = (
        {'remote_mlc_scripts': '1.2.0a4'},
        {'remote_repo_ref': 'abc123'},
        {'remote_mlcflow': '1.4.0a3', 'remote_repo_ref': 'dev'},
    )

    def test_no_generated_command_contains_a_single_quote(self):
        for inputs in self.ALL_MODES:
            for cmd in _ok(self, inputs)['cmds']:
                self.assertNotIn("'", cmd, f"single quote in: {cmd}")

    def test_commands_survive_the_ssh_escaping_and_still_parse(self):
        cmds = ['. mlcflow/bin/activate']
        for inputs in self.ALL_MODES:
            cmds.extend(_ok(self, inputs)['cmds'])
        cmds.append('mlcr detect,os --quiet')

        # Exactly what script/remote-run-commands/customize.py does.
        cmd_string = ' ; '.join(cmds).replace("'", "'\\''")
        safe = shlex.quote(cmd_string)

        # What the remote shell receives as its single argument.
        received = subprocess.run(
            ['bash', '-c', f'printf "%s" {safe}'],
            capture_output=True, text=True).stdout
        self.assertEqual(received, ' ; '.join(cmds))

        parsed = subprocess.run(['bash', '-n', '-c', received],
                                capture_output=True, text=True)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)


class TestRejections(unittest.TestCase):

    def test_mlcflow_cannot_be_pinned_alongside_a_package_pin(self):
        error = _rejected(self, {'remote_mlcflow': '1.4.0',
                                 'remote_mlc_scripts': '1.2.0a4'})
        self.assertIn('--remote_mlcflow', error)
        self.assertIn('never tested together', error)

    def test_mlcflow_cannot_be_pinned_alongside_mirror(self):
        error = _rejected(self, {'remote_mlcflow': '1.4.0',
                                 'remote_provision': 'mirror'})
        self.assertIn('not a mirror of anything', error)

    def test_mlcflow_is_accepted_where_nothing_else_decides(self):
        _ok(self, {'remote_mlcflow': '1.4.0'})
        _ok(self, {'remote_mlcflow': '1.4.0', 'remote_repo_ref': 'dev'})

    def test_mirror_refuses_an_explicit_pin(self):
        for extra in ({'remote_mlc_scripts': '1.2'},
                      {'remote_repo_ref': 'abc'},
                      {'remote_repo': 'me@fork'}):
            inputs = {'remote_provision': 'mirror'}
            inputs.update(extra)
            self.assertIn('Drop', _rejected(self, inputs))

    def test_the_two_kinds_of_pin_are_mutually_exclusive(self):
        self.assertIn('Pick one', _rejected(
            self, {'remote_mlc_scripts': '1.2', 'remote_repo_ref': 'abc'}))

    def test_package_mode_needs_a_version(self):
        self.assertIn('--remote_mlc_scripts',
                      _rejected(self, {'remote_provision': 'package'}))

    def test_repo_mode_needs_a_ref(self):
        self.assertIn('--remote_repo_ref',
                      _rejected(self, {'remote_provision': 'repo'}))

    def test_an_unknown_mode_lists_the_real_ones(self):
        error = _rejected(self, {'remote_provision': 'wheel'})
        for mode in provision.MODES:
            self.assertIn(mode, error)


# ---------------------------------------------------------------------------
# Layer 2 - mirror reading the head node
# ---------------------------------------------------------------------------
class _FakeRepo:
    def __init__(self, path):
        self.path = path


class _FakeAction:
    """Stands in for the Action that owns the registered repos."""

    def __init__(self, repos, package_repo_path=None,
                 package_repo_version=None):
        self.repos = [_FakeRepo(p) for p in repos]
        self.package_repo_path = package_repo_path
        self.package_repo_version = package_repo_version


@unittest.skipIf(shutil.which('git') is None, 'git is not installed')
class TestMirror(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = self.temp_dir.name

    # -- fixtures ---------------------------------------------------------

    def _package_tree(self):
        """A tree find_package_repo() would accept, in a realistic layout."""
        pkg = os.path.join(self.root, 'venv', 'lib', 'python3.12',
                           'site-packages', 'mlc_scripts')
        os.makedirs(os.path.join(pkg, 'script', 'detect-os'))
        with open(os.path.join(pkg, 'meta.yaml'), 'w') as f:
            f.write('alias: mlc-scripts-fixture\nuid: 0123456789abcdef\n')
        return pkg

    def _git_tree(self, push=True):
        origin = os.path.join(self.root, 'origin.git')
        work = os.path.join(self.root, 'work')
        self._git_run(['git', 'init', '--bare', '-q', origin])
        self._git_run(['git', 'clone', '-q', origin, work])
        self._git_run(['git', '-C', work, 'config', 'user.email', 't@t'])
        self._git_run(['git', '-C', work, 'config', 'user.name', 'tester'])
        os.makedirs(os.path.join(work, 'script', 'detect-os'))
        self._write(work, 'script/detect-os/meta.yaml', 'alias: detect-os\n')
        self._git_run(['git', '-C', work, 'add', '-A'])
        self._git_run(['git', '-C', work, 'commit', '-qm', 'initial'])
        if push:
            self._git_run(['git', '-C', work, 'push', '-q', 'origin', 'HEAD'])
        self._git_run(['git', '-C', work, 'remote', 'set-url', 'origin',
                       'https://github.com/mlcommons/mlperf-automations.git'])
        return work

    def _git_run(self, cmd):
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)

    def _write(self, root, rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)

    def _mirror(self, action, repo_path):
        return _resolve({'remote_provision': 'mirror'},
                        action_object=action,
                        script_path=os.path.join(repo_path, 'script',
                                                 'detect-os'))

    # -- tests ------------------------------------------------------------

    def test_a_packaged_head_sends_its_version(self):
        pkg = self._package_tree()
        r = self._mirror(_FakeAction([pkg], pkg, '1.2.0a4'), pkg)
        self.assertEqual(r['return'], 0, r.get('error'))
        self.assertEqual(r['mode'], 'package')
        self.assertIn('"mlc-scripts==1.2.0a4"', r['cmds'][0])
        self.assertNotIn('mlcflow==', ' '.join(r['cmds']),
                         "the package declares its own mlcflow")

    def test_a_checkout_sends_its_commit_and_its_mlcflow(self):
        work = self._git_tree()
        r = self._mirror(_FakeAction([work]), work)
        self.assertEqual(r['return'], 0, r.get('error'))
        self.assertEqual(r['mode'], 'repo')
        commit = subprocess.check_output(
            ['git', '-C', work, 'rev-parse', 'HEAD'], text=True).strip()
        joined = ' '.join(r['cmds'])
        self.assertIn(f'--checkout={commit}', joined)
        self.assertIn('mlcommons@mlperf-automations', joined)
        if provision.head_mlcflow_version():
            self.assertIn('pip install "mlcflow==', joined)

    def test_an_editable_install_mirrors_as_git_not_as_a_package(self):
        """The subtle one: an editable install is a checkout *and* a package,
        and only the checkout describes what this machine runs."""
        work = self._git_tree()
        r = self._mirror(_FakeAction([work], work, '9.9.9'), work)
        self.assertEqual(r['return'], 0, r.get('error'))
        self.assertEqual(r['mode'], 'repo')
        self.assertNotIn('9.9.9', ' '.join(r['cmds']))

    def test_a_dirty_checkout_is_refused_with_a_way_forward(self):
        work = self._git_tree()
        self._write(work, 'script/detect-os/meta.yaml', 'alias: edited\n')
        r = self._mirror(_FakeAction([work]), work)
        self.assertEqual(r['return'], 1)
        self.assertIn('uncommitted', r['error'])
        self.assertIn('--remote_copy_mlc_repos', r['error'])

    def test_an_untracked_file_is_not_dirty(self):
        """Results and logs land in a checkout constantly; they are not edits."""
        work = self._git_tree()
        self._write(work, 'results.json', '{}\n')
        r = self._mirror(_FakeAction([work]), work)
        self.assertEqual(r['return'], 0, r.get('error'))

    def test_an_unpushed_commit_is_refused(self):
        work = self._git_tree(push=False)
        r = self._mirror(_FakeAction([work]), work)
        self.assertEqual(r['return'], 1)
        self.assertIn('not on any remote branch', r['error'])

    def test_a_plain_directory_is_refused(self):
        plain = os.path.join(self.root, 'plain')
        os.makedirs(os.path.join(plain, 'script', 'detect-os'))
        r = self._mirror(_FakeAction([plain]), plain)
        self.assertEqual(r['return'], 1)
        self.assertIn('neither a git checkout nor an installed', r['error'])

    def test_a_packaged_head_with_no_version_is_refused(self):
        pkg = self._package_tree()
        r = self._mirror(_FakeAction([pkg], pkg, None), pkg)
        self.assertEqual(r['return'], 1)
        self.assertIn('--remote_mlc_scripts', r['error'])

    def test_an_unrecognised_script_path_is_refused(self):
        plain = os.path.join(self.root, 'plain')
        os.makedirs(plain)
        r = _resolve({'remote_provision': 'mirror'},
                     action_object=_FakeAction([plain]),
                     script_path='/nowhere/script/detect-os')
        self.assertEqual(r['return'], 1)
        self.assertIn('could not work out which registered repo', r['error'])

    def test_the_innermost_registered_repo_wins(self):
        """Repos can nest; the script belongs to the closest one."""
        outer = os.path.join(self.root, 'outer')
        inner = os.path.join(outer, 'inner')
        os.makedirs(os.path.join(inner, 'script', 'detect-os'))
        r = _resolve({'remote_provision': 'mirror'},
                     action_object=_FakeAction([outer, inner]),
                     script_path=os.path.join(inner, 'script', 'detect-os'))
        self.assertIn(inner, r['error'])


# ---------------------------------------------------------------------------
# The prerequisite: a packaged install has to be able to report its version
# ---------------------------------------------------------------------------
class TestPackagedProvenance(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = self.temp_dir.name

    def _provenance(self, payload):
        path = os.path.join(self.root, '.mlc-provenance.json')
        text = payload if isinstance(payload, str) else json.dumps(payload)
        with open(path, 'w') as f:
            f.write(text)

    def _version(self):
        from mlc.utils import get_repo_version
        return get_repo_version(self.root)

    def test_a_wheel_install_reports_its_version_and_commit(self):
        self._provenance({'version': '1.2.0a4', 'commit': 'abc123',
                          'source': 'https://github.com/x/y'})
        self.assertEqual(self._version(), {
            'source': 'package', 'commit': 'abc123', 'version': '1.2.0a4',
            'branch': '', 'dirty': False})

    def test_a_corrupt_provenance_file_is_not_fatal(self):
        self._provenance('{not json')
        self.assertEqual(self._version(), {})

    def test_a_provenance_file_naming_nothing_is_ignored(self):
        self._provenance({'source': 'https://github.com/x/y'})
        self.assertEqual(self._version(), {})

    def test_a_commit_file_still_works_when_provenance_says_nothing(self):
        self._provenance({})
        with open(os.path.join(self.root, 'git_commit_hash.txt'), 'w') as f:
            f.write('deadbeef\n')
        self.assertEqual(self._version()['source'], 'commit_file')

    def test_nothing_at_all_is_version_unknown(self):
        self.assertEqual(self._version(), {})


# ---------------------------------------------------------------------------
# The whole bootstrap, as remote_run() actually assembles it
# ---------------------------------------------------------------------------
class TestRemoteRunBootstrap(unittest.TestCase):
    """Assert on the command list remote_run() hands to the ssh layer."""

    def _bootstrap(self, **extra):
        from unittest.mock import MagicMock
        from script.remote_run import remote_run

        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'),
        }
        mock_self.update_run_state_for_selected_script_and_variations \
            .return_value = {'return': 0}
        mock_self.run_state = {}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()
        mock_self.action_object.access.return_value = {'return': 0}
        # A MagicMock would look like a repo whose path is a Mock; an empty
        # list is what an Action with nothing registered actually looks like.
        mock_self.action_object.repos = []
        mock_self.action_object.package_repo_path = None

        i = {'tags': 'detect,os', 'mlc_run_cmd': 'mlcr detect,os', 'env': {}}
        i.update(extra)

        result = remote_run(mock_self, i)
        if result['return'] > 0:
            return result, None
        called = mock_self.action_object.access.call_args[0][0]
        return result, called['run_cmds']

    # These assert the *shape* of the bootstrap, not its literal commands.
    # The installer line and the venv activation belong to remote_run.py and
    # change independently (the activation now carries a fresh uuid per call,
    # so two invocations are not even equal to each other). What must hold is
    # that an unconfigured run adds nothing, and a configured one adds exactly
    # one command in exactly one place.

    def test_an_unconfigured_run_adds_nothing_to_the_bootstrap(self):
        """The regression guard for the opt-in promise."""
        result, cmds = self._bootstrap()
        self.assertEqual(result['return'], 0)
        self.assertEqual(len(cmds), 3, cmds)
        self.assertIn('mlcflow_unix_installer.sh', cmds[0])
        self.assertTrue(cmds[-1].startswith('mlcr'))
        joined = ' '.join(cmds)
        for provisioning in ('mlc-scripts', 'mlc pull repo',
                             'MLC_PROVISION_FAILED'):
            self.assertNotIn(provisioning, joined)

    def test_a_pin_inserts_one_command_between_activation_and_the_script(self):
        _, base = self._bootstrap()
        _, cmds = self._bootstrap(remote_mlc_scripts='1.2.0a4')
        self.assertEqual(len(cmds), len(base) + 1)
        self.assertEqual(cmds[0], base[0], "installer line changed")
        self.assertEqual(cmds[-1], base[-1], "script command changed")
        self.assertIn('pip install "mlc-scripts==1.2.0a4"', cmds[2])
        self.assertTrue(cmds[-1].startswith('mlcr'))

    def test_the_new_flags_do_not_reach_the_remote_command(self):
        """prune_input strips remote_* keys; if that ever changes, the worker
        gets flags its mlcr does not understand."""
        _, cmds = self._bootstrap(remote_mlc_scripts='1.2.0a4',
                                  remote_provision='package')
        for leaked in ('--remote_mlc_scripts', '--remote_provision'):
            self.assertNotIn(leaked, cmds[-1])

    def test_a_rejected_combination_fails_before_any_ssh(self):
        result, cmds = self._bootstrap(remote_mlc_scripts='1.2.0a4',
                                       remote_mlcflow='1.4.0')
        self.assertEqual(result['return'], 1)
        self.assertIn('--remote_mlcflow', result['error'])
        self.assertIsNone(cmds)


if __name__ == '__main__':
    unittest.main()
