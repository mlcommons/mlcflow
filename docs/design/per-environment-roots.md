# Per-environment roots: what changed, and why

Branch `per-env-repo-roots`, measured against `main` at merge base
`f47be56`. Nine substantive commits, 29 files, +4,095 / -100 lines.

The branch has already caught up with `main` once (`e3fdd4a`), so this is the
second catch-up, not the first.

This is the record to read before merging the two branches. It covers what
changed for each target and action, the decisions behind those changes
(including the options rejected), and what the merge with `main` still has to
reconcile by hand.

---

## Why any of this exists

`mlc-scripts` used to deliver its script content through a `git clone` hooked
onto setup.py's install command. Modern pip never runs that command — it
builds a wheel and installs the wheel — so the hook fired at most once per
machine, into the *builder's* home, and never at all once pip had cached the
wheel.

Shipping the scripts as the package payload fixes delivery but creates a
second problem: two virtual environments on two different `mlc-scripts`
versions now share one `~/MLC/repos`. Script content would be per
environment, but the cache would not — and cache matching is keyed on tags
plus an optional `meta.yaml` `version`, never on what a script actually does.
An entry produced by one version is silently reused by another whenever an
author forgot to bump `version`. A stale hit with no error is exactly the
failure that quietly corrupts a submission.

So the branch does two things: **discover an installed `mlc-scripts` and
register it in place**, and **give each environment its own roots** so
versions cannot contaminate each other.

## The foundation: two independent roots

Everything below follows from this.

| Root | Resolution order | Holds |
|---|---|---|
| **repo root** | `$MLC_REPOS`, else `~/MLC/envs/<hash of site-packages>` when `mlc-scripts` is importable here, else `~/MLC/repos` | `repos.json`, the index files, pulled repos |
| **cache root** | `$MLC_CACHE`, else `~/MLC/envs/<hash of site-packages>`, else `~/MLC/repos` | the `local` repo: caches, experiments, authored scripts, docker/apptainer contexts |

The two chains are structurally identical and **neither reads the other's
variable**. They merely share a default, so on a plain install the two trees
interleave in one directory and nothing moves.

New in `mlc/action.py`: `default_mlc_root()`, `shared_root()`,
`environment_key()`, `find_package_repo()`, `resolve_repos_path()`,
`resolve_cache_path()`, `_sync_package_repo()`, `_ensure_local_registered()`,
`_packaged_path()`, `_refuse_packaged_removal()`,
`_warn_orphaned_legacy_cache()`, `get_default_parent()`.

## What changed, by target and action

### Target: `repo`

| Action | Change | Purpose |
|---|---|---|
| `pull` | Declines on a repo that is not a git checkout, naming how it was installed instead of letting `git` fail | The packaged `mlc-scripts` ships `git: false`; git-pulling inside site-packages is never right |
| `pull` | On a uid tie the **already-registered** repo wins, and every run says which copy it used | A pulled checkout and the packaged copy share a uid; silently swapping them is undebuggable |
| `pull` (auto) | The last-resort auto-pull passes `ignore_on_conflict` | So an unattended `--branch=dev` clone can never displace a version-pinned `mlc-scripts` |
| `add` | No longer stamps `git: True` on a plain folder — `has_git_dir()` decides | A registered folder that lies about being git makes `pull` and `rm` take the wrong path |
| `rm` | Refuses on a pip-managed tree: warns, changes nothing, **exit 0**, warning code `1007` | pip owns that tree. Failing would break callers that remove a repo defensively |
| `rm` | On a non-git repo, requires confirmation; declining unregisters without deleting | Without a checkout, `git status` cannot vouch for the contents; deleting on a guess is the worse failure |
| `list` / `show` | Prints both active roots and *why* each is what it is | A hashed directory that changes with the shell is otherwise unsupportable |

`mlc/repo_action.py` gains `_repos_path_origin()` and `_cache_path_origin()`,
which render `(set by MLC_REPOS)`, `(auto: mlc-scripts <ver> at <path>)`,
`(from the registered local repo)` or `(default)`.

### Target: `script`

