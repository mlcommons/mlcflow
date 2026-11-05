"""
Unit tests for convert_env_to_script list handling.

A list-valued env key used to be rendered with str(), which dropped a Python
repr (``['a', 'b']``) into the generated shell assignment.  It is now joined
with the platform separator.  These tests pin that behaviour for both
platforms and guard the '+KEY' append path that shares the same branch.
"""

import os
import subprocess
import sys
import unittest

# Ensure the automation directory is on sys.path so script.module can be
# imported without a full mlcflow install.
_automation_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'automation')
)
if _automation_dir not in sys.path:
    sys.path.insert(0, _automation_dir)


# os_info fixtures mirroring automation/utils.py, declared explicitly so the
# Windows expectations can be checked from any host.
UNIX_OS_INFO = {
    'platform': 'linux',
    'set_env': 'export ${key}="${value}"',
    'env_separator': ':',
    'env_quote': '"',
    'env_var': '${env_var}',
}

WINDOWS_OS_INFO = {
    'platform': 'windows',
    'set_env': 'set ${key}=${value}',
    'env_separator': ';',
    'env_quote': "'",
    'env_var': '%env_var%',
}


class ConvertEnvToScriptListTest(unittest.TestCase):
    def _convert(self, env, os_info):
        from script.module import convert_env_to_script
        return convert_env_to_script(env, os_info)

    def test_unix_list_is_joined_not_python_repr(self):
        """A plain key with a list value must be joined with ':', and must not
        leak Python repr syntax (brackets / quoted items) into the script."""
        script = self._convert({'MY_LIST': ['a', 'b', 'c']}, UNIX_OS_INFO)

        self.assertEqual(script, ['export MY_LIST="a:b:c"'])
        line = script[0]
        for repr_artifact in ('[', ']', "'"):
            self.assertNotIn(
                repr_artifact, line,
                f"Python repr artifact {repr_artifact!r} leaked into: {line}")

    def test_windows_list_uses_windows_separator(self):
        script = self._convert({'MY_LIST': ['a', 'b', 'c']}, WINDOWS_OS_INFO)

        self.assertEqual(script, ['set MY_LIST=a;b;c'])

    def test_non_list_values_are_unchanged(self):
        """The list branch must not capture scalars."""
        script = self._convert({'MY_STR': 'plain', 'MY_INT': 7}, UNIX_OS_INFO)

        self.assertEqual(
            script, ['export MY_INT="7"', 'export MY_STR="plain"'])

    def test_append_key_still_appends_existing_value(self):
        """'+KEY' keeps its append semantics -- it shares the if/elif chain
        with the list branch, so it is worth pinning here."""
        script = self._convert({'+PATH': ['/x', '/y']}, UNIX_OS_INFO)

        self.assertEqual(script, ['export PATH="/x:/y:${PATH}"'])

    def test_append_key_with_custom_separator(self):
        """A non-alphanumeric first character after '+' selects the separator."""
        script = self._convert({'+ CFLAGS': ['-O1', '-O2']}, UNIX_OS_INFO)

        self.assertEqual(script, ['export CFLAGS="-O1 -O2 ${CFLAGS}"'])

    @unittest.skipIf(sys.platform == 'win32', 'bash not available on Windows')
    def test_generated_unix_script_is_valid_bash_and_round_trips(self):
        """The generated assignment must parse under bash and the variable must
        hold the joined value -- this is the failure the change was made for."""
        script = self._convert(
            {'MY_LIST': ['one', 'two', 'three']}, UNIX_OS_INFO)
        body = '\n'.join(script)

        syntax_check = subprocess.run(
            ['bash', '-n', '-c', body], capture_output=True, text=True)
        self.assertEqual(
            syntax_check.returncode, 0,
            f"Generated script is not valid bash:\n{body}\n{syntax_check.stderr}")

        result = subprocess.run(
            ['bash', '-c', f'{body}\nprintf %s "$MY_LIST"'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'one:two:three')


class ConvertEnvToScriptQuotingTest(unittest.TestCase):
    """A regenerated container command (single-quoted args) must survive the
    Windows `set` serialization and still parse as POSIX arguments."""

    def _container_cmd(self):
        from script.docker_utils import regenerate_script_cmd
        r = regenerate_script_cmd({
            'script_uid': 'x', 'script_alias': 'x', 'tags': [],
            'run_cmd': {'tags': 'detect,os', 'note': 'a b', 'empty': '',
                        'quote': "it's"}})
        return r['run_cmd_string']

    def test_windows_set_keeps_quoted_args(self):
        import shlex
        from script.module import convert_env_to_script
        cmd = self._container_cmd()
        [line] = convert_env_to_script({'MLC_RUN_CMD': cmd}, WINDOWS_OS_INFO)
        prefix = 'set MLC_RUN_CMD='
        self.assertTrue(line.startswith(prefix))
        # cmd.exe `set` stores the rest of the line verbatim.
        value = line[len(prefix):]
        self.assertEqual(value, cmd)
        args = shlex.split(value)
        self.assertIn('--note=a b', args)
        self.assertIn('--empty=', args)
        self.assertIn("--quote=it's", args)

    def test_windows_set_does_not_backslash_single_quotes(self):
        from script.module import convert_env_to_script
        [line] = convert_env_to_script({'K': "it's"}, WINDOWS_OS_INFO)
        self.assertEqual(line, "set K=it's")


if __name__ == '__main__':
    unittest.main()
