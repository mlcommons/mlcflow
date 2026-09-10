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
`git merge-tree` predicts **zero textual conflicts**. That prediction is
correct and also misleading — one block merges cleanly and wrongly.

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

### Suggested order

1. Commit the in-flight remote-provisioning work (it modifies `remote_run.py`,
   which the merge also touches — git will refuse otherwise).
2. `git merge main`.
3. Hand-reconcile the `remote_copy_mlc_repos` block per the table above.
4. Re-apply / verify the `provision.resolve()` call still sits after venv
   activation and before the `mlcr` line.
5. Run both suites, then the remote-run CI workflow.