| Action | Change | Purpose |
|---|---|---|
| `add` | Destination redirected to `local:` **unconditionally** | `mlc add script foo` lands in the same place whether or not `mlc-scripts` is installed |
| `cp` | Destination resolved through the registry by alias, uid or basename, defaulting to the local repo | Authored scripts no longer land in site-packages |
| `cp` | Warns on a packaged destination, then **writes anyway** | Deliberate asymmetry with `rm`: cp adds, rm destroys |
| `rm` | Refuses on a pip-managed tree, same helper as `rm repo` | Deleting out of site-packages corrupts the install with no record pip can see |
| `rm` | The guard runs over the **whole result set before the first `rmtree`** | `Action.rm()` deletes as it iterates; a mid-loop return would leave earlier matches already gone |
| `run` | Script content may now resolve from the packaged repo, registered on every command | This is the delivery mechanism the whole branch exists to enable |

### Target: `cache`

No action logic changed. What changed is *where* it resolves: the `local`
repo now lives under the cache root, and `cache_path`, `local_cache_path` and
`local_repo_path` all derive from that single answer.

`local/` is kept **under** the cache root rather than flattening to
`envs/<hash>/cache`, because five call sites locate cache paths by finding the
`local` path component and assuming `cache` follows it. Preserving that
adjacency meant no changes in `automation/`.

### Target: `experiment`

Deliberately **not** guarded against packaged-tree writes. Noted as a known
gap rather than an oversight.

### Engine (`automation/`)

| File | Change |
|---|---|
| `docker_utils.py`, `apptainer.py` | Build contexts use the resolved `local_repo_path` instead of rebuilding `<root>/local/...`, which would leave a stray unregistered `local/` beside the real one |
| `remote_run.py` | `--remote_copy_mlc_repos` copies the repos that are actually **registered**, not a directory listing of the repo root — under a packaged install that root holds only `repos.json` and the index |
| `remote_run.py` | On the remote, copied repos are **registered with `mlc add repo`** rather than symlinked into `$MLC_REPOS` |
| `doc.py` | Documents the two variables separately |

### Cross-cutting

| Area | Change | Purpose |
|---|---|---|
| `index.py` | Deletion purge restricted to repos *this instance* actually scanned | An Action with a smaller repo list was deleting entries another Action had just written — 370 spurious "Detected deleted item" warnings on auto-pull |
| `index.py` | `remove_repo_from_index` no longer uses a bare prefix match | It stripped entries belonging to a sibling repo whose name is a prefix (`foo` vs `foo1`) |
| `main.py` | `default_parent` is now lazy (`get_default_parent()`) | `import mlc` used to construct an Action, creating directories and possibly rewriting `repos.json` with no command run |
| `action.py` | `repos.json` writes are file-locked; a non-writable root warns and continues | A bad root is a config error, not a crash |
| `utils.py` | New `has_git_dir()` / `is_git_repo()`, where meta's `git:` key wins over on-disk `.git` | The packaged tree ships `git: false` precisely so nothing tries to git-pull inside site-packages |
| `error_codes.py` | `WarningCode.PACKAGE_MANAGED_TARGET = 1007` | An exit code cannot distinguish "declined" from "removed"; callers check `warnings` |

## Decisions register

The reasoning that is not recoverable from the diff.

