# skill.md — Claude working guide for mlcflow

Compact task playbooks. Read AGENTS.md for full technical detail.

---

## Mental model

```
mlcr <tags>  →  mlc_expand_short("run")  →  main()
  →  get_action("script", parent)  →  ScriptAction.run(run_args)
    →  call_script_module_function("run", run_args)
      →  find_target_folder("script")        # bundled automation/script/ always preferred first,
                                              # falls back to scanning registered repos only if absent
      →  dynamic_import_module(module.py)    # loads ScriptAutomation
      →  ScriptAutomation(self, path).run(run_args)   # engine bundled in this repo
```

**This repo = CLI driver + script execution engine.** Engine logic lives in
`automation/script/module.py` here (originally developed in
`mlperf-automations`, now bundled here as the copy mlcflow actually loads).
`mlperf-automations` **keeps its own `automation/` copy** — it is not being
removed, so that pre-bundling mlcflow releases still have an engine to fall
back to. Script *content* (the 350+ `script/<alias>/` directories with
`meta.yaml`, `customize.py`, `run.sh`) still lives there and is pulled into
`~/MLC/repos/` as before.

**Coexistence is safe** (verified on real installs): bundled mlcflow loads the
bundled copy, pre-bundling mlcflow loads the repo copy, and in both cases
`module.py` + `utils.py` come from the *same* copy — never a hybrid.

**Version drift is permanent, and it bites via coupled changes.** The bundled
copy always wins, so any edit to `mlperf-automations/automation/` is invisible
here. Engine and content changes usually land together in one
mlperf-automations PR (see #1061: `MLC_SKIP_SUDO` + `script/detect-sudo/`,
`remote_shell` + `script/remote-run-commands/`). A bundled mlcflow then gets
new content against a frozen engine, and the feature silently stops working —
no error. **Any mlperf-automations PR touching `automation/` needs a companion
PR here.** `mlc_compat` in a script's `meta.yaml` is the guard that works.

**Don't break `from utils import …`:** `dynamic_import_module()` puts the
bundled `automation/` dir on `sys.path`, and ~188 `customize.py` files in
`mlperf-automations` rely on that to resolve a bare `from utils import ...`.
Touching that insertion breaks all of them at once.

**Result dict contract** — every action method must return:
- `{'return': 0}` on success
- `{'return': N, 'error': 'message'}` on failure (N > 0)

---

## Task playbooks

### "I need to add a new `mlc` command"

1. Add method to the appropriate Action class (hyphens → underscores in name):
   ```python
   # script_action.py — for a command that delegates to ScriptAutomation
   def my_action(self, run_args):
       return self.call_script_module_function("my_action", run_args)
   ```
   ```python
   # script_action.py — for a command handled entirely in mlcflow
   def my_action(self, run_args):
       self.action_type = "script"
       res = self.search(run_args)
       # ... do work ...
       return {'return': 0}
   ```

2. Register the command in `build_parser()` (`main.py`):
   ```python
   # General (script/cache/repo): add to the first for-loop ~line 363
   for action in ['run', 'pull', ..., 'my-action']:
   # Script-only: add to the second for-loop ~line 393
   for action in ['docker', ..., 'my-action']:
   ```

3. (Optional) Add a short command in `main.py` + `pyproject.toml`:
   ```python
   def mlcx():
       mlc_expand_short("my-action")
   ```
   ```toml
   mlcx = "mlc.main:mlcx"
   ```

### "I need to add a new dispatch branch for ScriptAutomation"

In `call_script_module_function()` (`script_action.py`), add an `elif` branch:
```python
elif function_name == "my_action":
    result = automation_instance.my_action(run_args)
```

### "I need to add validation for a new `meta.yaml` key"

In `meta_schema.py`:
```python
# Add to TOP_LEVEL_SCHEMA (top-level keys):
"my_new_key": DICT,   # or STR, LIST, BOOL, etc.

# Add to DEP_ENTRY_SCHEMA if it goes inside a dep entry
# Add to VARIATION_ENTRY_SCHEMA if it goes inside a variation
```
Types are sets like `STR = {"str"}`, `LIST = {"list"}`, etc. `validate_meta()`
is called during indexing — errors halt the index build.

### "I need to add a new error code or improve error messages"

In `error_codes.py`:
```python
class ErrorCode(Enum):
    MY_ERROR = (2008, "Description of the error")
```

To show actionable suggestions to the user, add a branch in `get_error_guidance()`:
```python
elif "my error pattern" in message:
    guidance["error_message"] = "Likely cause"
    guidance["suggestions"] = ["Do X to fix it."]
```

Error codes 2000–2007 are used; warning codes 1000–1006 are used. Pick the next
available number in each range.

### "I need to understand why `mlcr <tags>` fails"

```bash
mlcr <tags> --verbose                    # full debug output including ScriptAutomation logs
mlc find script --tags=<tags>            # verify script is indexed
mlc reindex                              # rebuild index if stale
mlc list repo                            # verify mlperf-automations is registered
mlc find cache --tags=<failing-dep>      # check if a dep is stale
mlc rm cache --tags=<failing-dep>        # clear dep cache
```

