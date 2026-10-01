# Typo Detection ("Did you mean…?")

MLCFlow detects mistyped commands and targets and suggests the closest valid
alternative before showing the standard error.

## How it works

When you type an invalid action or target, the CLI now prints a suggestion
immediately after the usage line:

```
$ mlc rune script

usage: mlc [-h] {run,pull,test,add,...} ...

Did you mean one of: 'prune', 'run'?

mlc: error: argument command: invalid choice: 'rune' (choose from 'run', 'pull', ...)
```

```
$ mlc run scrip

usage: mlc run {repo,repos,script,cache,experiment} [details] ...

Did you mean 'script'?

mlc run: error: argument target: invalid choice: 'scrip' (choose from repo, repos, script, cache, experiment)
```

When several alternatives are similarly close:

```
$ mlc find rep

Did you mean one of: 'repo', 'repos'?
```

If the input has no close match (e.g. a completely unrelated word), no hint is
shown — only the standard argparse error.

Target suggestions only come from the targets the chosen action accepts. For
example `mlc docker cach` shows no hint, because `docker` only accepts `script`
or `run`.

## Typos detected

Suggestions are shown for **both** levels of the command syntax:

| Typo location | Example input | Suggestion shown |
|---|---|---|
| Action | `mlc rune script` | `Did you mean one of: 'prune', 'run'?` |
| Action | `mlc fnd script` | `Did you mean 'find'?` |
| Action | `mlc serach cache` | `Did you mean 'search'?` |
| Action | `mlc mrak-tmp cache` | `Did you mean 'mark-tmp'?` |
| Target | `mlc run scrip` | `Did you mean 'script'?` |
| Target | `mlc find cach` | `Did you mean 'cache'?` |
| Target | `mlc pull rpo` | `Did you mean one of: 'repo', 'repos'?` |
| Target | `mlc load cfgg` | `Did you mean 'cfg'?` |
| Action (prefix) | `mlc dock run` | `Did you mean one of: 'docker', 'docker-run', 'doc'?` |
| Target (prefix) | `mlc find exp` | `Did you mean 'experiment'?` |

## Implementation

The feature is implemented in [`mlc/typo_mixin.py`](../mlc/typo_mixin.py) as a
Python mixin class — `TypoMixin` — that can be mixed into any
`argparse.ArgumentParser` subclass.

```python
class TypoMixin:
    def suggest(self, word, candidates) -> list[str]: ...
    def error(self, message) -> None: ...
```

`TypoMixin` overrides `ArgumentParser.error()` to:

1. Call `self.print_usage(sys.stderr)` (identical to the standard behaviour).
2. Parse the mistyped value and the valid-choices list from argparse's error
   text using a regex.
3. Collect candidates that start with the mistyped value (prefix rule, for
   inputs of 3+ characters), then add `difflib.get_close_matches()` results
   (Python stdlib, no extra dependencies) with a similarity cutoff of `0.6`.
   Prefix matches are listed first, so `exp` suggests `experiment` and `dock`
   suggests `docker` ahead of `doc`.
4. If one or more matches are found, write the hint line to stderr.
5. Call `self.exit(2, …)` with the original error message — identical to the
   standard behaviour.

In `main.py`, a concrete `TypoArgumentParser` class is assembled:

```python
class TypoArgumentParser(TypoMixin, argparse.ArgumentParser):
    pass
```

Both `build_pre_parser()` and `build_parser()` return `TypoArgumentParser`
instances.  Subparsers created via `add_subparsers()` automatically inherit the
class (argparse uses `type(self)` as the default `parser_class`), so target
typos inside a valid command are also caught.

## Tuning

Three class-level attributes control the matching behaviour; override them on
`TypoArgumentParser` if needed:

| Attribute | Default | Meaning |
|---|---|---|
| `_TYPO_CUTOFF` | `0.6` | Minimum similarity ratio (0–1). Raise to require a closer match. |
| `_TYPO_MAX_SUGGESTIONS` | `3` | Maximum number of alternatives displayed. |
| `_TYPO_MIN_PREFIX` | `3` | Minimum input length before prefix matches are suggested. |

## Testing

Tests live in [`tests/test_typo_mixin.py`](../tests/test_typo_mixin.py) and are
split into two suites:

- **`TypoMixinSuggestTests`** — unit tests for `TypoMixin.suggest()` covering
  single matches, multiple matches, edge cases (empty input, empty candidates,
  exact match, transposed characters).

- **`TypoMixinCliTests`** — subprocess integration tests that invoke
  `python -m mlc.main <typo> <target>` and assert that the correct hint
  appears in stderr with exit code 2.

Run locally with:

```bash
pip install -e .
python -m unittest tests/test_typo_mixin.py -v
```

Or via the full test suite:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