| # | Decision | Rejected alternative | Why |
|---|---|---|---|
| 1 | Cache root resolves per environment, same as the repo root | Keep one shared cache | Cache matching never keys on what a script does. Two versions sharing a cache silently reuse each other's entries. Cost accepted: a fresh environment re-downloads; `MLC_CACHE` is the opt-out |
| 2 | `MLC_CACHE` is the *only* variable that moves the cache root | Fall back to `$MLC_REPOS` | It coupled two independently configured roots and made the cache root depend on a variable that does not name it |
| 3 | Back-compat rests on the **registry**, not the environment | Special-case the old path in `resolve_cache_path()` | `_ensure_local_registered()` keeps an already-registered `local` when `MLC_CACHE` is unset, so a pre-1.4 layout keeps working. Reading the legacy path instead would re-couple the roots through a third path |
| 4 | Warn about an orphaned legacy cache; **move nothing** | Migrate the old cache | The old root stays self-consistent. A migration step is a failure mode; a one-line warning naming `MLC_CACHE` is not |
| 5 | Packaged-tree membership is **path containment**, never alias or uid | Match by alias/uid | A pulled checkout carries the same uid and usually the same alias. Removing *that* is a normal operation that has to keep working |
| 6 | `rm` on a packaged tree returns **exit 0** | Return non-zero | The request is not malformed — the tree is not ours to modify. Failing breaks callers that remove defensively. Warning `1007` carries the signal instead |
| 7 | `-f` does **not** override the packaged guard | Let force win | Force exists to skip confirmation prompts, not to authorise writing into another package manager's tree |
| 8 | `cp` warns and writes; `rm` warns and refuses | Treat both the same | Asymmetric on purpose: cp adds a file pip will overwrite on upgrade, rm destroys one pip still has in its RECORD |
| 9 | `add script` redirects to `local:` **unconditionally** | Redirect only when `mlc-scripts` is installed | A conditional redirect makes the same command mean different things on two machines |
| 10 | `local/` stays under the cache root | Flatten to `envs/<hash>/cache` | Five call sites assume `local` is immediately followed by `cache`. Preserving adjacency meant zero changes in `automation/` |
| 11 | On a uid tie, the already-registered repo wins | Newest wins | Registration order is the user's explicit `mlc pull repo`; the package arrives automatically |
| 12 | Remote repo copying **registers** on the remote | Symlink into `$MLC_REPOS` | The remote resolves its own root from its own interpreter. A path derived from this machine's site-packages means nothing there, and `$MLC_REPOS` is not normally exported in the remote shell |
| 13 | `resolve_cache_path()` takes `package_repo_path` as a **mandatory** argument | Default it | A partial revert of the resolution order in `__init__` becomes a `TypeError` rather than a silent return to one shared cache |

## Known gaps, carried deliberately

Recorded here so the merge does not mistake them for regressions.

- `get_container_path()` hard-codes the container-side cache root to
  `~/MLC/repos`. Needs a companion mlperf-automations change if the docker
  images install `mlc-scripts`.
- Sibling-environment cache duplication has no warning yet.
- `get_host_path()` / `fix_cache_paths()` match the **first** `local` path
  component, which breaks an `MLC_CACHE` such as `/usr/local/share/mlc`.
- `experiment` items are not guarded against packaged-tree writes.

## Merging with `main`

`main` is **51 commits ahead** since the last catch-up; the branch is 10
ahead (nine substantive plus that earlier merge).

> **Outcome (merge performed).** The `merge-tree` dry run predicted zero
> conflicts. That was wrong: it was run before the remote-provisioning work
> was committed, and that work touches `remote_run.py` and the remote-run
> workflow. The real merge produced **four** conflicts — `VERSION`,
> `mlc/action.py`, `automation/script/remote_run.py` and
> `.github/workflows/test-mlc-remote-run.yml`. The prediction that the
> `remote_copy_mlc_repos` block would merge *cleanly and wrongly* was also
> wrong in a useful direction: git flagged it as a conflict, so it had to be
> resolved by hand rather than slipping through. See "What the merge actually
> needed" below.

### What `main` brings

Twelve commits touching `remote_run.py` / `slurm_run.py`: isolated execution
mode (`--remote_isolated`), `--remote_env` passthrough, cache copy-back
(`--remote_copy_back_mlc_cache`), venv-usage cleanups, and installer fixes.
`tests/test_slurm_run.py` grows by ~742 lines.

### The one block that needs hand-merging

Both sides changed `remote_copy_mlc_repos`, in different places, so git will
combine them without complaint:

- **The branch** rewrote the *discovery* half — registered repos instead of
  `os.listdir()` — and replaced the remote-side symlink with `mlc add repo`.
- **`main`** rewrote the *surrounding* half — it hoisted `remote_copy_directory`
  to the top of the function, introduced `remote_copy_directory_for_cmd` and
  `remote_mlc_repos_path_for_cmd` for isolated mode, and changed
  `run_cmds.insert(0, ...)` to `run_cmds.insert(run_cmds_start_index, ...)`.

Taken naively, the merged block keeps the branch's `insert(0, ...)` and its
bare `remote_mlc_repos_path`, which puts the registration command before the
isolated-mode setup and points the copy at the wrong path. **Isolated mode
would break, silently, with a clean merge.**

The reconciliation, explicitly:

