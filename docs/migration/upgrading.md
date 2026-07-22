# How to upgrade from pre-2.0 mlcflow

You had `mlcflow` installed and a registered `mlperf-automations` clone before
the Option B migration. Here's what changes when you upgrade, and how to keep
(or intentionally leave behind) your existing setup.

## Prerequisites

- An existing pre-2.0 `mlcflow` install with a populated `~/MLC/repos`
  (registered repos, cache entries)
- Enough familiarity with your own setup to know whether you have local edits
  to any scripts (i.e. whether you've ever run `mlc add script` or hand-edited
  a `customize.py`/`meta.yaml` inside your registered clone)

## Steps

1. Upgrade both packages together:

   ```bash
   pip install -U mlcflow mlc-scripts
   ```

2. Run any `mlc`/`mlcr` command and watch the very first lines of output:

   ```bash
   mlcr detect,os -j --verbose
   ```

   - If you see a line starting with `Using a new cache at ...` — read it.
     This means the venv/conda-anchored default (see
     [Reference](reference.md#cache-and-repo-path-resolution)) chose a
     **new, empty** cache location, and your old `~/MLC/repos` still exists
     but isn't being used from this environment.
   - If you don't see that line, either you're not in a venv/conda
     environment (so the fallback is still `~/MLC/repos`, unchanged), or
     `MLC_REPOS` is already set explicitly.

3. **To keep using your existing cache and registered repos exactly as
   before**, set `MLC_REPOS` to the old path (add this to your shell profile
   if you want it permanent):

   ```bash
   export MLC_REPOS=~/MLC/repos
   ```

   This is the simplest option if you don't care about per-venv cache
   isolation and just want zero behavior change.

4. **To adopt the new per-environment cache** (recommended for anyone running
   mlcflow across multiple venvs/projects), leave `MLC_REPOS` unset and let
   each environment get its own fresh cache. Your old `~/MLC/repos` is left
   untouched on disk — nothing is deleted — you can point back at it with
   `MLC_REPOS` from any environment later if needed.

5. **If you have local edits to any script** (a hand-modified `customize.py`,
   or a script added via `mlc add script` that isn't in the published
   `mlc-scripts` package), check whether it's now being shadowed:

   ```bash
   mlc reindex --verbose
   ```

   Look for a line like:

   ```
   N script(s) skipped due to a UID clash between the bundled mlc-scripts
   package and a registered/dev repo (bundled package wins by default) ...
   ```

   If your edited script's UID is one of the ones skipped, your edits are
   currently **not** being used — the bundled package's version runs instead.

6. **To make your local edits take effect again**, set:

   ```bash
   export MLC_PREFER_DEV_SCRIPTS=1
   ```

   This flips the priority so your registered/dev repo wins over the bundled
   package on any UID clash. Re-run `mlc reindex --verbose` to confirm the
   shadowing warning is gone.

## Verification

```bash
python -c "from mlc.engine import ScriptAutomation; print('engine OK')"
python -c "import mlc_scripts, os; print('scripts:', sum(1 for e in os.scandir(mlc_scripts.SCRIPTS_DIR) if e.is_dir()))"
mlcr detect,os -j
```

All three should succeed: `engine OK`, a script count around 378, and a
`detect,os` result with `MLC_HOST_OS_TYPE` populated.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `mlcr` behaves as if your cache is empty after upgrading | New environment picked the venv/conda-anchored default instead of your old `~/MLC/repos` | `export MLC_REPOS=~/MLC/repos` (see step 3) |
| A script you customized stopped reflecting your edits | Bundled `mlc-scripts` package is winning the UID-clash priority (default behavior) | `export MLC_PREFER_DEV_SCRIPTS=1`, then `mlc reindex` |
| `mlc reindex` reports shadowed scripts you don't recognize | You have an old registered clone with scripts that also ship in `mlc-scripts` now | Harmless if you don't need your copy to win — otherwise set `MLC_PREFER_DEV_SCRIPTS=1` |
| `ImportError: No module named mlc_scripts` | Only `mlcflow` was upgraded, not `mlc-scripts` | `pip install -U mlc-scripts` — the two packages are independent, upgrading one doesn't upgrade the other |

## See also

- [Reference](reference.md) — full technical detail on cache resolution and priority rules
- [Why Option B](index.md) — the reasoning behind these defaults
