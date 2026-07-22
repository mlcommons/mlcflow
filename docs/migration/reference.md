# Option B Migration — Reference

Complete technical reference for the architecture introduced in **mlcflow 2.0.0 /
mlc-scripts 2.0.0** (the "Option B" migration). If you want the *why*, see
[Why Option B](index.md). If you want task-oriented steps, see
[Running remote/Docker without a clone](remote-and-docker.md) or
[Upgrading from pre-2.0 mlcflow](upgrading.md).

---

## Package layout

Two PyPI packages now divide the responsibility that used to live in two git
repos glued together at runtime:

| Package | Repo | Contains |
|---|---|---|
| `mlcflow` | [mlcommons/mlcflow](https://github.com/mlcommons/mlcflow) | CLI driver (`mlc/main.py`, `mlc/action.py`, `mlc/script_action.py`, …) **and** the script execution engine (`mlc/engine/`) |
| `mlc-scripts` | [mlcommons/mlperf-automations](https://github.com/mlcommons/mlperf-automations) | ~378 benchmark script directories, shipped as pip package data at `mlc_scripts/script/**` |

`mlc-scripts` depends on `mlcflow>=2.0.0,<3` (see `pyproject.toml`). There is no
dependency in the other direction — `mlcflow` works standalone (you can register
your own script repos), `mlc-scripts` is the officially published content.

### `mlc/engine/` — the execution engine (now inside mlcflow)

| File | Role |
|---|---|
| `module.py` | `ScriptAutomation` — the core script-execution class (dep resolution, variations, cache lookup, run.sh/run.bat dispatch) |
| `cache_utils.py` | Cache search, validation, and path-rewriting (`fix_cache_paths`) when a cached entry's recorded paths point at an old cache root |
| `docker.py` / `docker_utils.py` | Docker container build + run |
| `apptainer.py` | Apptainer/Singularity container build + run |
| `remote_run.py` | SSH remote execution (`mlcrr`/`mlcre`/`mlcrd`) |
| `experiment.py` | Experiment/sweep runs (`mlce`/`mlcre`) |
| `meta_schema.py` | `meta.yaml` schema validation |
| `script_utils.py` | Script search/selection helpers |
| `help.py` / `doc.py` / `lint.py` / `validate.py` | `mlc help`, `mlc doc`, `mlc lint`, meta validation entry points |
| `utils.py` | Engine-internal utilities |
| `__init__.py` | Exposes `ScriptAutomation`; also re-exports these utils as a top-level `utils` module (see [Backward compatibility](#backward-compatibility-the-utils-shim) below) |

Before the migration, this code lived in `mlperf-automations` at
`automation/script/*.py` and was loaded at runtime via
`importlib.util.spec_from_file_location()` — `dynamic_import_module()` in
`script_action.py`. That function, and the auto git-clone fallback that used to
back it, are gone. `mlc/script_action.py` now does:

```python
from mlc.engine import ScriptAutomation
```

directly, at import time.

### `mlc_scripts` — script content as package data

```python
# mlc_scripts/__init__.py
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "script")
```

`pyproject.toml` in `mlperf-automations` declares:

```toml
[tool.setuptools]
packages = ["mlc_scripts"]
include-package-data = true

[tool.setuptools.package-data]
"mlc_scripts" = ["script/**/*"]
```

This bundles every file in every script directory — `meta.yaml`, `customize.py`,
`run.sh`, `run.bat`, `README.md`, `tests/`, and any binary/source assets a
script needs (`.jpg`, `.c`, `.cpp`, …) — as read-only package data. A plain
`pip install mlc-scripts` (wheel, sdist, or editable) ships all of it; nothing
is fetched at runtime.

`setup.py` and its `CustomInstallCommand` (which used to run `mlc pull repo
mlcommons@mlperf-automations` as a post-install step) were removed entirely —
packaging is pure `pyproject.toml` now.

!!! note "`by-category/` is a docs mirror, not the real script tree"
    `mlc_scripts/script/by-category/**` is a set of symlinks back into the
    canonical `mlc_scripts/script/<alias>/` directories, kept for the published
    docs site's category browsing. The engine always resolves scripts via their
    canonical path; `by-category` is not a second copy of script logic.

---

## How mlcflow discovers `mlc-scripts` content

`Action.__init__()` (`mlc/action.py`) calls `_get_package_scripts_repo()` on
every startup:

```python
def _get_package_scripts_repo(self):
    import mlc_scripts
    scripts_dir = mlc_scripts.SCRIPTS_DIR
    pkg_dir = os.path.dirname(scripts_dir)          # {site-packages}/mlc_scripts
    repo = Repo(path=pkg_dir, meta={
        "alias": "mlc-scripts-pkg",
        "uid": "mlcscriptspkg000",
        "name": "Bundled mlc-scripts package (read-only)",
    })
    repo.readonly = True
    return repo
```

This synthetic, read-only `Repo` is prepended to `self.repos` alongside any
repos you've registered yourself (via `mlc add repo` / `mlc pull repo`). The
index (`mlc/index.py`) scans it exactly like any other repo. If `mlc-scripts`
isn't installed, this silently returns `None` and mlcflow falls back to
whatever repos you've registered — mlcflow does not hard-require `mlc-scripts`.

### Priority on a UID clash — bundled package wins by default

If a registered repo (e.g. a local `git clone` you're actively developing
against) defines a script with the **same UID** as one already shipped in the
`mlc-scripts` package, `Index._process_config_file()` has to pick one:

- **Default: the bundled package wins.** The installed/published script runs.
  This exists specifically so a stale local clone left over from the old
  auto-clone flow can't silently shadow a fresh `pip install` — the exact
  failure mode this migration is designed to eliminate.
- **`MLC_PREFER_DEV_SCRIPTS=1`** (also accepts `true`/`yes`/`on`) flips this:
  your registered/editable dev repo wins instead. Set this while actively
  developing a script (e.g. `pip install -e ./mlperf-automations`).

The decision is **order-independent** — it holds the same way regardless of
which repo gets indexed first, for both full and incremental index rebuilds.

If any scripts get shadowed this way, `mlc reindex` (and any command that
triggers indexing) prints a rolled-up warning:

```
N script(s) skipped due to a UID clash between the bundled mlc-scripts package
and a registered/dev repo (bundled package wins by default). If you have local
edits to a shadowed script, set MLC_PREFER_DEV_SCRIPTS=1 ...
```

Run with `--verbose` to see exactly which scripts were shadowed
(logged at `DEBUG`).

---

## Cache and repo path resolution

Resolution order for `self.repos_path` (`mlc/action.py`, `Action.__init__`):

```
1. $MLC_REPOS, if set             → used as-is, unconditionally
2. $CONDA_PREFIX, if set           → {CONDA_PREFIX}/mlc_cache
   (but NOT if $CONDA_DEFAULT_ENV == "base" — see note below)
3. venv (sys.prefix != sys.base_prefix) → {sys.prefix}/mlc_cache
4. fallback                        → ~/MLC/repos
```

!!! note "Why conda `base` is excluded"
    `CONDA_PREFIX` is set whenever *any* conda environment is active —
    including `base`, which many users auto-activate via `conda init` in
    their shell rc without consciously opting into a dedicated environment.
    Redirecting those users would silently make their existing `~/MLC/repos`
    cache and registered repos invisible. Only named, deliberately-activated
    conda environments get the isolated cache; `base` falls through to the
    venv check (which will also be false for a bare `base` shell) and then to
    `~/MLC/repos`.

**Why venv/conda-anchored at all?** Each virtualenv or conda environment gets
its own independent `repos.json` + cache, instead of one global
`~/MLC/repos` shared (and collided on) across every environment on the
machine. It also survives `pip install -U` cleanly: pip only ever touches
`lib/pythonX.Y/site-packages/` inside a venv, never the venv root, so a cache
anchored at `{sys.prefix}/mlc_cache` is never touched by an upgrade.

**Cache root specifically** (separate from `repos_path`, but nested under it by
default):

```
self.cache_root = $MLC_CACHE_DIR, if set, else {repos_path}/local/cache
```

`MLC_CACHE_DIR` lets you point the cache root somewhere else entirely — e.g. a
large-disk mount for multi-TB dataset caches — independent of where
`repos.json` itself lives.

**One-time legacy warning:** if the venv/conda-anchored default is about to
create a brand-new, empty cache while a pre-existing, already-populated
`~/MLC/repos` sits unused (has a `repos.json` and a populated `local/`), you'll
see:

```
Using a new cache at <new path> — your existing cache/registered repos at
~/MLC/repos are not used from this environment. Set MLC_REPOS=~/MLC/repos to
keep using them here.
```

### Environment variable summary

| Variable | Effect |
|---|---|
| `MLC_REPOS` | Overrides `repos_path` entirely (where `repos.json`, `local/`, and — by default — the cache live). Unconditional; takes priority over venv/conda detection. |
| `MLC_CACHE_DIR` | Overrides the cache root specifically, independent of `MLC_REPOS`. |
| `MLC_PREFER_DEV_SCRIPTS` | `1`/`true`/`yes`/`on` — let a registered/dev repo override the bundled `mlc-scripts` package on a UID clash (default: package wins). |

---

## Remote execution (`mlcrr` / `mlcre` / `mlcrd`) — no more auto-clone

Before the migration, the SSH bootstrap on the remote host always ran the
installer's `pull_repo()`, which did a full `git clone` of `mlperf-automations`
on **every remote run**, regardless of whether the remote already had
`mlc-scripts` installed. The bootstrap now does this instead
(`mlc/engine/remote_run.py`):

```
1. Fetch and run the mlcflow installer (from GitHub, or a local path — see below)
2. Activate the target venv
3. pip install -U mlc-scripts   (or a custom pip spec — see below)
4. (optional) mlc pull repo     (only if remote_pull_mlc_repos is explicitly set)
5. Run the actual script command
```

`docs/install/mlcflow_unix_installer.sh`'s own default flipped too: the
installer's `pull_repo()` step is now **opt-in** (`--pull-repo`), not opt-out
(the old `--skip-repo-pull`, which is still accepted for compatibility but is
now a no-op since skip is already the default). A normal `mlcrr`/`mlcre` call
with no special flags no longer clones anything on the remote host.

### `remote_run` / `remote_experiment` / `remote_docker` flags

All three actions (`mlcrr`, `mlcre`, `mlcrd`) share the same dispatch in
`remote_run.py` and accept the same flags:

| Flag | Effect |
|---|---|
| `--remote_host` | IP or hostname (default: `localhost`) |
| `--remote_port` | SSH port (default: `22`) |
| `--remote_user` | SSH username |
| `--remote_password` | Password for SSH authentication |
| `--remote_ssh_key_file` | Path to an SSH private key |
| `--remote_skip_host_verify` | Skip SSH host key verification |
| `--remote_python_venv` | Remote venv name (default: `mlcflow`) |
| `--remote_pull_mlc_repos` | Explicit additive `mlc pull repo` step on the remote (separate from, and independent of, the auto-clone-by-default behavior that was removed) |
| `--remote_copy_directory` | Remote directory for copied files (default: `mlc-remote-artifacts`) |
| `--remote_pre_run_cmds` | Commands to run on the remote before the main script |
| `--remote_client_refresh` | Refresh the SSH client connection |
| `--remote_local_installer_path` | Path to a local `mlcflow_unix_installer.sh` — use `cat <path>` instead of `curl`-ing it from GitHub. Useful for testing installer changes before they're merged. |
| `--remote_local_mlcflow_path` | Path to a local mlcflow checkout to install on the remote instead of from PyPI |
| `--remote_skip_repo_pull` | Skip the installer's repo-pull step (default: `True` — see above) |
| `--remote_mlc_scripts_pip_spec` | pip install spec for `mlc-scripts` on the remote (default: `mlc-scripts`; accepts a local path or a version pin) |

**Verifying the no-clone guarantee** — see
[Running remote/Docker without a clone](remote-and-docker.md).

---

## Docker — same no-clone guarantee

`mlc_scripts/script/build-dockerfile/dockerinfo.json` lists `mlc-scripts` in
every `python-packages` list, so the generated Dockerfile installs scripts
from pip inside the container. `build-dockerfile/customize.py` computes:

```python
scripts_from_pip = any(p in ('mlc-scripts', 'mlc_scripts') for p in python_packages)
```

and skips both the build-time `RUN mlc pull repo ...` and sets
`MLC_DOCKER_NOT_PULL_UPDATE=True` for the runtime pull whenever
`local_wheels_path or scripts_from_pip`. Escape hatches if you specifically
need the repo pulled at runtime anyway: `MLC_DOCKER_HOST_MLC_REPOS` (mount host
repos into the image) or `MLC_REPO_PATH` (copy a local repo into the build
context).

---

## Backward compatibility: the `utils` shim

Roughly 190 script `customize.py` files do `from utils import ...` — a holdover
from the old dynamic loader, which prepended the engine's directory to
`sys.path` so that bare import worked. `mlc/engine/__init__.py` re-exposes the
engine's utils module as a top-level `utils` module, so **every existing
script's `customize.py` runs completely unmodified** under the new engine —
this is the compatibility contract the whole migration depends on for the
~378 already-published scripts.

---

## See also

- [Why Option B](index.md) — the problem this solves and the trade-offs
- [Running remote/Docker without a clone](remote-and-docker.md) — how-to + verification
- [Upgrading from pre-2.0 mlcflow](upgrading.md) — for existing users/environments
- [Tutorial: fresh install to first run](tutorial-fresh-install.md)
- `mlperf-automations` [migration page](https://github.com/mlcommons/mlperf-automations/blob/migration-option-b/docs/migration.md) — content-repo side of this same migration