| Keep from | What |
|---|---|
| branch | the registered-repo discovery loop |
| branch | `mlc add repo` on the remote instead of `ln -sfn` into `$MLC_REPOS` (decision 12) |
| main | `run_cmds_start_index` instead of `0` |
| main | `remote_mlc_repos_path_for_cmd` instead of `remote_mlc_repos_path` |
| main | the hoisted `remote_copy_directory` / `_for_cmd` variables |

### Also worth checking after the merge

- `remote_python_venv` default: branch has `i.get('remote_python_venv', 'mlcflow')`,
  main has `i.get('remote_python_venv') or 'mlcflow'`. Main's handles an
  explicit empty string; take main's.
- `main`'s isolated mode points the cache at
  `<copy_directory>/local/cache`. Confirm that agrees with decision 10 —
  `local/` under the cache root — on the remote side.
- `tests/test_slurm_run.py`: main's expanded version is authoritative; the
  branch never touched it.
- `main`'s installer fixes overlap the venv-reuse behaviour the provisioning
  work depends on. Re-run the remote-run CI after merging.

## What the merge actually needed

Four conflicts, and three follow-on fixes the conflicts did not surface.

| File | Resolution |
|---|---|
| `VERSION` | Kept `1.4.0a3`; `main`'s `1.3.7` is older, and `mlc-scripts` pins `mlcflow>=1.4.0a3` |
| `mlc/action.py` | Kept the branch's constructor — `main`'s side referenced `mlc_local_repo_path`, a variable this branch removed, so taking it would have been a `NameError`. Adopted `main`'s race-safe `open(..., 'x')` + `FileExistsError` from its thread-safety work, ordered before the branch's `RootNotWritableError` (which is also an `OSError`) |
| `automation/script/remote_run.py` | Per the table above, plus a bug the merge exposed — see below |
| `.github/workflows/test-mlc-remote-run.yml` | Union of both sides' `paths:` filters |

### A latent bug the merge exposed

The branch registered copied repos with `run_cmds.insert(0, ...)`. By that
point `run_cmds` already began with the installer, so `mlc add repo` was
placed **before mlcflow existed on the remote** — and the loop is
`|| true`-guarded, so it failed silently and registered nothing.
`--remote_copy_mlc_repos` copied the repos and then never registered them.

`main`'s `run_cmds_start_index` is not the fix either: it points *before* the
installer too, which is correct for `main`'s pure-shell `ln -sfn` and wrong
for a command that needs the CLI. The merged code introduces
`run_cmds_after_venv`, captured immediately after the activation command.

Verified on the merged code, isolated mode plus a repo copy plus a package
pin: `installer=6 < register=8 < provision=9 < mlcr=10`, with the isolated
preamble (including `export MLC_REPOS`) still at 0-5.

### Two tests that had to change

Both are `main`'s tests encoding `main`'s mechanisms, not regressions:

- `test_slurm_run.py` asserted the run commands contain `$MLC_REPOS` — the
  symlink this branch deliberately replaced (decision 12). Now asserts
  `mlc add repo` is present *and ordered after the installer*. Isolated mode
  exports `MLC_REPOS`, so registration lands in the isolated root.
- `test_thread_safety.py` pinned only `MLC_REPOS`, which moved both roots on
  `main`. Under decision 2 it does not, so the test was writing cache items
  into the developer's real `~/MLC/repos/local`. Now pins both, the same fix
  the branch already applied to two CI steps.

The remote-provisioning bootstrap tests also stopped asserting literal
installer and activation strings, which `main` legitimately changed (`dev` →
`main` in the installer URL; activation is now a generated venv-picking
command carrying a fresh uuid per call, so two invocations are not even equal
to each other). They now assert the guarantee — an unconfigured run adds
nothing, a pin inserts exactly one command in exactly one place.

### Result

172 tests pass in mlcflow (108 before the merge), 14 in mlperf-automations.
`mlc list repo` still reports both roots and their origins. The ssh quoting
round-trip still holds with `main`'s new base64 activation command, which
contains double quotes but no single quotes.

Still to do: run the remote-run CI workflow, which is the only thing that
exercises a real node.

---

# Open items after the merge