Check for `ScriptExecutionError` in the output — it prints a rerun command, the
error code, likely cause, suggestions, and version info file path.

### "I need to debug why the index is not picking up a script"

1. Check `meta.yaml` has all four required keys:
   `alias`, `uid`, `automation_alias`, `automation_uid`
2. Run `mlc reindex` to force a full rebuild
3. Check `~/MLC/repos/index_script.json` directly if needed
4. Run `mlcr <tags> --verbose` — validation errors are logged during indexing

### "I need to understand how args reach the automation engine"

`convert_args_to_dictionary()` in `utils.py` parses `sys.argv` extras:
- `--key=val` → `{"key": "val"}`
- `--flag` → `{"flag": True}`
- `--adr.compiler.tags=gcc` → `{"adr": {"compiler": {"tags": "gcc"}}}`
- `-v` → `{"v": True}` (unless it matches `log_flag_aliases`)

The resulting `run_args` dict is passed directly to `ScriptAutomation.run()`.

### "I need to call mlcflow from Python"

```python
from mlc.action import access

result = access({
    'action': 'run',
    'target': 'script',
    'tags': 'detect,os'
})
if result['return'] > 0:
    print(result['error'])
```

Or use the instance method on an `Action` object:
```python
from mlc.action import Action
a = Action()
result = a.access({'action': 'find', 'target': 'script', 'tags': 'detect,os'})
```

### "I need to write a test"

Look at existing tests for patterns:
```
tests/test_cache_mark_tmp.py
tests/test_action_invalid_meta_entries.py
```

Run tests with:
```bash
pip install -e .
python -m pytest tests/
```

### "I need to review a PR"

Full spec — required structure, severity definitions, evidence rules — is in
**AGENTS.md → "PR review format"**. Follow it exactly; the short version:

```
> attribution block: AI-performed, on whose request, what was inspected
## Verdict                  ← 2-3 sentences + merge recommendation
## 🔴 High severity         ← omit any tier with no findings
## 🟠 Medium severity
## 🟡 Low severity
## Suggested path to merge  ← numbered, ordered, concrete
```

Investigate before writing:
```bash
gh pr diff <N> --repo mlcommons/mlcflow
SHA=$(gh pr view <N> --repo mlcommons/mlcflow --json headRefOid -q .headRefOid)
git fetch --depth 1 https://github.com/mlcommons/mlcflow.git refs/pull/<N>/head && git checkout FETCH_HEAD
```

- Read the **callers and callees** of changed code, not just the diff. A comment
  claiming "we now read X" is only true if some caller actually reads X — grep
  for readers before believing it.
- Check whether CI actually runs for the change: compare the touched paths
  against each workflow's `paths:` filter. `automation/**` is **not** covered by
  `test-unit.yml`.
- Check whether the change duplicates existing coverage in `tests/`.
- Run the changed shell functions where you can; quote the real output as evidence.

Post as a plain comment so no required review slot is consumed:
```bash
gh pr comment <N> --repo mlcommons/mlcflow --body-file review.md
```

---

## Quick reference: key classes and where they live

| Class / function | File | What it does |
|---|---|---|
| `main()` | `main.py` | CLI entry point; parses args, dispatches to action |
| `mlcr()`, `mlcd()`, … | `main.py` | Short-form entry points registered in pyproject.toml |
| `get_action(target, parent)` | `action_factory.py` | Maps `"script"/"cache"/"repo"` → Action class |
| `Action` | `action.py` | Base: repo loading, index, CRUD (`add/rm/cp/mv/search`) |
| `Action.access(i)` | `action.py` | Python API: call any action programmatically |
| `ScriptAction` | `script_action.py` | Script actions; delegates to `ScriptAutomation` via `call_script_module_function` |
| `ScriptExecutionError` | `script_action.py` | Exception with script context; formatted by `_report_error()` |
| `RepoAction` | `repo_action.py` | `pull`/`add`/`rm`/`find` for repos |
| `CacheAction` | `cache_action.py` | `find`/`rm`/`show`/`prune`/`list`/`mark-tmp` for caches |
| `Index` | `index.py` | Incremental tag-based index; file-locked JSON |
| `validate_meta()` | `meta_schema.py` | Validates script `meta.yaml`; called during indexing |
| `get_error_guidance()` | `error_codes.py` | Pattern-matches error text → actionable suggestions |
| `get_new_uid()` | `utils.py` | Generates a 16-hex UID |

---

## Don'ts

- Don't raise exceptions for recoverable errors in action methods — return `{'return': 1, 'error': '...'}`
- Don't call `print()` for user-facing messages — use `logger.info/warning/error`
- Don't add `.` in flat arg key names — `.` triggers nested dict parsing in `convert_args_to_dictionary()`
- Don't push directly to `main` — open a PR; use `dev` only for urgent merges without approval
- Don't hard-code `~/MLC/repos` — use `self.repos_path` (which reads `MLC_REPOS` env var)
- Don't edit `index_script.json` or `modified_times.json` by hand — use `mlc reindex`
- Don't call `ScriptAutomation` directly — always go through `call_script_module_function()`
