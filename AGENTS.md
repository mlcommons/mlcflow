# AGENTS.md — AI coding agent guide for mlcflow

> **⚠️ ARCHITECTURE MIGRATION (Option B, mlcflow 2.0.0) — READ FIRST.**
> The execution engine now lives **inside this repo** at `mlc/engine/`
> (`module.py`, `cache_utils.py`, `docker.py`, `apptainer.py`, `remote_run.py`,
> `experiment.py`, `meta_schema.py`, `script_utils.py`, `docker_utils.py`,
> `lint.py`, `doc.py`, `help.py`, `validate.py`, `utils.py`, `meta.json`) and is
> imported directly: `from mlc.engine import ScriptAutomation`. There is **no
> more `dynamic_import_module` and no auto git-clone** of mlperf-automations.
> Script *content* comes from the **`mlc-scripts` pip package** (discovered via
> `mlc_scripts.SCRIPTS_DIR`) and/or registered local repos. On a UID clash the
> **package wins by default** (published scripts run); set
> **`MLC_PREFER_DEV_SCRIPTS=1`** to let registered/editable dev repos override
> the package — see `index.py` priority policy. `Automation`
> base class moved to `mlc/automation.py` (breaks a circular import). Sections
> below that describe dynamic loading / auto-pull are historical; trust this
> banner where they conflict. See `migration-modification-plan.md`.

mlcflow is the CLI driver for the MLC automation framework. It provides the
`mlc`, `mlcr`, `mlcd`, and related commands. As of the Option B migration it also
**contains the script execution engine** (`ScriptAutomation`) under `mlc/engine/`.
This file covers everything an AI agent needs to contribute correctly to this repo.

---

## Mental model

```
User runs: mlcr detect,os --verbose
                │
                ▼
mlc/main.py:mlcr()
  → mlc_expand_short("run")   # inserts "run script" into sys.argv
  → main()
      → build_pre_parser()    # quick pre-parse for action/target
      → build_parser()        # full argparse dispatch
      → get_action("script", default_parent)  → ScriptAction(parent)
      → ScriptAction.run(run_args)
          → call_script_module_function("run", run_args)
              → find_target_folder("script")
                  # walks registered repos looking for automation/script/
              → dynamic_import_module("automation/script/module.py")
                  # loads ScriptAutomation class at runtime
              → ScriptAutomation(self, module_path).run(run_args)
                  # all actual script logic lives in mlperf-automations
```

**Two repos, two roles:**
- `mlcflow` (this repo) — the CLI driver: arg parsing, repo/index management,
  dynamic dispatch, error reporting. Has no script content.
- `mlperf-automations` — the content: 377+ script directories +
  `automation/script/module.py` (the `ScriptAutomation` engine).

mlcflow does **not** contain or execute benchmark logic. It finds the engine,
loads it, and hands off `run_args`.

---

## Repo layout

```
mlcflow/
  mlc/
    main.py            # CLI entry point; all short commands (mlcr, mlcd…) defined here
    action.py          # Base Action class: repo loading, index access, CRUD
    action_factory.py  # Maps target strings → Action subclasses
    script_action.py   # ScriptAction + ScriptExecutionError
    repo_action.py     # RepoAction: pull/add/rm/find repos
    cache_action.py    # CacheAction: find/rm/show/prune/list/mark-tmp
    experiment_action.py
    index.py           # Tag-based index; file-locked JSON files
    meta_schema.py     # Schema + validate_meta() for script meta.yaml
    error_codes.py     # ErrorCode/WarningCode enums + get_error_guidance()
    logger.py          # Logging setup
    utils.py           # UID gen, YAML/JSON I/O, arg parsing helpers
    repo.py            # Repo data class
    item.py            # Item data class (path + meta)
    cfg_action.py      # Config loading (load cfg)
  tests/
    test_action_invalid_meta_entries.py
    test_cache_mark_tmp.py
  .github/
    workflows/         # CI: core actions test, script features, MLPerf inference runs
    scripts/
  pyproject.toml       # Package metadata + entry-point registration
  README.md
```