Compiled by checking each documented behaviour against the code and, where
possible, running it. Evidence level is stated per item: **proven** means it
was executed, **read** means it was established from the source.

## A. Discrepancies detected

### A1. `--remote_isolated` no longer isolates the cache  *(proven on hardware — FIXED)*

The isolated preamble exports `MLC_REPOS` only
(`remote_run.py:175`, `slurm_run.py:175`), and its comment says "so that MLC
state is contained and cleaned up". Under decision 2, `MLC_REPOS` does not
move the cache root. Confirmed on a real Linux node (mlc2), running the
preamble verbatim with the branch mlcflow installed and `HOME` redirected
into the test workspace:

```
MLC_REPOS exported = <isolated>/MLC
MLC_CACHE          = <unset>
cache path         = <HOME>/MLC/repos/local/cache/probe2   <- not isolated
```

Only `repos.json` landed in the isolated dir; the `local` repo, which owns
the cache, was created under `HOME`.

Two consequences. Cache entries land in the remote's real home and survive
the `trap rm -rf` that cleans the temp dir. And
`--remote_copy_back_mlc_cache` reads `{tmp}/MLC/local/cache`
(`remote_run.py:370`), which is empty — the copy-back silently returns
nothing.

The branch's own "MLC_REPOS is set but MLC_CACHE is not" warning fires here.
It reported the problem and nothing acted on it.

**Fixed** by C1: the preamble now exports both roots. Re-run on the same node
with the fix in place, the cache resolved to
`<isolated>/MLC/local/cache/probe-c1` — which is exactly the directory
`--remote_copy_back_mlc_cache` reads — and `HOME` was left with zero entries.
Two unit tests cover it, and both were confirmed to fail with the fix
reverted.

### A2. `consistent: true` is reachable for genuinely different versions  *(proven — FIXED)*

`get_commit_hash()` returns the literal string `"unknown"` when git metadata
is absent (`mlperf-automations/setup.py:90`). The aggregator compares on
`commit` alone, so two wheels built without git metadata compare equal and
pass, at different versions.

### A3. The installer README documents something the installer does not do  *(read)*

`docs/install/README.md` lists "Cloning the automation repository" among the
installer's jobs. `pull_repo()` exists, has `--mlc-repo` / `--mlc-repo-branch`
flags wired to it, and `main()` never calls it.

### A4. `--remote_no_internet` needs internet on the head node  *(proven)*

An earlier revision of this note claimed the flag was "broken for pip users".
That was too strong, and the correction matters: `--remote_no_internet`
describes the **remote**, which is why the installer is rsynced over instead
of curled there. The head fetching it is legitimate.

The real limit is narrower. `_get_local_installer()` looks for
`docs/install/mlcflow_unix_installer.sh` relative to the installed package.
`pyproject.toml` ships `mlc`, `automation` and `automation.script` only, and
package-data lists just `COPYRIGHT.txt`, `meta.json` and `README.md` — so
`docs/` is genuinely not in the wheel, and a pip-installed head falls through
to `urllib.request.urlretrieve(INSTALLER_URL)`.

So: a pip-installed head **with** internet works, downloading once per run.
A fully air-gapped environment — where the head has no internet either, which
is the normal shape of an air-gapped cluster — fails, and fails with an
uncaught `URLError` rather than the `{'return': 1, 'error': ...}` the
convention in `AGENTS.md` requires. Shipping the installer in the wheel (C3)
fixes both the redundant download and the crash.

### A5. Package mode installs mlcflow twice  *(proven)*

The installer installs mlcflow, then `pip install mlc-scripts==X` replaces it:

```
Successfully uninstalled mlcflow-1.3.6
Successfully installed mlc-scripts-1.2.0a4 mlcflow-1.4.0a3
```

Correct end state; wasted download and a second chance to fail on a flaky
network.

### A6. The container-side cache root does not follow the resolved roots  *(read)*

`docker_utils.py:494-496` hard-codes `["", "home", username, "MLC", "repos"]`.
Needs a companion mlperf-automations change if the images install
`mlc-scripts`.

### A7. `local` is matched by first occurrence  *(read)*

`docker_utils.py:465,497` use `path_split.index("local")`, which breaks an
`MLC_CACHE` such as `/usr/local/share/mlc`.

