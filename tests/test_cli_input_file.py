"""
Tests for --mlc_input_file: loading run options from a YAML/JSON file
and merging them into the CLI args dict.
"""
import argparse
import json
import os
import sys
import tempfile
import unittest

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


class LoadCliInputFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name, text):
        path = os.path.join(self.tmp.name, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    def test_yaml_merges_with_cli_override_and_deep_merge(self):
        from mlc import utils
        path = self._write(
            'run.yaml',
            "tags: run,spec,cpu\n"
            "tune: base\n"
            "env:\n"
            "  MLC_QUIET: 'yes'\n"
            "adr:\n"
            "  compiler:\n"
            "    tags: llvm\n",
        )
        args = {'mlc_input_file': path, 'tune': 'peak', 'env': {'X': '1'}}
        r = utils.load_cli_input_file(args)
        self.assertEqual(r['return'], 0)
        d = r['args_dict']
        self.assertEqual(d['tags'], 'run,spec,cpu')       # from file
        self.assertEqual(d['tune'], 'peak')               # CLI overrides file
        self.assertEqual(d['env']['MLC_QUIET'], 'yes')    # from file
        self.assertEqual(d['env']['X'], '1')              # CLI, deep-merged
        self.assertEqual(d['adr']['compiler']['tags'], 'llvm')
        self.assertNotIn('mlc_input_file', d)

    def test_json_file(self):
        from mlc import utils
        path = os.path.join(self.tmp.name, 'run.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'tags': 'run,spec', 'quiet': True}, f)
        r = utils.load_cli_input_file({'mlc_input_file': path})
        self.assertEqual(r['return'], 0)
        self.assertEqual(r['args_dict']['tags'], 'run,spec')
        self.assertIs(r['args_dict']['quiet'], True)

    def test_plain_input_file_key_passes_through(self):
        # A script's own --input_file must NOT be consumed by mlcflow.
        from mlc import utils
        r = utils.load_cli_input_file(
            {'input_file': 'script_data.txt', 'tags': 'x'})
        self.assertEqual(r['return'], 0)
        self.assertEqual(
            r['args_dict'], {'input_file': 'script_data.txt', 'tags': 'x'})

    def test_no_input_file_is_passthrough(self):
        from mlc import utils
        r = utils.load_cli_input_file({'tags': 'x'})
        self.assertEqual(r['return'], 0)
        self.assertEqual(r['args_dict'], {'tags': 'x'})

    def test_missing_file_errors(self):
        from mlc import utils
        r = utils.load_cli_input_file(
            {'mlc_input_file': os.path.join(self.tmp.name, 'nope.yaml')})
        self.assertEqual(r['return'], 1)
        self.assertIn('not found', r['error'])

    def test_non_mapping_top_level_errors(self):
        from mlc import utils
        path = self._write('bad.yaml', '- a\n- b\n')
        r = utils.load_cli_input_file({'mlc_input_file': path})
        self.assertEqual(r['return'], 1)
        self.assertIn('top-level', r['error'])

    def test_nested_input_file_key_is_ignored(self):
        from mlc import utils
        path = self._write('a.yaml', "tags: x\nmlc_input_file: b.yaml\n")
        r = utils.load_cli_input_file({'mlc_input_file': path})
        self.assertEqual(r['return'], 0)
        self.assertNotIn('mlc_input_file', r['args_dict'])

    def test_build_run_args_integration(self):
        from mlc.main import build_run_args
        path = self._write('run.yaml', "tags: run,spec\nquiet: true\n")
        args = argparse.Namespace(
            command='run', target='script', details=None,
            extra=[f'--mlc_input_file={path}'])
        run_args = build_run_args(args)
        self.assertEqual(run_args['tags'], 'run,spec')
        self.assertIs(run_args['quiet'], True)
        self.assertNotIn('mlc_input_file', run_args)

    def test_docker_positional_tags_override_file_tags(self):
        # `mlcd detect,os --mlc_input_file=f.yaml` where f.yaml also has tags:
        # the typed positional tags must win; other file options merge in.
        from mlc.main import build_run_args
        path = self._write('full.yaml',
                           'tags: run,spec\nquiet: true\ndocker_os: ubuntu\n')
        args = argparse.Namespace(
            command='docker', target='script', details='detect,os',
            extra=[f'--mlc_input_file={path}'])
        run_args = build_run_args(args)
        self.assertEqual(run_args['tags'], 'detect,os')
        self.assertEqual(run_args['docker_os'], 'ubuntu')
        self.assertIs(run_args['quiet'], True)

    def test_file_supplies_tags_when_none_positional(self):
        from mlc.main import build_run_args
        path = self._write('t.yaml', 'tags: run,spec\n')
        args = argparse.Namespace(
            command='docker', target='script', details=None,
            extra=[f'--mlc_input_file={path}'])
        self.assertEqual(build_run_args(args)['tags'], 'run,spec')


if __name__ == '__main__':
    unittest.main()