**Filesystem state managed by mlcflow at runtime:**
```
~/MLC/repos/                      # controlled by MLC_REPOS env var
  repos.json                      # ordered list of registered repo absolute paths
  local/
    meta.yaml                     # auto-created on first run
    cache/                        # all script caches live here
  index_script.json               # tag index for scripts
  index_cache.json                # tag index for caches
  index_experiment.json
  modified_times.json             # mtime map used for incremental index
  mlcommons@mlperf-automations/   # pulled repos
    automation/script/module.py   # ScriptAutomation engine (loaded dynamically)
    script/<alias>/meta.yaml      # script content (not in this repo)
```

---

## CLI dispatch — full reference

### Syntax
```
mlc <action> <target> [options]
```

| Target | Actions |
|--------|---------|
| `script` | `run`, `find`/`search`, `rm`, `mv`, `cp`, `add`, `test`, `docker`/`docker-run`, `show`, `experiment`, `doc`, `lint` |
| `cache` | `find`/`search`, `rm`, `show`, `list`, `prune`, `mark-tmp` |
| `repo` | `pull`, `add`, `find`/`search`, `rm`, `list`/`show` |

### Short commands (registered in `pyproject.toml`)
| Short command | Equivalent |
|---|---|
| `mlcr <tags>` | `mlc run script <tags>` |
| `mlcd <tags>` | `mlc docker script <tags>` |
| `mlca <tags>` | `mlc apptainer script <tags>` |
| `mlcrr <tags>` | `mlc remote-run script <tags>` |
| `mlcrd <tags>` | `mlc remote-docker script <tags>` |
| `mlcre <tags>` | `mlc remote-experiment script <tags>` |
| `mlce <tags>` | `mlc experiment script <tags>` |
| `mlct <tags>` | `mlc test script <tags>` |
| `mlcp <repo>` | `mlc pull repo <repo>` |

All short commands call `mlc_expand_short(action)` in `main.py`, which inserts
the missing positional args into `sys.argv` and calls `main()`.

### Arg parsing rules (from `main.py` and `utils.py`)
- Hyphens in option names are converted to underscores before parsing
  (`convert_hyphen_to_underscore_in_args()`). `--my-flag` → `my_flag`.
- Non-ASCII characters in unquoted args cause an immediate error with a
  descriptive message (catches copy-paste from PDFs/docs).
- `--flag` (no value) → `{"flag": True}`.
- `--key=val` → `{"key": "val"}`.
- `--key.sub=val` → `{"key": {"sub": "val"}}` (nested dict; used by `--adr`).
- `-v` / `--verbose` → `logging.DEBUG`; `-s` / `--silent` → `logging.WARNING`.
- `-p` / `--path_only` on find/search: prints only the filesystem path (no
  logger prefix), intended for shell script consumption.
- `mlc_output=on|true|yes|1` causes `tmp-state.json` and `tmp-run-env.out` to
  be written after a successful script run.

---

## How the engine loads automation modules

This is the most important thing to understand when modifying `script_action.py`.

`call_script_module_function(function_name, run_args)` in `script_action.py`:

1. **Finds the automation folder**: calls `find_target_folder("script")` on the
   `Action` base. This walks `self.repos` looking for a repo that has an
   `automation/script/` directory inside it.

2. **Auto-pull if missing**: if no `automation/script/` is found, it pulls
   `mlcommons@mlperf-automations --branch=dev` automatically and retries once.

3. **Loads module dynamically**: calls `dynamic_import_module(module_path)`
   where `module_path = "<repo>/automation/script/module.py"`. This uses
   `importlib.util.spec_from_file_location()`. The parent directory
   (`automation/`) is prepended to `sys.path` so relative imports inside
   `module.py` resolve.

4. **Instantiates `ScriptAutomation`**: checks if `ScriptAutomation.__init__`
   accepts a `run_args` parameter (via `inspect.signature`) and calls the
   appropriate constructor form.

5. **Dispatches**: calls `automation_instance.run(run_args)` (or `docker`,
   `test`, `experiment`, `lint`, `doc`, `help`).

6. **Error wrapping**: any exception (except `ScriptExecutionError`) is caught
   and re-raised as `ScriptExecutionError` with `script_name`, `repo_alias`,
   `module_path`, and `run_args` attached. `main.py:_report_error()` formats
   this for the user with a rerun command and issue URL.

**What this means for contributors:**
- The `ScriptAutomation` class is **not** in this repo. Changes to how it is
  called must be backward-compatible.
- The `run_args` dict is the primary contract between mlcflow and the engine.
  Keys added to `run_args` here become available to `ScriptAutomation`.