### Not one of ours: `mlc add cache <name>` crashes  *(proven, pre-existing)*

Found while testing A1 on real hardware, and recorded here only so it is not
re-discovered and mistaken for merge fallout.

```
$ mlc add cache probe --tags=a1
TypeError: join() argument must be str, bytes, or os.PathLike object, not 'NoneType'
  action.py:951  target_path = os.path.join(repo_path, target_name)
```

`main.py` never puts `target_name` into `run_args`, and `Action.action_type`
is `None` on the inherited `add`, so `target_name` resolves to `None`. The
Python API is unaffected because callers pass `target_name` explicitly —
which is why the test suite never caught it.

**Not introduced by this branch.** The line is byte-identical on `main` and
absent from the branch diff, and the crash reproduces on a clean `main`
install (1.3.7) with no MLC environment variables set at all. It also raises
rather than returning `{'return': 1, ...}`, against the convention in
`AGENTS.md`. Belongs in its own issue, not in this merge.

## B. To be tested to determine

No coverage either way — the behaviour is asserted by reading the code only.

| # | Behaviour | Target / action |
|---|---|---|
| B1 | Declines on a non-git registered repo | `repo` / `pull` |
| B2 | Does not stamp `git: True` on a plain folder | `repo` / `add` |
| B3 | Confirms on a non-git repo; declining unregisters without deleting | `repo` / `rm` |
| B4 | Index purge restricted to repos this instance scanned | cross-cutting |
| B5 | `remove_repo_from_index` exact match (`foo` vs `foo1`) | cross-cutting |
| B6 | `import mlc` creates no directories and writes no registry | cross-cutting |
| B7 | meta `git:` wins over an on-disk `.git` | cross-cutting |
| B8 | `repos.json` locking under concurrent writers | cross-cutting |
| B9 | uid-tie precedence in `register_repo` (only the auto-pull half is covered) | `repo` / `pull` |
| B10 | End-to-end run against packaged content | `script` / `run` |
| B11 | Copy-back failures propagate (mlperf-automations) | `remote-run-commands` |
| B12 | Anything at all against a real remote node | remote-run CI |
| B13 | Whether sibling-environment cache duplication is a practical problem | `cache` |
| B14 | Whether `experiment` actually writes into a packaged tree | `experiment` |

## B12 results: run against a real remote node

Executed from this machine against `mlc2` (Linux, Python 3.12), head node
running the merged branch. Everything the tooling controls was contained
under `/data/common/anandhu`.

**Confirmed working, end to end:**

| Case | Result |
|---|---|
| default mode | remote got `mperf-automations@dev`, unchanged behaviour |
| `--remote_mlc_scripts=1.1.0` | remote venv reports exactly `mlc-scripts 1.1.0` |
| re-pin to `1.0.2` in the **reused** venv | moved correctly — the case flagged as most likely to fail quietly |
| `--remote_repo_ref=6418ce5df` | remote checkout moved `7c2645d24` → `6418ce5df` |
| `--remote_provision=mirror`, dirty head | refused **before connecting** (zero ssh calls), naming repo, commit and both alternatives |
| C1 through the real multi-node script | cache resolved inside the isolated dir, and the `trap` removed it |
| `mlc_scripts_version` | fully populated, `consistent: false`, correctly reporting head `dirty: true` |

**Not tested:** mirror's *success* path. It needs a clean checkout and this
machine's content repo has uncommitted work; forcing it clean would disturb
the user's tree for little gain, since mirror emits the same
`mlc pull repo --checkout=<sha>` that repo mode above proved on hardware.
The derivation itself is unit-tested.

### B12a. The remote venv is not isolated, and not under `$HOME`  *(proven — FIXED)*

The default venv argument is the bare name `mlcflow`, and the installer
resolves it against the **ssh login directory**, not `$HOME`:

```
[INFO] Found working virtual environment at: mlcflow
  source mlcflow/bin/activate
```

Two consequences. Exporting `HOME` does not move the venv. And a
provisioning run without an explicit absolute `--remote_python_venv`
pip-installs into whatever venv happens to sit in the remote user's login
directory — so `--remote_mlc_scripts=X` mutates an environment the operator
may share with other work. `--remote_isolated` did not cover this: it
isolated the MLC roots, not the interpreter.