- If you add a new function name to dispatch (e.g., `remote_run`), add the
  `elif function_name == "remote_run":` branch in `call_script_module_function`.

---

## How to add a new CLI action

### Step 1 — Add the method to the appropriate Action class

Each method name must match the CLI command (hyphens → underscores). All methods
receive a `run_args` dict and must return `{'return': 0}` on success or
`{'return': N, 'error': 'message'}` on failure.

**For a new `script` action** that delegates to the automation engine
(`automation/script/module.py`):
```python
# in script_action.py
def my_action(self, run_args):
    return self.call_script_module_function("my_action", run_args)
```
Then add the `elif function_name == "my_action":` branch in
`call_script_module_function`.

**For a new `script` action** handled entirely in mlcflow (no engine dispatch):
```python
# in script_action.py
def my_action(self, run_args):
    self.action_type = "script"
    res = self.search(run_args)
    # ... do work ...
    return {'return': 0}
```

**For a new `cache` or `repo` action**: add to `CacheAction` or `RepoAction`
with the same signature.

### Step 2 — Register in `build_parser()` (main.py)

If it's a new command for an existing target group, add to the relevant list:
```python
# General commands (work with script, cache, or repo)
for action in ['run', 'pull', ..., 'my-action']:  # line 363-364

# Script-only commands
for action in ['docker', 'docker-run', ..., 'my-script-action']:  # line 393-394
```

### Step 3 — (Optional) Register a short command

In `main.py`, add a top-level function:
```python
def mlcx():
    mlc_expand_short("my-action")
```

Then register in `pyproject.toml`:
```toml
mlcx = "mlc.main:mlcx"
```

### Step 4 — Add a new target (rare)

If adding a completely new target type (not script/cache/repo):
1. Create a new `XxxAction(Action)` class in a new file.
2. Add to `actions` dict in `action_factory.py`.
3. Add to `choices` in `build_parser()` for both the pre-parser and the full
   parser.

---

## Key internal APIs

### `Action.access(i)` — Python API for programmatic use

Call any action without going through the CLI:
```python
from mlc.action import access

result = access({
    'action': 'run',
    'target': 'script',
    'tags': 'detect,os'
})
# result = {'return': 0, ...} or {'return': N, 'error': '...'}
```

The `Action` class also exposes `access()` as an instance method (used
internally by `RepoAction` and others to call cross-target operations).

### `Action.search(i)` — tag-based lookup

Used by all action classes. Returns `{'return': 0, 'list': [Item, ...]}`.

For `script` target: variation tags (prefixed `_`) are stripped before
matching. For `cache`/`experiment`: all tags are matched. Negative tags use
`-` prefix.

### `Index` class (`index.py`)

Maintains three index files plus `modified_times.json`:
- `Index.build_index()` — incremental; only re-processes `meta.yaml` files
  whose mtime changed. Set `force_rebuild=True` to clear and rebuild.
- `Index.add_repo(repo)` — called after registering a new repo; indexes it
  immediately.
- `Index.remove_repo_from_index(repo_path)` — called when a repo is
  unregistered.
- All file writes are protected by `filelock.FileLock` with a 60-second timeout
  (retries once).

`mlc reindex` calls `index.build_index(force_rebuild=True)`.

### `validate_meta(data, file_path)` (`meta_schema.py`)

Returns `(errors, warnings)`. Called automatically during `build_index()` when
a script's `meta.yaml` mtime changes. Errors halt indexing with an exception;
warnings are logged at DEBUG level.

**Required keys** (from `REQUIRED_KEYS`):
```python
{"alias", "uid", "automation_alias", "automation_uid"}
```

### `get_error_guidance(return_code, error_message)` (`error_codes.py`)

Pattern-matches error text for: disk space exhaustion, segfault, network
failure, permission denied (126), command not found (127), OOM (137), interrupt
(130). Returns a guidance dict with `error_message` and `suggestions`, or
`None` if no pattern matches.

### `utils.get_new_uid()` — UID generation

```python
from mlc.utils import get_new_uid
result = get_new_uid()
uid = result['uid']  # 16-hex string, e.g. "a3f9c0d1b2e45678"
```

UIDs are generated as `uuid.uuid4().hex[:16]`. `is_uid(name)` validates with
`^[0-9a-fA-F]{16}$`.

### Result dict convention