`slurm_run.py` gets this right by accident -- it `cd`s into the isolated dir
(line 174), so the relative name lands inside. `remote_run.py` deliberately
does not `cd`, so that rsync targets stay valid, and the venv escaped. Two
implementations of "isolated" differing in a way nobody wrote down. And
`remote_run.py`'s own `--remote_no_internet` error already asserted slurm's
behaviour -- *"each isolated run re-installs mlcflow into a fresh venv"* --
which was false as implemented.

**Fixed:** under `--remote_isolated` the venv now defaults to `{tmp}/venv`,
inside the dir the trap removes. An explicit `--remote_python_venv` still
wins, and non-isolated runs are untouched. The cost is negligible: the trap
already deletes the whole MLC tree, so every isolated run re-clones
mperf-automations regardless -- far more expensive than a venv.

Proven on `mlc2` with `--remote_isolated --remote_mlc_scripts=1.1.0` and no
explicit venv -- the command that previously would have pip-installed into
the operator's own venv:

```
venv used               : <base>/mlcflow-isolated-7cd8.../venv
user venv mtime after   : 2026-05-27 05:37:41.320524240  (identical to baseline)
mlc-scripts in ~/mlcflow: absent
isolated dir afterwards : removed by the trap
```

Three unit tests cover it; the containment one was confirmed to fail with the
fix reverted.

### B12b. Default mode gives a *stale* version, not the newest  *(proven)*

The proposal says unconfigured workers get "newest on PyPI that morning".
On a node that already has a venv they get whatever is in it. `mlc2` had
`mlcflow 1.2.3` from May and reused it. The drift is real but its direction
is the opposite of what was documented, and pinning matters more, not less.

### B12c. `mlc-scripts==1.2.0a4` does not exist  *(proven)*

PyPI has `mlc-scripts` up to `1.1.0` and `mlcflow` up to `1.3.6`; there is no
`1.4.0a3` and no `1.2.0a4`. The version in the proposal is hypothetical, and
the published `mlc-scripts` wheels carry no importable script content — that
is the unreleased `ship-scripts-in-wheel` work. So package mode is proven
mechanically (the pin lands, re-pinning moves) but its payoff, "the wheel
carries the scripts so the `dev` fallback stops firing", cannot be shown
until such a wheel is published.

### B12d. The multi-node script forced remotes to use `$HOME`  *(fixed)*

`get-mlperf-multi-node-system-info` forwarded the provisioning inputs but not
`remote_python_venv`, `remote_isolated` or `remote_isolated_base_dir`, so
every node was pinned to `~/mlcflow` and `~/MLC` with no way to say
otherwise. Added to the same pass-through map.

### B12e. Two remote paths remain hard-coded  *(read)*

`detect-host-system-details` writes `~/system-info.json`, and the multi-node
script hard-codes the remote output directory `/tmp/mlperf-system-info-single-node`
(`customize.py`, the `out_dir_path` passed to `remote_run`). Neither honours
any placement input, so a run always writes to those two locations on every
node. Worth an input of its own.

## C. To be fixed

Ordered by consequence.

| # | Fix | Addresses | Size |
|---|---|---|---|
| C1 | ~~Export `MLC_CACHE` alongside `MLC_REPOS` in the isolated preamble, both files~~ **done, verified on hardware** | A1 | ~2 lines |
| C2 | ~~Compare `version` as well as `commit`~~ **done** — identity is now `(commit, version)`, literal `unknown` treated as absent, and an identity with nothing in it no longer confirms | A2 | small |
| C3 | Ship the installer inside the wheel (file move + `package-data`) | A4 | small |
| C4 | Call `pull_repo()` from `main()`, or correct the README | A3 | small |
| C5 | Make `get_container_path()` follow the resolved roots | A6 | needs a companion PR |
| C6 | Anchor the `local` path match instead of taking the first occurrence | A7 | small |
| C7 | Avoid the redundant mlcflow install in package mode | A5 | needs an installer flag; low value |

C1 was the one to do before anything ships: it silently defeated a documented
flag, and it is the same class of failure as the `MLC_REPOS`-only pinning that
made `test_thread_safety` write into a real home cache. It is now done and
verified end to end on a real remote node. C2-C7 remain open.