All methods in this codebase return a dict with at minimum:
- `{'return': 0}` — success
- `{'return': N, 'error': 'message'}` — failure (N > 0)

`main()` checks `res['return'] > 0` and exits with code 1. Never raise
exceptions for recoverable errors in action methods — use the return dict.

---

## Adding or modifying error codes

1. Add to `ErrorCode` or `WarningCode` enum in `error_codes.py`.
2. Add a pattern branch in `get_error_guidance()` if actionable suggestions
   should be shown to the user.
3. Error codes 2000–2007 are for fatal errors; warning codes 1000–1006 are for
   recoverable situations.

---

## Common pitfalls (derived from the code)

**1. Index is stale after manually editing `meta.yaml`**
The index rebuilds incrementally on mtime change. If `meta.yaml` is edited and
the mtime is not updated (e.g., restored from backup with original timestamp),
the index won't pick up the change. Fix: `mlc reindex`.

**2. `mlc pull repo` silently skips if local changes exist**
`RepoAction.pull_repo()` checks `git status --porcelain --untracked-files=no`.
If tracked changes are found, it logs a warning and returns without pulling.
Use `--force` to stash, pull, and re-apply.

**3. `automation_alias` and `automation_uid` are required in every `meta.yaml`**
`validate_meta()` checks `REQUIRED_KEYS = {"alias", "uid", "automation_alias",
"automation_uid"}`. A script missing either of these will cause an error during
`build_index()` and prevent any mlc command from running until fixed or the
bad script is removed/corrected.

**4. `--adr.compiler.tags=gcc` becomes a nested dict, not a flat key**
`convert_args_to_dictionary()` splits on `.` in key names. This is intentional:
`--adr.compiler.tags=gcc` → `{"adr": {"compiler": {"tags": "gcc"}}}`. Do not
use `.` in key names that should be flat strings.

**5. Non-ASCII in CLI args causes immediate exit**
`check_raw_arguments_for_non_ascii()` runs before any parsing and exits with
code 1. This is intentional to catch copy-paste artifacts. Quoted args are
excluded from the check.

**6. Auto-pull uses `--branch=dev`**
When `call_script_module_function()` cannot find `automation/script/`, it
auto-pulls `mlcommons@mlperf-automations --branch=dev`. If the local checkout
is on `main`, the auto-pull may switch branches. This is a fallback path and
should not normally be triggered if the repo is already registered.

**7. `ScriptAction.add()` always uses `cp` with `src_tags`**
`ScriptAction.add(i)` calls `self.cp(ii)` with `ii['src_tags'] =
i.get("template_tags", "template,generic")`. If multiple scripts match
`template_tags`, it interactively prompts. Passing an exact unique tag set
avoids the prompt.

---

## Files to read first by task type

| Task | Read these |
|---|---|
| Understand CLI dispatch | `mlc/main.py` (focus: `main()`, `build_parser()`, `mlc_expand_short()`) |
| Add a new action or command | `mlc/main.py` + relevant Action class (`script_action.py` / `repo_action.py` / `cache_action.py`) |
| Understand how automation engine is loaded | `mlc/script_action.py` (`call_script_module_function`, `dynamic_import_module`) |
| Debug a failed script run | `mlc/script_action.py` (`ScriptExecutionError`), `mlc/error_codes.py` (`get_error_guidance`) |
| Fix index/search issues | `mlc/index.py` (`build_index`, `_index_single_repo`, `_save_indices`) |
| Add or fix meta.yaml validation | `mlc/meta_schema.py` (`REQUIRED_KEYS`, `TOP_LEVEL_SCHEMA`, `validate_meta`) |
| Understand repo registration | `mlc/repo_action.py` (`pull_repo`, `register_repo`) |
| Understand cache management | `mlc/cache_action.py` |
| Add a new error code or improve error messages | `mlc/error_codes.py` + `mlc/main.py:_report_error()` |
| Understand programmatic (Python) API | `mlc/action.py` (`access`, `search`) |
| Add tests | `tests/` — see `test_cache_mark_tmp.py` and `test_action_invalid_meta_entries.py` for patterns |
| CI workflows | `.github/workflows/` |

---

## Branch policy

- PRs target `main`.
- `dev` is kept in sync with `main` and is only used for urgent merges that
  need to bypass the normal approval process.
- Never push directly to `main`.
