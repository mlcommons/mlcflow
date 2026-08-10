# TESTING.md — split-roots / packaged-scripts feature

Test plan and results for the two-root (`MLC_CACHE` + `MLC_REPOS`) change in
`mlcflow` 1.4.0 and the wheel-payload change in `mlperf-automations`
(`mlc-scripts`).

Legend: **PASS** = behaves as designed · **FAIL** = defect found ·
**N/T** = not tested (reason given) · **NOTE** = observation, not a defect.

Environments used (all under the QA scratch dir):

| Name | mlcflow | mlc-scripts | Notes |
|---|---|---|---|
| `venvBare` | editable checkout | absent | exercises the "no package" branches |
| `venvA` | editable checkout | wheel 1.1.0 | primary packaged env |
| `venvB` | editable checkout | wheel 1.1.0 | second env, for sharing tests |
| `venvS` | editable checkout | wheel 1.1.0 | site-packages path **contains a space** |
| `venvC` | **wheel** (non-editable) | wheel 1.1.0 | the only realistic end-user layout |

`venvC` is the important one: with an editable mlcflow, `automation/` never
lands in site-packages, which hides the most severe defect below. Any future
test pass **must** include a non-editable mlcflow install.

---

## 1. Root resolution

Risk: two independent resolution chains with a deliberate asymmetry (an
explicit `MLC_REPOS` also sets the cache root, but the *auto* repo root never
does). Getting this wrong silently relocates every cached dataset.

| # | Case | Expected | Result |
|---|---|---|---|
| 1.1 | no vars, no package | both roots = `~/MLC/repos` | **PASS** |
| 1.2 | `MLC_REPOS` only, no package | both roots = `$MLC_REPOS` (back-compat rule) | **PASS** |
| 1.3 | `MLC_CACHE` only, no package | cache = `$MLC_CACHE`, repo = `~/MLC/repos` | **PASS** |
| 1.4 | both set, no package | independent | **PASS** |
| 1.5 | no vars, package installed | cache = `~/MLC/repos`, repo = `~/MLC/envs/<12hex>` | **PASS** |
| 1.6 | `MLC_REPOS` set, package installed | `MLC_REPOS` wins for repo root, and also sets cache root | **PASS** |
| 1.7 | `MLC_CACHE` only, package installed | cache = `$MLC_CACHE`, repo = `~/MLC/envs/<hash>` | **PASS** |
| 1.8 | empty-string / whitespace-only env vars | treated as unset (`.strip()`) | **PASS** |
| 1.9 | relative `MLC_REPOS` | resolved to abspath once, at `Action.__init__` | **PASS** |
| 1.10 | `~`-prefixed `MLC_CACHE` | expanded | **PASS** |
| 1.11 | env hash is stable & distinct per venv | sha256(site-packages)[:12] | **PASS** — 3 venvs → 3 distinct dirs |
| 1.12 | venv whose path contains a space | works | **PASS** |
| 1.13 | `mlc-scripts` present but `meta.yaml` missing | should keep the env root | **FAIL** — silently falls back to `~/MLC/repos` (D5) |

**NOTE:** `mlc/action.py:1146-1148` constructs a module-level `Action()`, so
merely `import mlc` now does `os.makedirs(repos_path)` and creates
`$MLC_CACHE/local/{meta.yaml,cache}`. A typo'd `MLC_CACHE` silently
materialises a directory tree in `$HOME`. `os.makedirs(self.repos_path)` is
new in this change; the local-repo creation is not.

## 2. `local` repo placement, uid stability, cache destination

Risk: this is the mechanism that makes caches shared. It is driven by a
registry lookup (`self.local_repo` = the registered repo whose alias is
`local`), not by `self.cache_path`, so the two can disagree.

| # | Case | Expected | Result |
|---|---|---|---|
| 2.1 | first run: `local` created under cache root, registered into `$MLC_REPOS/repos.json` | yes | **PASS** |
| 2.2 | `local` never created under the repo root | yes | **PASS** (repo root has only `repos.json`/`index_*.json`) |
| 2.3 | two envs, same `MLC_CACHE` → same `local` uid | yes | **PASS** |
| 2.4 | cache entries land under `$MLC_CACHE/local/cache` | yes | **PASS** |
| 2.5 | **changing `MLC_CACHE` after the first run** | new cache root takes effect | **FAIL — D2 (High)** |
| 2.6 | single-root user adds `MLC_CACHE` | caches move to the new root | **FAIL — same as D2** |

## 3. Package discovery and registration

| # | Case | Expected | Result |
|---|---|---|---|
| 3.1 | packaged repo auto-registered on every command | yes | **PASS** |
| 3.2 | registered **in place**, nothing copied | yes | **PASS** |
| 3.3 | read-only site-packages (`chmod -R a-w`) | run succeeds | **PASS** |
| 3.4 | `pip uninstall mlc-scripts` → registry self-heals | stale entry dropped | **PASS** (editable mlcflow only; see D1) |
| 3.5 | re-install after uninstall | re-registered | **PASS** |
| 3.6 | package `meta.yaml` corrupt YAML | warn, skip registration | **PASS** (message is misleading — says "has no uid") |
| 3.7 | package `meta.yaml` has no `uid` | warn, skip registration | **PASS** |
| 3.8 | package `meta.yaml` deleted | warn, skip | **FAIL — D5**, also flips the repo root |
| 3.9 | `mlc rm repo` on the packaged repo | should be removable, or refuse with a reason | **FAIL — D6** (unregisters, then silently returns next command) |

## 4. uid collision and the shadow announcement

| # | Case | Expected | Result |
|---|---|---|---|
| 4.1 | `mlc add repo` of a same-uid checkout | explicit copy wins, package unregistered | **PASS** |
| 4.2 | `mlc pull repo mlcommons@mlperf-automations` on a packaged install | explicit clone wins | **PASS** |
| 4.3 | announcement printed on **every** subsequent run | yes | **PASS** (3/3 runs) |
| 4.4 | announcement names both winner and loser + version | yes | **PASS** |
| 4.5 | auto-pull carve-out passes `ignore_on_conflict` | yes | **PASS** (unit test `tests/test_script_action_apptainer.py`) |
| 4.6 | auto-pull cannot displace a registered same-uid repo, end-to-end | — | **N/T** — requires forcing the "no content repo" branch while a same-uid repo is registered; the two conditions are mutually exclusive in practice |

**NOTE:** the log line emitted while unregistering the shadowed copy reads
`Path: <site-packages>/mlc_scripts has been removed.` (`repo_action.py:1089`).
Nothing was deleted — it means "removed from repos.json". Alarming wording now
that the path points into site-packages.

## 5. Two environments sharing one cache

| # | Case | Expected | Result |
|---|---|---|---|
| 5.1 | distinct repo roots per venv | yes | **PASS** |
| 5.2 | one shared cache root | yes | **PASS** |
| 5.3 | one shared `local` uid | yes | **PASS** |
| 5.4 | alternating A→B→A→B→S→A produces no "Detected deleted item" storm | yes | **PASS** — index files are per repo root, so the two registries never fight |
| 5.5 | cache created in B is reused in A | yes (when 2.5 does not interfere) | **PASS** |

## 6. Non-git `pull` / `rm` / `add`

| # | Case | Expected | Result |
|---|---|---|---|
| 6.1 | `mlc add repo <plain dir>` records `git: false` | yes | **PASS** |
| 6.2 | `mlc add repo` on a real checkout records `git: true` | yes | **PASS** (`has_git_dir`) |
| 6.3 | `is_git_repo` honours `git:` in meta.yaml over disk state | yes | **PASS** |
| 6.4 | `mlc pull repo` on a registered non-git repo **whose folder is `$MLC_REPOS/<name>`** | friendly refusal | **PASS** |
| 6.5 | `mlc pull repo <alias>` where alias ≠ folder name | should refuse | **FAIL — D4** (tries `git clone <alias>`) |
| 6.6 | `mlc pull repo mlcommons@mlperf-automations` on a packaged install | should refuse or explain | **FAIL — D4** (clones a whole second copy from GitHub) |
| 6.7 | `mlc rm repo` non-git, declined | unregister only, folder kept | **PASS** |
| 6.8 | `mlc rm repo -f` non-git | folder deleted + unregistered | **PASS** |
| 6.9 | `mlc pull repo` (no args) skips non-git repos | yes | **PASS** — but uses a raw `.git` existence test, not `utils.is_git_repo()` (D8) |

## 7. Index correctness

| # | Case | Expected | Result |
|---|---|---|---|
| 7.1 | prefix-match fix: repos `pfx` and `pfx1`, remove `pfx` | `pfx1` entries survive in both `index_*.json` and `modified_times.json` | **PASS** |
| 7.2 | `mlc find script` still resolves `pfx1` afterwards | yes | **PASS** |
| 7.3 | index files live under the repo root, not the cache root | yes | **PASS** |
| 7.4 | full index build over 371 packaged scripts | ~2 s | **PASS** (1.8 s) |

**NOTE (pre-existing, out of scope):** `Index.build_index(force_rebuild=True)`
only clears `self.indices` when an index *file* is missing, so `mlc reindex`
does not drop entries whose folder is no longer inside any registered repo.
Observed while investigating D7.

## 8. `mlc list repo` output

| # | Case | Expected | Result |
|---|---|---|---|
| 8.1 | prints active `MLC_REPOS` and `MLC_CACHE` | yes | **PASS** |
| 8.2 | `(set by MLC_REPOS)` annotation | yes | **PASS** |
| 8.3 | `(auto: mlc-scripts <ver> at <path>)` annotation | yes | **PASS** |
| 8.4 | `(default)` annotation | yes | **PASS** |
| 8.5 | reported `MLC_CACHE` matches where caches actually go | yes | **FAIL — D2**: prints the new root while writing to the old one |

## 9. Docker / Apptainer context paths

| # | Case | Expected | Result |
|---|---|---|---|
| 9.1 | `mlcd detect,os` build context under `$MLC_CACHE/local/docker/<name>` | yes | **PASS** |
| 9.2 | no stray `local/` under the repo root | yes | **PASS** |
| 9.3 | apptainer context under `$MLC_CACHE/local/apptainer/` | — | **N/T** — apptainer not installed on this host; code path is identical to 9.1 |

## 10. `remote_run`

| # | Case | Expected | Result |
|---|---|---|---|
| 10.1 | uses the resolved `repos_path` rather than hardcoded `~/MLC/repos` | yes | **PASS** (static) |
| 10.2 | `remote_copy_mlc_repos=True` copies script content to the remote | — | **FAIL (static) — D9**: on a packaged install the repo root holds no repo directories, so nothing is copied |
| 10.3 | remote registration loop | — | **N/T** — no SSH target available |

## 11. Wheel contents / install

| # | Case | Expected | Result |
|---|---|---|---|
| 11.1 | ships `mlc_scripts/meta.yaml` with `git: false` | yes | **PASS** |
| 11.2 | ships `mlc_scripts/script/` — 371 script dirs | yes | **PASS** |
| 11.3 | no `by-category/` | yes | **PASS** |
| 11.4 | no symlink entries, no `__pycache__` | yes | **PASS** |
| 11.5 | `.mlc-provenance.json` with version/commit/source | yes | **PASS** |
| 11.6 | executable bits preserved (25 files) | yes | **PASS** (`0o775` in the zip and after install) |
| 11.7 | `Requires-Dist: mlcflow >=1.4.0` | yes | **PASS** |
| 11.8 | `pip install` runs no clone, needs no git/network | yes | **PASS** |
| 11.9 | **wheel ships only `mlc_scripts`** | yes | **FAIL — D1 (Critical)**: also ships a top-level `automation` package |
| 11.10 | build does not depend on untracked files | yes | **FAIL — D10**: `mlc_scripts/__init__.py` is untracked. Rebuilt without it: payload still ships and discovery still works, but `top_level.txt` becomes just `automation` |
| 11.11 | plain `pip install mlc-scripts` (deps resolved normally) leaves a working engine | yes | **FAIL — D1**: `bundled_automation_path()` then resolves to mperf-automations' engine copy |

## 12. Backwards compatibility — existing single-root user

Simulated a pre-1.4.0 layout (`repos.json`, `local/meta.yaml`,
`local/cache/get-legacy_1234abcd/mlc-cached-state.json`, `index_*.json`,
`modified_times.json`) and ran with `MLC_REPOS` only.

| # | Case | Expected | Result |
|---|---|---|---|
| 12.1 | existing cache entry still found by `mlc find cache` | yes | **PASS** |
| 12.2 | nothing moved, no new directories | yes | **PASS** |
| 12.3 | `repos.json` untouched | yes | **PASS** |
| 12.4 | `mlc list repo` reports cache root == repo root | yes | **PASS** |
| 12.5 | the same user later sets `MLC_CACHE` | caches move | **FAIL — D2** |
| 12.6 | real `~/MLC/repos` unaffected by a read-only command | yes | **PASS** (mtime unchanged) |

## 13. Regression suites

| # | Case | Result |
|---|---|---|
| 13.1 | `python3 -m pytest tests/ .github/scripts/ -q` | 58 passed, 4 failed — all 4 are `.github/scripts/test_mlc_access.py` tests that CI pre-seeds with `mlc pull repo` steps; with those pulls performed the file gives 14 passed / 1 failed, the remaining one (`test_find_repo`) being an ordering artefact of running the whole file after both forks are pulled. **No regression attributable to this change.** |
| 13.2 | `tests/test_script_action_apptainer.py` (`ignore_on_conflict` contract) | **PASS** |

## 14. Adversarial / miscellaneous

| # | Case | Expected | Result |
|---|---|---|---|
| 14.1 | 24 concurrent `mlc list repo` against a fresh root, 6 trials | `repos.json` intact | **PASS** (0 bad trials) — but see D8: `_rewrite_repos_json` is an unlocked read-modify-write while every index file uses `filelock` |
| 14.2 | `mlc add script <name>` destination | the shared local repo | **FAIL — D3 (High)**: writes into site-packages |
| 14.3 | `mlc cp script <src> local:<name>` | `$MLC_CACHE/local/script/<name>` | **FAIL — D7**: writes to `$MLC_REPOS/local/script/<name>`, outside any registered repo |
| 14.4 | `mlc find cache` after switching repo root, same cache root | finds it | **PASS** |
| 14.5 | `mlc find script` for authored work after switching repo root | finds it | **FAIL — D7** |
| 14.6 | `mlc pull repo` with no arguments | pulls every git repo, skips the rest | **PASS** |
| 14.7 | `mlc reindex` | — | **NOTE** under §7 |

---

## Defect index

Status column added by the **round-2 verification pass** (see §15 onwards).

| ID | Severity | One-line | Round-2 status |
|---|---|---|---|
| D1 | **Critical** | `mlc-scripts` wheel ships a top-level `automation` package that overwrites mlcflow's bundled engine; uninstalling it breaks mlcflow | **VERIFIED FIXED** |
| D2 | **High** | `MLC_CACHE` is only honoured on the first run for a given repo root | **PARTIAL** — fixed for one registered `local`; reopens as N2/N3 |
| D3 | **High** | `mlc add script` writes into site-packages | **VERIFIED FIXED** |
| D4 | **Medium** | `pull_repo`'s non-git guard is unreachable for the packaged repo | **VERIFIED FIXED** |
| D5 | **Medium** | A package with a missing `meta.yaml` silently flips the repo root to `~/MLC/repos` | **PARTIAL** — root no longer flips; warning-distinction sub-fix is dead code (N6) |
| D6 | **Medium** | The packaged repo cannot be removed — `mlc rm repo` is undone by the next command | **STILL BROKEN** (a *different* D6 — the `resolve_repos_path` docstring — was fixed instead; that part verified) |
| D7 | **Medium** | `<repo>:<name>` destinations resolve against `MLC_REPOS`, so `local:` lands outside the real local repo | **VERIFIED FIXED** (with N1 caveat) |
| D8 | **Low** | `repos.json` writes are unlocked; `pull` (no args) bypasses `utils.is_git_repo()` | **PARTIAL** — locking + `is_git_repo` verified; lock failure mode is fatal (N4) |
| D9 | **Low/Unverified** | `remote_copy_mlc_repos` copies nothing on a packaged install | **PARTIAL** — `True` form fixed; explicit-alias and empty-registry forms still copy nothing silently (N8) |
| D10 | **Low** | The wheel build depends on an untracked `mlc_scripts/__init__.py` (cosmetic — discovery works without it) | **VERIFIED FIXED** (by git-tracking the file; the `build_py` fallback is dead code — N9) |

## Directories created outside the scratch dir during this run

`~/MLC/envs/` (from the deliberate auto-resolution tests). Safe to delete:

- `518c9787f718` (venvB) — created by this QA run
- `be33943c3d61` (venvS) — created by this QA run
- `9068a9e0e7d4` (venvD) — created by this QA run
- `939642a0024b` (venvA) — pre-existing before this QA run

`~/MLC/repos/` was not modified (`repos.json` mtime unchanged).

---
---

# Round 2 — verification pass after the fixes

Ran 2026-08-10 against the current working trees of `mlcflow` and
`mlcommons@mlperf-automations`. Both wheels **rebuilt from the current source**
before any non-editable test.

Environments (all fresh, under the QA scratch dir):

| Name | mlcflow | mlc-scripts | Purpose |
|---|---|---|---|
| `venvPK` | **wheel** (non-editable) | wheel 1.1.0 | the realistic end-user layout; primary env for round 2 |
| `venvED2` | editable checkout | wheel 1.1.0 | second env for the sharing/isolation tests |
| `venvBare2` | editable checkout | absent | "no package" branches |
| `venvDEP` | resolved as a dependency | `pip install mlc-scripts` | 11.11 — plain dependency-resolved install |

`~/MLC/repos/repos.json` was verified byte-correct at the start of the run.
It was **corrupted once during the run** (by the pytest suite, not by mlcflow —
see N7) and restored by hand to exactly the two required entries; verified
correct again at the end. No new `~/MLC/envs/<hash>` directories were created:
the four listed above are still the only ones, and the auto-resolution checks
were done by calling `resolve_repos_path()` directly rather than by running a
command.

## 15. D1–D10 re-verification

### D1 — wheel payload / engine clobber — **VERIFIED FIXED**

| Check | Result |
|---|---|
| `mlc_scripts-1.1.0.dist-info/top_level.txt` | `mlc_scripts` alone |
| top-level dirs in the wheel | `mlc_scripts`, `mlc_scripts-1.1.0.dist-info` only — no `automation/` |
| entries / script dirs | 2042 entries, 371 script dirs, no `by-category/`, no `__pycache__` |
| `meta.yaml` in the wheel | `git: false` |
| `.mlc-provenance.json` | version 1.1.0, commit `bee7550…`, source URL |
| RECORD overlap between `mlcflow` and `mlc_scripts` (venvDEP) | **0 paths** |
| which RECORD claims `automation/script/module.py` | `mlcflow-1.4.0.dist-info` only |
| `pip uninstall mlc-scripts` then `mlc --version` / `mlc list repo` | engine file survives, commands work (venvPK **and** venvDEP) |
| 11.11 — `pip install mlc-scripts` with deps resolved normally, then `mlcr detect,os` | **PASS** |

### D2 — `MLC_CACHE` honoured after the first run — **PARTIAL**

| # | Case | Result |
|---|---|---|
| 15.2a | run with `MLC_CACHE=C1`, then switch to `C2` | **PASS** — logs *"Local repo moved to …C2/local; unregistering the previous one at …C1/local"*, `repos.json` re-pointed, new cache lands in `C2` |
| 15.2b | switch back to `C1` | **PASS** — `mlc find cache` resolves the original `C1` entry again |
| 15.2c | `MLC_CACHE` set and the registered local is **already** the right one | **PASS** — `repos.json` content **and mtime** unchanged (no gratuitous rewrite) |
| 15.2d | `MLC_CACHE` unset, a local registered elsewhere | **PASS** — left alone (back-compat), `Keeping the registered local repo at …` |
| 15.2e | §12.5 single-root user later sets `MLC_CACHE` | **PASS** — caches move |
| 15.2f | §8.5 `mlc list repo` reports where caches actually go | **FAIL in the back-compat branch — N3** |
| 15.2g | a *second* `local` also registered | **FAIL — N2** |
| 15.2h | the first run after switching `MLC_CACHE` | **NOTE** — the old root's cache entries are still in `index_cache.json` (nothing calls `Index.remove_repo_from_index()` when the stale local is unregistered), so that run silently *reuses* a cache entry under the old root. Self-heals on a later run once the entry disappears. Low. |

### D3 — `mlc add script` destination — **VERIFIED FIXED**

`mlc add script my-new-script` → `$MLC_CACHE/local/script/my-new-script`.
Nothing new appears under `site-packages/mlc_scripts/script/`.
`mlc add script local:x` and `mlc add script mlc_scripts:x` both still honour
the explicit repo. `mlc add script mlcommons@mlperf-automations:x` crashes —
see **N1**.

### D4 — `pull` guard — **VERIFIED FIXED**

| # | Case | Result |
|---|---|---|
| 15.4a | `mlc pull repo plaindir` (registered non-git, folder == alias) | **PASS** — friendly refusal |
| 15.4b | `mlc pull repo myalias` (alias ≠ folder name) | **PASS** — friendly refusal naming the real path |
| 15.4c | `mlc pull repo fakegit` — folder has a `.git` dir but `git: false` in `meta.yaml` | **PASS** — declaration wins, refused |
| 15.4d | `mlc pull repo mlcommons@mlperf-automations` on a packaged install | **PASS (by design)** — clones into `$MLC_REPOS`, the uid rule then displaces the packaged copy and the shadow line is printed on every later run |
| 15.4e | `mlc pull repo` with no args | **PASS** — non-git repos skipped via `utils.is_git_repo()` |
| 15.4f | `mlcp <unregistered non-clonable name>` | **NOTE** — still falls through to `git clone <name>` and surfaces git's raw `repository does not exist`. Pre-existing, cosmetic. |

### D5 — damaged package meta — **PARTIAL**

| # | Case | Result |
|---|---|---|
| 15.5a | `mlc_scripts/meta.yaml` deleted, `MLC_REPOS` unset | **PASS** — `resolve_repos_path()` still returns `~/MLC/envs/aa58d2dbb8e9`; the root no longer flips to `~/MLC/repos` |
| 15.5b | warning text for a missing meta | **PASS** — *"has no meta.yaml at …, so it cannot be registered … `pip install --force-reinstall mlc-scripts`"* |
| 15.5c | **unparseable** `meta.yaml` | **FAIL — N6** — still reports *"has no uid"*; the new "Could not parse" branch is unreachable |
| 15.5d | valid meta with no `uid` | **PASS** |

### D6 — two different defects

* **As filed** (§3.9, "the packaged repo cannot be removed") — **STILL BROKEN.**
  `mlc rm repo mlcommons@mlperf-automations` unregisters it and prints
  *"Path: …/site-packages/mlc_scripts has been removed."*; `repos.json` drops to
  one entry; the **very next command** re-registers it
  (`Registered mlc-scripts 1.1.0 from …`) with no explanation. Nothing was
  changed to address this.
* **The docstring** (`resolve_repos_path`) — **VERIFIED FIXED.** The text now
  says an explicit `MLC_REPOS` still gets the packaged repo registered into it
  and that the uid rule is what yields "my checkout and nothing else". Both
  halves confirmed empirically: with `MLC_REPOS` set the package *is*
  registered (15.4d, §12), and `mlc add repo`/`mlc pull repo` of a same-uid
  checkout *does* displace it (15.4d, 15.9).

### D7 — `<repo>:` destinations — **VERIFIED FIXED**

`mlc cp script detect-os local:copied-detect-os` →
`$MLC_CACHE/local/script/copied-detect-os`. No phantom `$MLC_REPOS/local`
is created, and `mlc find script copied-detect-os` resolves it afterwards.
Caveat: destination repos are still matched by **folder basename** — see N1.

### D8 — `repos.json` locking — **PARTIAL**

| # | Case | Result |
|---|---|---|
| 15.8a | 24 concurrent `mlc list repo` against a fresh root × 4 trials | **PASS** — 0 bad trials, `repos.json` always exactly 2 entries |
| 15.8b | `pull` (no args) uses `utils.is_git_repo()` | **PASS** |
| 15.8c | read-only `MLC_REPOS`, everything already registered | **PASS** — no write attempted, command succeeds |
| 15.8d | read-only `MLC_REPOS`, registration needed | **FAIL — N4** — uncaught `PermissionError` from creating `repos.json.lock` |

### D9 — `remote_copy_mlc_repos` — **PARTIAL**

Exercised by executing the real source block from `remote_run.py` against
stubbed `self_module.action_object` values (no SSH target available).

| Input | `files_to_copy` |
|---|---|
| `True`, packaged install | `[…/cache/local, …/site-packages/mlc_scripts]` — **fixed** |
| `['mlc_scripts']` (basename) | the packaged repo — works |
| `['mlcommons@mlperf-automations']` (the **alias**, the name users know) | **`None` — nothing copied, silently** |
| `action_object.repos` empty | **`None` — nothing copied, silently** |

See **N8**.

### D10 — untracked `mlc_scripts/__init__.py` — **VERIFIED FIXED**

`git ls-files mlc_scripts/` returns `mlc_scripts/__init__.py` (staged add).
`top_level.txt` is `mlc_scripts`; the sdist (4660 entries) contains both
`mlc_scripts/__init__.py` and `script/`. The *fallback* in `build_py` does not
actually work — see **N9**.

## 16. The lazy `default_parent` change

| # | Case | Result |
|---|---|---|
| 16.1 | `import mlc` creates nothing (`$MLC_REPOS`/`$MLC_CACHE` both point at non-existent dirs) | **PASS** — neither directory exists afterwards |
| 16.2 | same for `mlc.main`, `mlc.action`, `mlc.cfg_action`, `mlc.experiment_action`, `mlc.repo_action`, `mlc.script_action`, `mlc.cache_action`, `mlc.action_factory` | **PASS** — all 8 clean |
| 16.3 | no remaining import-time construction anywhere | **PASS** — `grep -rn default_parent` shows only `action.py`'s lazy accessor and `get_default_parent()` call sites in `main.py` (×4) and `cfg_action.py` (×1); `experiment_action.py`'s stale import removed and it never used it |
| 16.4 | `mlc --version` | **PASS** — prints `mlcflow 1.4.0`; deliberately never builds an `Action` |
| 16.5 | `mlc list repo`, `mlc list cache`, `mlc reindex`, `mlc find script/cache/repo`, `mlc show cache`, `mlc add/rm/cp/mv script`, `mlc add/rm repo`, `mlc rm cache` | **PASS** — all exercised on venvPK |
| 16.6 | `mlcr`, `mlct`, `mlcd`, `mlcp` | **PASS** |
| 16.7 | `mlc` with no args / `mlc --help` / `mlc <target>` help path (`get_action(..., get_default_parent())`) | **PASS** |
| 16.8 | `mlc.access({...})` for `find`/`run`/`list`, and `from mlc.action import access` | **PASS**; `get_default_parent() is get_default_parent()` → `True` (single shared instance, as before) |
| 16.9 | `CfgAction()` with no parent | **PASS** |
| 16.10 | error reporting when `Action.__init__` itself fails | **FAIL — N5** (double fault) |

**Pre-existing, unrelated to this change:** the documented
`Action().access({...})` form in `.claude/skill.md` raises
`AttributeError: 'Action' object has no attribute 'parent'`
(`mlc/action.py:193`). Identical line exists at `HEAD`, so not a regression.

## 17. Regression re-runs

| # | Case | Result |
|---|---|---|
| 17.1 | §5 two-venv isolation — `venvPK` + `venvED2`, distinct `MLC_REPOS`, one shared `MLC_CACHE`, alternating A→B→A→B→A | **PASS** — one shared `local` uid, exactly one cache entry reused by both, **0** "Detected deleted item" lines in all five runs |
| 17.2 | §6.7 `mlc rm repo` non-git, declined | **PASS** — folder kept, unregistered only |
| 17.3 | §6.8 `mlc rm repo -f` non-git | **PASS** — folder deleted and unregistered |
| 17.4 | §4.1 `mlc add repo` of a same-uid checkout | **PASS** — checkout wins, package unregistered, shadow line printed |
| 17.5 | §4.3 shadow announcement on every subsequent run | **PASS** — 3/3 |
| 17.6 | §9.1 `mlcd detect,os` build context | **PASS** in the normal case — `$MLC_CACHE/local/docker/detect-os_86373`, no stray `local/` under the repo root. **FAIL in the divergent back-compat state — N3** |
| 17.7 | §12 back-compat, `MLC_REPOS` only, pre-1.4.0 layout | **PASS** — legacy cache entry found, cache root == repo root, `local` entry untouched (`repos.json` gains only the packaged repo, by design) |
| 17.8 | §7.1 index prefix-match | **PASS** (unit-covered; `belongs_to_repo()` uses `path == repo_path or startswith(repo_path + os.sep)`) |
| 17.9 | `env -u MLC_REPOS -u MLC_CACHE python3 -m pytest tests/ .github/scripts/ -q` | **61 passed, 1 failed.** The single failure is `.github/scripts/test_mlc_access.py::test_find_repo`, which needs `anandhu-eng@mlperf-automations` pre-pulled by CI. **No regression.** ⚠ this invocation *wrote to the developer's real `~/MLC/repos`* — see N7. |
| 17.10 | same suite with `MLC_REPOS`/`MLC_CACHE` pinned to scratch | **58 passed, 4 failed** — the same 4 `test_mlc_access.py` tests the round-1 report described (`test_find_repo`, `test_cp_script`, `test_add_script`, `test_mv_script`), all needing CI-pulled content. Byte-identical outcome to round 1. |
| 17.11 | `tests/` alone, vars unset | **36 passed**, real `repos.json` untouched — the three pinned modules behave |

## 18. NEW defects introduced by / surviving the fixes

### N2 — **High** — `MLC_CACHE` is still ignored when a second `local` is registered

`Action._ensure_local_registered()` (`mlc/action.py:474-476`) returns as soon as
*a* repo aliased `local` matches the cache root, without checking whether other
stale `local` entries are also registered. Reproduced with supported commands
only:

1. `MLC_REPOS=R MLC_CACHE=OLD mlc list repo` → registers `OLD/local`.
2. `mlc add repo NEW/local` (a folder whose `meta.yaml` says `alias: local`) → appended after it.
3. `MLC_REPOS=R MLC_CACHE=NEW mlcr detect,os`.

**Expected:** the cache entry lands in `NEW/local/cache`.
**Actual:** it lands in `OLD/local/cache`. `mlc list repo` prints
`MLC_CACHE: …/NEW`. The two derived values disagree:
`self.local_cache_path` takes the **first** `alias == 'local'` repo
(`mlc/action.py:420-423`, → `OLD`) while `self.local_repo` is set from the
**last** one seen in `load_repos_and_meta()` (`mlc/action.py:326-327`, → `NEW`'s
uid) — precisely the split the D2 fix's own comment says it exists to prevent.
The same shape occurs with a hand-edited `repos.json` and is what the new
`remote_run` registration loop will produce on a remote (N8).

### N3 — **Medium** — `cache_path` is not derived from the registered local, so the back-compat branch lies and writes outside it

When the registry already holds a `local` elsewhere and `MLC_CACHE` is unset,
`_ensure_local_registered()` correctly leaves it alone — but `self.cache_path`
keeps the *computed* value. Repro: run once with `MLC_REPOS=R MLC_CACHE=C`,
then run again with `MLC_CACHE` unset and the same `MLC_REPOS`.

**Expected:** everything reports and uses `C/local`, the registered local.
**Actual:**

* `mlc list repo` prints `MLC_CACHE: R` while listing `C/local` as the local
  repo two lines further down, and `mlcr` really does write its cache to
  `C/local/cache` — the §8.5 misreport, unchanged, in a different branch
  (`mlc/repo_action.py:957`).
* `mlcd detect,os` puts the build context in **`R/local/docker/`** — an
  unregistered directory outside every registered repo — because
  `automation/script/docker_utils.py:203-206` (and `apptainer.py:488-491`) read
  `mlc.cache_path`, not the registered local. This is the exact "stray `local/`
  with no `meta.yaml` beside every registry" the new comment there claims to
  prevent.
* `Action.__init__` creates `R/local/` and writes a `meta.yaml` with a freshly
  minted uid on **every** such run (`mlc/action.py:392-401`) before deciding not
  to register it — a permanent orphan repo with a wasted uid.

### N4 — **Medium** — `_repos_json_lock()` only survives `Timeout`, so a read-only repo root kills every command

`mlc/action.py:436-445` catches `filelock.Timeout` and falls back to running
unlocked, but a `PermissionError`/`OSError` from *creating* `repos.json.lock`
propagates. With `MLC_REPOS` on a read-only or root-owned directory (a
site-wide shared root, a read-only container mount) and the packaged repo not
yet registered:

**Expected:** a clean `{'return': 1, 'error': …}` or the documented unlocked
fallback.
**Actual:** `PermissionError: [Errno 13] Permission denied: …/repos.json.lock`
as a raw traceback from `mlc/action.py:438`; `mlc list repo` exits 1 with 20+
lines of traceback, `mlcr` with 80 (see N5).

### N5 — **Medium** — error reporting double-faults when `Action.__init__` is what failed

`main.py:190` calls `_get_repo_hashes()`, which at `main.py:101` now does
`get_default_parent().repos`. The old code guarded this with
`if default_parent is None: return []`; the lazy change removed the guard, so
`_report_error` now *constructs* the `Action` it is reporting about.

**Expected:** the formatted error report (error line, source location, version,
rerun hint).
**Actual:** with any `Action.__init__` failure (N4 is an easy trigger) the
report is cut off after the version line and Python prints
`During handling of the above exception, another exception occurred` plus a
second full traceback — 80 lines of stderr where 6 were intended. Exit code is
still 1.

### N1 — **Medium** — `cp`/`add script` destinations are matched by folder basename, not by repo alias

`Action.cp()` (`mlc/action.py:974-983`) resolves `<repo>:<name>` with
`os.path.basename(repodata.path) == target_repo_name`. Until this feature every
repo lived at `$MLC_REPOS/<alias>`, so basename and alias agreed. The packaged
repo breaks that: its alias is `mlcommons@mlperf-automations`, its basename is
`mlc_scripts`.

**What I did:** `mlc cp script detect-os mlcommons@mlperf-automations:alias-test`
and `mlc add script mlcommons@mlperf-automations:explicit-script`.
**Expected:** either the copy, or a clean "not registered" error.
**Actual:** `UnboundLocalError: cannot access local variable 'target_repo'` from
`mlc/action.py:977` — the error f-string interpolates `target_repo` before it is
assigned. The same crash fires for any unregistered name
(`mlc cp script detect-os nosuchrepo:x`). `mlc_scripts:alias-test` works, so the
only spelling that succeeds is the site-packages folder name.

The `target_repo is None` guard the D7 fix added at `mlc/action.py:980-982` is
unreachable for this branch — the older `any(basename == …)` check returns
first. The broken f-string exists at `HEAD` too, but it was previously
unreachable in practice; this feature makes alias ≠ basename normal. The same
alias-vs-basename mismatch also breaks `remote_copy_mlc_repos` (N8).

### N6 — **Low** — the "unparseable meta.yaml" warning branch is dead code

`_sync_package_repo()` (`mlc/action.py:541-546`) wraps `utils.read_yaml()` in
`try/except` to distinguish an unparseable meta from a missing one, but
`utils.read_yaml()` (`mlc/utils.py:~120`) catches the `YAMLError` itself and
returns `None`. A corrupt package `meta.yaml` therefore still produces
*"…/meta.yaml has no uid"* — the misleading message §3.6 complained about. The
`except` clause can never run.

### N7 — **Low** — the test-hygiene fix missed the one module that actually writes repos

`tests/test_action_invalid_meta_entries.py`, `tests/test_cache_mark_tmp.py` and
`.github/scripts/test_repo_pull_force.py` now pin both variables. But
`.github/scripts/test_mlc_access.py` calls `mlc.access(...)` throughout and pins
neither. Running the documented command
(`env -u MLC_REPOS -u MLC_CACHE python3 -m pytest tests/ .github/scripts/ -q`)
therefore operates on the developer's real root: it added
`/home/user/MLC/repos/my-new-repo` to `repos.json` and created the folder
(`test_add_repo` has no matching teardown). Restored by hand during this run.
It also leaves `local/script/moved-my-script-1` behind in the real local repo.

### N8 — **Low** — `remote_copy_mlc_repos` still copies nothing, silently, for the forms that matter

`automation/script/remote_run.py:181-215`:

* the `registered` map is keyed by **basename**, so the alias form
  `remote_copy_mlc_repos=['mlcommons@mlperf-automations']` misses, falls back to
  `$MLC_REPOS/mlcommons@mlperf-automations` (which does not exist on a packaged
  install) and copies nothing — the original D9 symptom, unfixed;
* an empty `action_object.repos` copies nothing;
* both cases are silent — no warning, the run proceeds and fails later on the
  remote;
* two registered repos sharing a basename collide in the dict and only one is
  copied;
* `True` now includes the `local` repo, i.e. the **entire cache** — correct per
  the old behaviour, but much more consequential now that `local` is the shared
  cache root;
* the new remote bootstrap `mlc add repo`s every copied directory, including the
  copied `local`. On a remote that already has its own `local`, that produces
  two `local`-aliased repos with the same uid — the N2 configuration.

### N9 — **Low / cosmetic** — the `build_py` "write `__init__.py` if missing" fallback is dead code

`setup.py`'s `BuildPyWithScriptContent.run()` writes `mlc_scripts/__init__.py`
when absent, but `packages=[PACKAGE_REPO_MODULE]` makes setuptools validate the
package directory during `egg_info`, before `build_py` runs. Building from a
tree without `mlc_scripts/` fails with
`error: package directory 'mlc_scripts' does not exist`. D10 is genuinely fixed
— by git-tracking the file — but the belt-and-braces half does not hold.

## 19. Round-2 directories created outside the scratch dir

**None.** `~/MLC/envs/` still contains only the four hashes listed above.
`~/MLC/repos/repos.json` was verified at the start, corrupted by the pytest run
in 17.9 (extra `my-new-repo` entry), restored by hand, and verified byte-correct
at the end:

```
[
  "/home/user/MLC/repos/local",
  "/home/user/MLC/repos/mlcommons@mlperf-automations"
]
```

`/home/user/MLC/repos/my-new-repo/` (created by that same test) was deleted.
`/home/user/MLC/repos/local/script/moved-my-script-1` was left in place — it may
predate this run.


---
---

# Round 3 — final verification pass

Ran 2026-08-10 against the current working trees of `mlcflow` and
`mlcommons@mlperf-automations`, after the fixes for N1–N6, N8, N9 and the D6
message. **Both wheels rebuilt from the current source** (`dist4/`) before any
non-editable test; the round-2 wheels were discarded.

Environments (all fresh, under the QA scratch dir `r3/`):

| Name | mlcflow | mlc-scripts | Purpose |
|---|---|---|---|
| `venvPK` | **wheel** (non-editable) | wheel 1.1.0 | primary end-user layout |
| `venvED` | editable checkout | wheel 1.1.0 | second env for sharing/isolation |
| `venvBARE` | editable checkout | absent | "no package" branches |
| `venvDEP3` | resolved as a dependency | `pip install mlc-scripts` | dependency-resolved install |
| `venvEDS` | wheel | **`pip install -e .`** | new this round — see N10 |

`/home/user/MLC/repos/repos.json` verified byte-correct at the start **and** at
the end; mtime unchanged throughout (`16:16:43`, i.e. before this run began).
No new `~/MLC/envs/<hash>` directories: the four from round 1 are still the only
ones. The documented unpinned pytest invocation was run with `HOME` redirected
to a scratch dir (see 20.9) so that N7, which is unfixed by design, could not
corrupt the real registry a second time.

## 20. N1–N9 and the D6 message

### N1 — `cp`/`add script` destination matching — **VERIFIED FIXED**

| Spelling | Result |
|---|---|
| `mlcommons@mlperf-automations:alias-test` (alias) | **PASS** — copied |
| `9cf241afa6074c89:uid-test` (uid) | **PASS** — copied |
| `mlc_scripts:basename-test` (folder basename) | **PASS** — copied |
| `nosuchrepo:x` | **PASS** — clean `The target repo nosuchrepo is not registered in MLC…`, no `UnboundLocalError` |
| `mlc add script mlcommons@mlperf-automations:explicit-script` | **PASS** |
| warning when the destination is the installed package | **PASS** — *"…belongs to the installed mlc-scripts. Anything written there is lost on the next upgrade or uninstall - use `local:` to keep it."* |

### N2 — `MLC_CACHE` ignored when a second `local` is registered — **VERIFIED FIXED**

Exact round-2 reproduction, supported commands only:

1. `MLC_REPOS=R MLC_CACHE=OLD mlc list repo` → registers `OLD/local`.
2. `mlc add repo NEW/local` (meta says `alias: local`) → appended, two locals registered.
3. `MLC_REPOS=R MLC_CACHE=NEW mlcr detect,os`.

**Result: PASS.** Logs *"Local repo is now …NEW/local; unregistering the previous
one at …OLD/local. Its contents are left on disk."*; `repos.json` ends with one
`local`; the cache entry lands in `NEW/local/cache` and `OLD/local/cache` stays
empty; `mlc list repo` reports `MLC_CACHE: …/NEW`.

| # | Case | Result |
|---|---|---|
| 20.2a | `MLC_CACHE` C1 → C2 | **PASS** — repointed, new cache in C2 |
| 20.2b | switch back C2 → C1 | **PASS** (covered by §12.5-style re-switch) |
| 20.2c | already correct — no gratuitous rewrite | **PASS** — content **and mtime** unchanged |
| 20.2d | hand-injected duplicate `local`, `MLC_CACHE` unset | **PASS** — first registered wins, the other is unregistered and announced, contents left on disk |
| 20.2e | de-dup on a `local` that still holds caches | **PASS (by design)** — announced at INFO, files untouched; the dropped repo's index entries are not purged, so its caches simply stop resolving (round-2 note 15.2h, unchanged, Low) |

### N3 — back-compat branch reported/wrote outside the registered local — **VERIFIED FIXED**

Repro: run with `MLC_REPOS=R2 MLC_CACHE=C`, then again with `MLC_CACHE` unset.

| Check | Round 2 | Round 3 |
|---|---|---|
| `mlc list repo` `MLC_CACHE:` line | `R2` (wrong) | **`C`** — matches the registered local |
| `mlcd detect,os` build context | `R2/local/docker/…` | **`C/local/docker/detect-os_86373`** |
| `R2/local/` created at all | yes | **no — `R2` holds only `repos.json` + index files** |
| throwaway `R2/local/meta.yaml` with a wasted uid | yes, every run | **none** (`find R2 -name meta.yaml` → empty) |

### N4 — `_repos_json_lock()` and a read-only repo root — **PARTIAL (defect still open)**

The filed cause is fixed: `except OSError` is present and the lock-creation
failure no longer propagates — the traceback now originates *past* the lock, at
`_rewrite_repos_json`. But the user-visible defect is unchanged, and the
refactor introduced a worse one (**N11**).

| # | Case | Result |
|---|---|---|
| 20.4a | read-only `MLC_REPOS`, everything already registered | **PASS** — no write attempted |
| 20.4b | read-only `MLC_REPOS` (fresh, no `repos.json`) | **FAIL** — raw `PermissionError` traceback from `action.py:393` |
| 20.4c | read-only `MLC_REPOS`, `repos.json` exists, package needs registering | **FAIL** — raw `PermissionError` from `_rewrite_repos_json` (`action.py:456`); the lock fallback fired correctly, the write did not |
| 20.4d | writable dir, **read-only `repos.json`** | **FAIL — N11**, the real error is replaced by `RuntimeError: generator didn't stop after throw()` |

### N5 — error reporting double fault — **VERIFIED FIXED**

`peek_default_parent()` returns `None` and `_get_repo_hashes()` returns `[]`, so
the error path no longer constructs the `Action` that just failed.

| Check | Round 2 | Round 3 |
|---|---|---|
| `mlcr` stderr on an `Action.__init__` failure | 80 lines, 2 tracebacks | **3 lines, 0 tracebacks** |
| `During handling of the above exception` | present | **absent** |
| exit code | 1 | 1 |

`mlc list repo` still shows a raw traceback for the same failure, because
`get_default_parent()` is called at `main.py:650`, outside the `try` that feeds
`_report_error`. Identical to `HEAD` behaviour (the old code built the `Action`
at import time), so not a regression — but the friendly report is only reached
through the `mlcr`/script path.

### N6 — the "unparseable meta.yaml" branch — **VERIFIED FIXED**

| Package `meta.yaml` state | Message |
|---|---|
| unparseable YAML | *"…is empty or not valid YAML, so the installed mlc-scripts cannot be registered. Reinstall it with `pip install --force-reinstall mlc-scripts`."* |
| empty file | same message |
| valid YAML, no `uid` | *"…has no uid. The installed mlc-scripts cannot be registered."* |
| file absent | *"The installed mlc-scripts has no meta.yaml at …"* |

All four distinguished. **D5's §3.6 complaint is closed.** The repo root also
still stays at `~/MLC/envs/<hash>` in every damaged case (D5 root-flip fix holds).

### N7 — `.github/scripts/test_mlc_access.py` unpinned — **NOT FIXED (agreed: correct call)**

Confirmed still unpinned, and confirmed it still writes to whatever root is
active: run with `HOME` redirected, the suite added `my-new-repo` to the scratch
`repos.json` with no teardown — the exact round-2 corruption pattern.

**I agree with leaving it as is for the release.** The module is CI
infrastructure whose fixtures are seeded by the workflow's own `mlc pull repo`
steps; pinning `MLC_REPOS`/`MLC_CACHE` inside the test file would point it at an
empty root and break the four tests CI currently relies on. It is a test-hygiene
issue in a file that only ever runs in CI, not a shipping defect. What it does
cost is developer safety: anyone running the documented
`env -u MLC_REPOS -u MLC_CACHE python3 -m pytest tests/ .github/scripts/ -q`
locally mutates their real registry. Worth a follow-up (a session-scoped
`conftest.py` fixture that pins both roots *and* performs the pre-pull, so CI
and local runs agree) — not a release blocker.

### N8 — `remote_copy_mlc_repos` — **VERIFIED FIXED**

Exercised by executing the real source block from `remote_run.py` (lines
180–239) against stubbed `self_module.action_object` values.

| Input | `files_to_copy` | Warning |
|---|---|---|
| `True`, packaged install (pkg + local registered) | `[site-packages/mlc_scripts]` — **`local` correctly skipped** | — |
| `['mlcommons@mlperf-automations']` (alias) | the packaged repo | — |
| `['mlc_scripts']` (basename) | the packaged repo | — |
| `['9cf241afa6074c89']` (uid) | the packaged repo | — |
| `['nosuchrepo']` | none | **both** warnings: per-name + "nothing matched" |
| `action_object.repos` empty | none | "nothing matched" |
| only `local` registered, `True` | none | "nothing matched" |
| explicit `['local']` | none | per-name + "nothing matched" |
| two repos sharing a basename, `True` | **both** copied (`values()`, not keys) | — |
| two repos sharing a basename, basename form | one (last registered) | — (see N13) |

The remote bootstrap now `mlc add repo`s each copied directory instead of
symlinking into `$MLC_REPOS`, and no longer copies `local`, so the N2
configuration can no longer be manufactured on the remote.

### N9 — `build_py` `__init__.py` fallback — **VERIFIED FIXED**

`grep -n "__init__" setup.py` → no matches; the dead branch is gone.
`git ls-files mlc_scripts/` → `mlc_scripts/__init__.py` (tracked).
The rebuilt wheel contains `mlc_scripts/__init__.py` and `top_level.txt` is
`mlc_scripts`.

### D6 (as filed) — the packaged repo cannot be removed — **VERIFIED ADDRESSED**

`mlc rm repo mlcommons@mlperf-automations` now prints, before removing:

> `…/site-packages/mlc_scripts belongs to the installed mlc-scripts and is
> re-registered at the start of every command. To stop using it,
> `pip uninstall mlc-scripts`, or pull a checkout of the same repo — an
> explicit `mlc pull repo` takes precedence over the packaged copy.`

Every claim in it verified this round: the repo *is* re-registered by the next
command (`Registered mlc-scripts 1.1.0 from …`); `pip uninstall mlc-scripts`
does stop it and leaves a working engine (20.11); and
`mlc pull repo mlcommons@mlperf-automations` does displace it by the uid rule,
with the shadow line printed on every later run. Accepted as the right
resolution — suppressing re-registration would break discovery, which runs every
command by design.

Residual cosmetics (pre-existing, unchanged): the warning is still followed by
`Repo mlc_scripts was not found in the repo folder.` and
`Path: …/site-packages/mlc_scripts has been removed.` — nothing was deleted.

## 21. Full regression sweep

| # | Area | Result |
|---|---|---|
| 21.1 | §1 root resolution, all 7 shapes × `venvPK`/`venvBARE` | **PASS** — identical to rounds 1–2; empty/whitespace treated as unset, relative resolved, `~` expanded |
| 21.2 | §1.11 env hash stable & distinct per venv | **PASS** — PK `a9eb19aa8fac`, ED `acf531c59481`, BARE → `~/MLC/repos`; hash is independent of `HOME` |
| 21.3 | §1.13 / D5 package with no `meta.yaml` keeps the env root | **PASS** |
| 21.4 | §2 cache destination + cache hits | **PASS** — `$MLC_CACHE/local/cache`, reused across roots |
| 21.5 | §3.3 read-only site-packages (`chmod -R a-w`) | **PASS** — `mlcr detect,os` rc=0 |
| 21.6 | §3.4/3.5 uninstall → registry self-heals → reinstall re-registers | **PASS** (`venvDEP3`) |
| 21.7 | §4 uid tie: `mlc add repo` of a same-uid checkout | **PASS** — checkout wins, package unregistered |
| 21.8 | §4.3/4.4 shadow announcement on every subsequent run | **PASS** — 3/3, names winner, loser and version |
| 21.9 | §5 two-venv isolation, one shared `MLC_CACHE`, A→B→A→B→A | **PASS** — distinct roots, one shared `local` uid `16097278af0e4ad1`, one cache entry reused, **0 "Detected deleted item" lines in all five runs** |
| 21.10 | §6.1/6.2 `git:` derived from disk on `mlc add repo` | **PASS** — plain dir `git: false`, real checkout `git: true` |
| 21.11 | §6.4/6.5 `mlc pull repo` on a registered non-git repo, folder == alias and alias ≠ folder | **PASS** — friendly refusal naming the real path |
| 21.12 | §6.x `.git` present but `git: false` declared | **PASS** — declaration wins, refused |
| 21.13 | §6.6 `mlc pull repo mlcommons@mlperf-automations` on a packaged install | **PASS (by design)** — clones, uid rule displaces the packaged copy |
| 21.14 | §6.7 `mlc rm repo` non-git, declined (repo under the root) | **PASS** — *"is not a git checkout, so uncommitted work cannot be detected"* → *"Folder kept. Unregistering …"*, folder survives |
| 21.15 | §6.8 `mlc rm repo --f` non-git | **PASS** — *"removing because force was requested"*, folder deleted |
| 21.16 | §6.9 `mlc pull repo` (no args) skips non-git via `utils.is_git_repo()` | **PASS** |
| 21.17 | §7.1/7.2 index prefix-match (`pfx` vs `pfx1`) | **PASS** — `pfx1` survives in `index_script.json` **and** `modified_times.json`, still resolvable |
| 21.18 | §7.3/7.4 index files under the repo root; full rebuild | **PASS** — 3.7 s over 371 scripts |
| 21.19 | §8 `mlc list repo` annotations | **PASS** — `(set by MLC_REPOS)`, `(auto: mlc-scripts 1.1.0 at …)`, `(default)`; §8.5 now correct in **both** branches |
| 21.20 | §9.1/9.2 docker build context | **PASS** — `$MLC_CACHE/local/docker/detect-os_86373`, no stray `local/` under the repo root |
| 21.21 | §11 wheel contents (rebuilt) | **PASS** — 2043 entries, 371 script dirs, top-level `mlc_scripts` only, no `by-category/`, no `__pycache__`, no symlinks, 25 exec-bit files, `git: false`, provenance `bee7550…`, `Requires-Dist: mlcflow>=1.4.0` |
| 21.22 | §11.9/11.11 D1 — RECORD overlap and engine survival | **PASS** — **0** overlapping paths, only `mlcflow` claims `automation/script/module.py`, `pip uninstall mlc-scripts` leaves `mlc --version` / `mlc list repo` working |
| 21.23 | §12 back-compat single-root user, `MLC_REPOS` only | **PASS** — legacy cache found, `MLC_CACHE == MLC_REPOS`, nothing moved, `repos.json` gains only the packaged repo |
| 21.24 | §12.5 that user later sets `MLC_CACHE` | **PASS** — announced, caches move, old tree left on disk |
| 21.25 | §14.1 24 concurrent `mlc list repo` × 4 trials | **PASS** — `repos.json` exactly 2 entries every trial |
| 21.26 | §14.2/14.3 `mlc add script` / `mlc cp script local:` destination | **PASS** — `$MLC_CACHE/local/script/…`; **no** contamination of `site-packages/mlc_scripts/script/` |
| 21.27 | §14.4/14.5 switch repo root, keep cache root | **PASS** — both the cache entry and the authored script still resolve |
| 21.28 | §16.1/16.2 `import` side-effect freedom, 9 modules | **PASS** — no directory created by any of them |
| 21.29 | §16.3 no import-time `Action()` anywhere | **PASS** |
| 21.30 | §16.4 `mlc --version` builds no `Action` | **PASS** |
| 21.31 | §16.5–16.7 every CLI entry point + all 16 short commands + help paths | **PASS** — 18 console scripts present, all reach the parser (`mlc show cache` / `mlc script` exit 1 only on genuine usage errors) |
| 21.32 | §16.8 `mlc.access()` / `from mlc.action import access`; `get_default_parent()` identity | **PASS** — single shared instance; `peek_default_parent()` is `None` before first use and the same object after |
| 21.33 | `_create_local_repo` under contention — 32 concurrent first-runs × 3 trials | **PASS** — one valid `local/meta.yaml`, one uid, `repos.json` exactly 2 entries |

## 22. Regression suites

| # | Case | Result |
|---|---|---|
| 22.1 | `MLC_REPOS`/`MLC_CACHE` pinned: `pytest tests/ .github/scripts/ -q` | **58 passed, 4 failed** — `test_find_repo`, `test_cp_script`, `test_add_script`, `test_mv_script`, all needing CI-pulled content. **Byte-identical to rounds 1 and 2.** |
| 22.2 | vars unset, `HOME` redirected to scratch (see N7) | **58 passed, 4 failed** — same four. Round 2's `61 passed, 1 failed` differed only because the developer's real root already had `anandhu-eng@mlperf-automations` pulled. **No regression.** |
| 22.3 | `tests/` alone | **PASS** — the three pinned modules honour both roots |
| 22.4 | `tests/test_script_action_apptainer.py` `ignore_on_conflict` contract | **PASS** |

## 23. NEW defects found in round 3

### N11 — **High** — `_repos_json_lock()` swallows the body's `OSError` and yields twice, replacing every such failure with `RuntimeError: generator didn't stop after throw()`

`mlc/action.py:436-455`. The `yield` sits *inside* the `try`, so an exception
raised by the **body** of `with self._repos_json_lock():` is delivered to the
generator at that `yield` and caught by the new `except OSError`. The generator
then falls through to the trailing bare `yield`, and `contextlib` — which is
unwinding a `gen.throw()` — raises `RuntimeError("generator didn't stop after
throw()")` instead of the original error.

**Repro** (writable repo root, so the lock file *is* creatable; only
`repos.json` is not writable — a root-owned registry under a user-writable
directory, i.e. exactly the "shared, admin-managed root" the new comment says
this branch exists to support):

```
mkdir -p R C
MLC_REPOS=R MLC_CACHE=C mlc list repo      # (no mlc-scripts installed) seeds repos.json
chmod 444 R/repos.json
MLC_REPOS=R MLC_CACHE=C mlc list repo      # from a venv WITH mlc-scripts -> must append
```

**Expected:** the `PermissionError`, or a clean `{'return': 1, 'error': …}`.
**Actual:**

```
PermissionError: [Errno 13] Permission denied: '…/R/repos.json'

During handling of the above exception, another exception occurred:
  …
  File ".../mlc/action.py", line 575, in _sync_package_repo
    with self._repos_json_lock():
  File "/usr/lib/python3.12/contextlib.py", line 194, in __exit__
    raise RuntimeError("generator didn't stop after throw()")
RuntimeError: generator didn't stop after throw()
```

Through `mlcr` the whole diagnosis collapses to three useless lines:
`Error during 'script' action: RuntimeError: generator didn't stop after throw()
at /usr/lib/python3.12/contextlib.py:194` — the real cause is erased, which also
negates the N5 improvement for this class of failure. Reproduced at **both**
call sites (`_sync_package_repo:575` and `_ensure_local_registered:498`).

Triggers are any `OSError` from `_rewrite_repos_json` while the lock is held:
read-only `repos.json`, `ENOSPC`, a stale NFS handle, an `EACCES` on a
root-owned registry.

**Fix shape:** acquire/release explicitly and keep the `yield` outside the
`try` that catches lock errors —

```python
lock = None
try:
    lock = FileLock(repos_file_path + ".lock", timeout=60)
    lock.acquire()
except Timeout:
    logger.warning(...); lock = None
except OSError as e:
    logger.debug(...); lock = None
try:
    yield
finally:
    if lock is not None:
        lock.release()
```

### N12 — **Low** — docker/apptainer contexts still hard-code the folder name `local`, so they miss a registered local repo whose folder is named otherwise

The N3 fix derives `self.cache_path` from the *resolved* local repo
(`os.path.dirname(local_repo_path)`), but `automation/script/docker_utils.py:203`
and `apptainer.py:488` still rebuild the path as
`os.path.join(mlc.cache_path, 'local', …)`. When the registered `local` repo
lives in a folder that is not literally called `local`, those two disagree again.

**Repro:** `repos.json` containing `X/mycache`, whose `meta.yaml` says
`alias: local`; `MLC_CACHE` unset.
**Actual:** caches correctly go to `X/mycache/cache`, `mlc list repo` correctly
reports `MLC_CACHE: X` — but `mlcd detect,os` writes to
`X/local/docker/detect-os_86373`, creating a stray unregistered `X/local/`
beside the real one. Same "stray `local/` with no `meta.yaml`" the new comment
there claims to prevent, one level in.

Narrow: `mlc add repo` always sets `alias` = folder basename, so this needs a
hand-written `meta.yaml`. Both call sites should use the resolved local repo
path (e.g. `os.path.dirname(mlc.local_cache_path)`) rather than re-appending
`'local'`.

### N10 — **Medium** — `pip install -e .` of `mlc-scripts` produces a mis-resolved environment and prints advice that would destroy the editable install

The payload (`meta.yaml`, `script/`) is assembled into `build_lib` at build
time and never exists in the source tree; `<checkout>/mlc_scripts/` holds only
`__init__.py`. `find_package_repo()` accepts a candidate on `__init__.py` alone
(deliberately, so a damaged install does not flip the root), so an editable
install resolves the package repo to `<checkout>/mlc_scripts`.

**Actual, verified in `venvEDS`:**

* every command warns *"The installed mlc-scripts has no meta.yaml at
  `<checkout>/mlc_scripts/meta.yaml` … Reinstall it with `pip install
  --force-reinstall mlc-scripts`"* — advice that, if followed, replaces the
  developer's editable install with the PyPI wheel;
* the repo root becomes `~/MLC/envs/<hash of the checkout dir>` instead of
  `<hash of site-packages>`, so two different venvs editable-installed from the
  same checkout silently share one repo root;
* no script content is registered at all — the first `mlcr` falls through to the
  "no content repo" auto-pull and clones `--branch=dev` into `$MLC_REPOS`, so the
  developer ends up running **dev HEAD content, not their own checkout**, and
  that first run emits a large "Detected deleted item" burst.

The same masquerade fires for *any* interpreter with the checkout on `sys.path`
after a local build, because `python -m build` leaves a `mlc_scripts.egg-info/`
in the tree: `cd <checkout> && python -c "import mlc…"` reports mlc-scripts 1.1.0
"installed" at `<checkout>/mlc_scripts` and flips the repo root. Console scripts
(`mlc`, `mlcr`) are immune — `sys.path[0]` is `venv/bin`, not the cwd — so this
only bites the Python API and `python -m` style invocations.

Cheapest mitigations: require `meta.yaml` **or** `script/` (not `__init__.py`)
when accepting a candidate, and/or ship a `[project.optional-dependencies]`-free
note that `pip install -e .` is unsupported for `mlc-scripts`.

### N13 — **Low** — `remote_copy_mlc_repos=True` can copy two repos to the same remote path

With two registered repos sharing a folder basename, the `True` form now
correctly copies both — but both land in `MLC/repos/<basename>` on the remote, so
the second overwrites the first. The explicit basename form silently picks the
last-registered one. Neither is warned. Narrow; only reachable with two repos
whose directories share a name.

## 24. Release-hygiene observations (not code defects)

* The `mlperf-automations` working tree is dirty in ways that reach the wheel:
  `script/my-os-detect/` is **untracked** and `script/app-image-corner-detection/`
  is **deleted**. `setup.py` copies the working tree, so the wheel I built ships
  `my-os-detect` — a duplicate of `detect-os` carrying the same `detect,os` tags,
  which makes `mlcr detect,os` and `mlcd detect,os` fail with *"More than one
  scripts found for tags detect,os"*. I removed it from the test venvs to get a
  clean comparison. A CI build from a clean checkout is unaffected, but the tree
  should be cleaned before tagging.
* `mlc_scripts.egg-info/` and `build/` persist in the checkout after a local
  build and are what make N10's masquerade fire. Worth a `make clean`/CI note.
* Displacing the packaged repo (explicit `mlc pull repo` of the same uid) emits a
  burst of `Detected deleted item: …/site-packages/mlc_scripts/script/*/meta.yaml`
  warnings for files that still exist. It is one-off (0 on the next run) and is
  just index cleanup, but the wording is alarming.
* `mlc cp script <src> <alias>:<name>` with two repos sharing an alias picks the
  first registered, deterministically and without warning.

## 25. Defect index — round-3 status

| ID | Severity | One-line | Round-3 status |
|---|---|---|---|
| D1 | Critical | wheel ships a top-level `automation` package | **FIXED** (re-verified on a rebuilt wheel: 0 RECORD overlap) |
| D2 | High | `MLC_CACHE` only honoured on the first run | **FIXED** (N2 + N3 both closed) |
| D3 | High | `mlc add script` writes into site-packages | **FIXED** |
| D4 | Medium | `pull_repo`'s non-git guard unreachable | **FIXED** |
| D5 | Medium | missing package `meta.yaml` flips the repo root | **FIXED** (root holds; N6 closed the message) |
| D6 | Medium | packaged repo cannot be removed | **ADDRESSED** — accurate warning + two working escape hatches |
| D7 | Medium | `<repo>:` destinations resolve against `MLC_REPOS` | **FIXED** (N1 closed the alias caveat) |
| D8 | Low | `repos.json` writes unlocked; `pull` bypasses `is_git_repo` | **PARTIAL** — locking and `is_git_repo` verified; failure handling regressed into **N11** |
| D9 | Low | `remote_copy_mlc_repos` copies nothing | **FIXED** (N8 closed; N13 is a new, narrower residue) |
| D10 | Low | wheel build depends on an untracked `__init__.py` | **FIXED** (N9 removed the dead fallback) |
| N1 | Medium | `cp` destination matched by basename only | **FIXED** |
| N2 | High | second `local` defeats `MLC_CACHE` | **FIXED** |
| N3 | Medium | back-compat branch misreports and writes outside the local repo | **FIXED** |
| N4 | Medium | read-only repo root kills every command | **PARTIAL** — lock cause fixed, symptom remains (20.4b/c) |
| N5 | Medium | error reporting double fault | **FIXED** |
| N6 | Low | unparseable-meta branch was dead code | **FIXED** |
| N7 | Low | `test_mlc_access.py` unpinned | **WON'T FIX** (agreed) |
| N8 | Low | `remote_copy_mlc_repos` alias/empty forms | **FIXED** |
| N9 | Low | dead `build_py` fallback | **FIXED** |
| N11 | **High** | lock context manager converts body `OSError` into `RuntimeError` | **NEW — open** |
| N12 | Low | docker/apptainer hard-code the folder name `local` | **NEW — open** |
| N10 | Medium | `pip install -e .` of mlc-scripts mis-resolves | **NEW — open** |
| N13 | Low | `remote_copy_mlc_repos` basename collision on the remote | **NEW — open** |

## 26. Round-3 directories created outside the scratch dir

**None.** `~/MLC/envs/` still contains only `518c9787f718`, `9068a9e0e7d4`,
`939642a0024b`, `be33943c3d61` — all from round 1. Every CLI run pinned
`MLC_REPOS`/`MLC_CACHE`, and the auto-resolution checks called
`resolve_repos_path()` directly or redirected `HOME` into the scratch dir.

`/home/user/MLC/repos/repos.json` verified byte-correct at the start and at the
end, **mtime unchanged** (`2026-08-10 16:16:43`, before this run began):

```
[
  "/home/user/MLC/repos/local",
  "/home/user/MLC/repos/mlcommons@mlperf-automations"
]
```

`/home/user/MLC/repos/my-new-repo/` does not exist.
`/home/user/MLC/repos/local/script/moved-my-script-1` is still there — it
predates round 3.

## 27. Verdict

**Do not ship as is — one blocker.**

* **Blocker: N11.** It is a two-line context-manager bug, but it turns every
  write failure on `repos.json` into `RuntimeError: generator didn't stop after
  throw()` with the real cause erased, on the *first line of every command*. It
  fires precisely in the deployment the fix was written to support (a shared,
  admin-managed repo root) and it undoes N5's benefit for that class of failure.
  Low risk to fix, high cost to leave.
* **Should fix with it: N4's remaining symptom.** With N11 corrected, a
  read-only root still exits with a raw `PermissionError` traceback. Wrapping the
  two `_rewrite_repos_json` call sites so they log and continue read-only would
  finish the story the code comment already tells.
* **Before tagging:** clean the `mlperf-automations` working tree — the untracked
  `script/my-os-detect/` duplicates `detect-os`'s tags and would ship in the wheel,
  breaking `mlcr detect,os` for every user (§24).
* **Follow-ups, not blockers:** N10 (editable install), N12, N13, and a
  `conftest.py` that pins both roots for `.github/scripts/` (N7).

Everything else that was in scope for this round — D1–D10, N1, N2, N3, N5, N6,
N8, N9 and the D6 message — is verified fixed, and the full regression sweep
(33 checks) plus both pytest invocations show no regression against rounds 1
and 2.

---
---

# Round 4 — final sign-off pass

Ran 2026-08-10 against the current working trees, after the fixes for **N11**
(the round-3 blocker), **N4**'s remaining symptom, **N10**, **N12** and the
`mlperf-automations` release-hygiene cleanup.

**The mlcflow wheel was rebuilt from the current source for this round**
(`r4/distflow/mlcflow-1.4.0-py3-none-any.whl`); no wheel on disk contained the
N11/N12 fixes. It was built from a *copy* of the checkout
(`r4/srcflow/`) so that no build artefact could land in the real tree. The
`mlc-scripts` wheel is the supplied `dist4/mlc_scripts-1.1.0-py3-none-any.whl`.
Presence of every fix was confirmed inside the built wheel before any test.

Environments (all fresh, under the QA scratch dir `r4/`):

| Name | mlcflow | mlc-scripts | Purpose |
|---|---|---|---|
| `venvPK` | **wheel** (non-editable) | wheel 1.1.0 | primary end-user layout |
| `venvED` | editable `srcflow` | wheel 1.1.0 | second env for sharing/isolation, pytest |
| `venvBARE` | editable `srcflow` | absent | "no package" branches, pytest baseline |
| `venvEDS` | wheel | **`pip install -e .`** | N10 |
| `venvEDS2` | wheel | `pip install -e .` of a **second** checkout | N15 |
| `venvDEP` | wheel | wheel, deps satisfied | uninstall/reinstall, RECORD overlap |
| `venvFL` | resolved by pip (`--find-links`) | resolved by pip | true dependency resolution |
| `venvFB` | wheel | deliberately broken payload | `find_package_repo` adversarial |

## 28. The round-3 blocker and its follow-ups

### N11 — lock context manager erased the real error — **VERIFIED FIXED**

The exact round-3 repro (writable root so the lock file *is* creatable, only
`repos.json` made read-only, then a run that must append the packaged repo):

```
MLC_REPOS=R MLC_CACHE=C venvBARE/bin/mlc list repo    # seeds repos.json
chmod 444 R/repos.json
MLC_REPOS=R MLC_CACHE=C venvPK/bin/mlc list repo      # must append
```

| Check | Round 3 | Round 4 |
|---|---|---|
| error surfaced | `RuntimeError: generator didn't stop after throw()` | *"Could not update …/repos.json ([Errno 13] Permission denied…). Continuing with the registry as it is on disk; changes to registered repos will not persist."* |
| traceback | full, real cause erased | **none** |
| exit code | 1 | **0** |
| `mlcr` diagnosis | 3 useless lines | the real cause, named file |

Context-manager properties, exercised directly against `Action._repos_json_lock()`:

| # | Property | Result |
|---|---|---|
| 28.1 | body raises `OSError` → propagates unchanged | **PASS** |
| 28.2 | body raises `ValueError` → propagates unchanged | **PASS** |
| 28.3 | body raises `KeyboardInterrupt` (BaseException) → propagates | **PASS** |
| 28.4 | lock released after a body exception (re-acquire in the same process) | **PASS** |
| 28.5 | `return` inside the `with` → releases, re-acquirable | **PASS** |
| 28.6 | no double release (`lock.release()` guarded by `acquired`) | **PASS** |
| 28.7 | lock-creation failure (read-only root) → unlocked fallback, body still runs | **PASS** |
| 28.8 | body `OSError` in the *unlocked fallback* path also propagates | **PASS** |
| 28.9 | nested `with self._repos_json_lock():` | **NOTE — N18**: not reentrant; stalls 60 s, then proceeds unlocked with a Timeout warning. **Not reachable in the current code** (neither call site nests), but it is a 60-second trap for any future nesting |

Both original call sites (`_ensure_local_registered`, `_sync_package_repo`) were
re-exercised. **N11 is closed.**

### N4 — remaining symptom — **FIXED, with one new consequence (N14)**

| # | Case | Result |
|---|---|---|
| 28.10 | read-only `MLC_REPOS`, everything already registered | **PASS** — no write attempted, `mlc list repo` fully functional, both repos listed. This is the realistic admin-managed deployment and it works end to end |
| 28.11 | read-only `MLC_REPOS`, **no** `repos.json` (bootstrap), via `mlcr` | **PASS** — 4 lines, no traceback, final line is *"Could not create …/repos.json (…). **Set MLC_REPOS to a writable directory.**"*. Reads sensibly and names the fix |
| 28.12 | same, via `mlc list repo` | **PASS (with a caveat)** — a raw traceback is still printed, but it now *terminates* in the same actionable `RuntimeError`. Pre-existing: `get_default_parent()` is called at `main.py:650`, outside the `try` that feeds `_report_error`; identical at `HEAD`. The N5 improvement is reached through the `mlcr`/script path only |
| 28.13 | fully read-only root (dir **and** file), package needs registering | **PASS** — warning, `rc=0`, no traceback (round 3: raw `PermissionError`) |
| 28.14 | that run's usability | **FAIL — N14** (new, see §30) |

### N10 — `pip install -e .` of `mlc-scripts` — **VERIFIED FIXED**

`find_package_repo()` now rejects the bare `__init__.py` stub and falls back to
the parent when it has both `meta.yaml` and `script/`.

| Check | Round 3 | Round 4 (`venvEDS`) |
|---|---|---|
| resolved package repo | `<checkout>/mlc_scripts` (stub, empty) | **`<checkout>`** — the real payload |
| *"has no meta.yaml … `pip install --force-reinstall`"* warning | on every command | **0 occurrences** |
| script content registered | none | **registered**, alias `mlcommons@mlperf-automations` |
| first `mlcr detect,os` | auto-cloned `--branch=dev`, "Detected deleted item" burst | **rc=0, no clone**, cache in `$MLC_CACHE/local/cache/detect-os_…` |
| repo root contents afterwards | a full dev-HEAD clone | only `repos.json` + index files |

The cwd masquerade (`cd <checkout> && python -c "import mlc…"` after a local
build leaves `mlc_scripts.egg-info/`) still reports mlc-scripts "installed", but
it now resolves to the checkout with its real content instead of an empty stub,
so the harmful half is gone. Residual: see **N15**.

Wheel installs are unaffected — `venvPK` still resolves
`<site-packages>/mlc_scripts` on the first branch (`meta.yaml` present), and the
D5 property holds: with `meta.yaml` deleted the candidate is still accepted via
`script/`, so the repo root does **not** flip (28.20 below).

### N12 — docker/apptainer build contexts — **VERIFIED FIXED**

`Action` exposes `self.local_repo_path`; both call sites derive from it.

Repro: `repos.json` holding `X/mycache` whose `meta.yaml` says `alias: local`,
`MLC_CACHE` unset, `MLC_REPOS=R`.

| Check | Round 3 | Round 4 |
|---|---|---|
| `mlc list repo` `MLC_CACHE:` | `X` | `X` |
| `mlcd detect,os` build context | `X/local/docker/detect-os_86373` | **`X/mycache/docker/detect-os_86373`** |
| stray `X/local/` | created | **absent** |
| stray `R/local/` | — | **absent** |
| container ran | — | **rc=0**, real docker build + run |
| apptainer expression (evaluated directly; apptainer not installed) | — | `<resolved>/apptainer/<folder>`; the `getattr` fallbacks degrade to `cache_path/local` then `repos_path/local` for an old `mlc` object |

### N13 — same-basename repos colliding on the remote — **CONFIRMED OPEN, accept as a follow-up**

`remote_run.py` is unchanged since round 3. Re-read: `repos_to_copy` de-dups by
*path*, so two registered repos sharing a directory basename are both copied —
but both land in `MLC/repos/<basename>` on the remote, so the second overwrites
the first, and the explicit basename form still picks the last-registered one.
Neither is warned.

**I agree it is not a release blocker.** It needs two registered repos whose
*directory names* collide, `remote_copy_mlc_repos` in use, and an SSH target;
the failure is a missing repo on the remote, not data loss; and the fix (copy to
`MLC/repos/<alias-or-uid>`) changes the remote layout, which is not a change to
make under a release deadline. It should be filed.

### Release hygiene — **VERIFIED CLEAN**

| Check | Result |
|---|---|
| `script/my-os-detect/` in the tree | **gone** |
| `script/app-image-corner-detection/` | **restored** (tracked, present) |
| `git status --short` in `mlperf-automations` | 5 modified + 1 staged add — exactly the feature diff, no artefacts |
| wheel: entries / script dirs | 2042 / **371** |
| wheel: `top_level.txt` | `mlc_scripts` |
| wheel: top-level dirs | `mlc_scripts`, `mlc_scripts-1.1.0.dist-info` — **no `automation/`** |
| wheel: `my-os-detect` | **absent** |
| wheel: `app-image-corner-detection` | **present** |
| wheel: `by-category/`, `__pycache__`, symlinks | none / none / 0 |
| wheel: exec-bit files | 25 |
| wheel: `meta.yaml` | `git: false`, uid `9cf241afa6074c89` |
| wheel: `.mlc-provenance.json` | 1.1.0, commit `bee7550…`, source URL |
| wheel: `Requires-Dist` | `mlcflow >=1.4.0` |

**Where the `my-os-detect` artefact came from — now identified.** It is created
by `.github/scripts/test_mlc_access.py::test_cp_script`, which runs
`cp script detect-os` → dest `my-os-detect` **with no repo prefix**. Under this
feature that lands in the *source* repo — site-packages, or a registered
checkout of `mlperf-automations`. Reproduced this round: running the CI suite in
`venvED` wrote `my-os-detect` into `venvED/.../site-packages/mlc_scripts/script/`.
So the artefact will reappear for anyone who runs the CI suite locally. That is
**N17**.

## 29. Full regression sweep

| # | Area | Result |
|---|---|---|
| 29.1 | §1 root resolution, 9 shapes × `venvPK`/`venvBARE` (18 cases) | **PASS** — byte-identical to rounds 1–3; empty/whitespace treated as unset, relative resolved to abspath, `~` expanded, `MLC_REPOS` also sets the cache root, auto repo root never does |
| 29.2 | §1.11 env hash distinct per venv | **PASS** for wheel installs (`venvPK` `7e253535f6fc`, `venvED` `54d22c6f5f2b`, `venvBARE` → `~/MLC/repos`). **Editable installs collide — N15** |
| 29.3 | §1.13 / D5 package with `meta.yaml` deleted keeps the env root | **PASS** — accepted via `script/`, root stays `~/MLC/envs/7e253535f6fc` |
| 29.4 | §2.4 cache destination | **PASS** — `$MLC_CACHE/local/cache/detect-os_…`; repo root holds only `repos.json` + index files |
| 29.5 | §2 real `mlcr detect,os` cold run, then **cache hit** | **PASS** — second run reuses, still exactly one cache entry |
| 29.6 | §3.3 read-only site-packages (`chmod -R a-w`) | **PASS** — `mlcr detect,os` rc=0, loads the cached state |
| 29.7 | §3.4/3.5 uninstall → registry self-heals → reinstall re-registers | **PASS** (`venvDEP`) |
| 29.8 | §4.1 uid tie: `mlc add repo` of a same-uid checkout | **PASS** — checkout wins, package unregistered, `repos.json` = 2 entries |
| 29.9 | §4.3/4.4 shadow announcement on every subsequent run | **PASS** — 3/3, names winner, loser and version |
| 29.10 | §5 two-venv isolation, distinct `MLC_REPOS`, one shared `MLC_CACHE`, A→B→A→B→A | **PASS** — one shared `local` uid `926af4b222894eaa`, one cache entry reused by both, **0 "Detected deleted item" lines in all five runs** |
| 29.11 | §6.1/6.2 `git:` derived from disk on `mlc add repo` | **PASS** — plain dir `git: false`, real checkout `git: true` |
| 29.12 | §6.4 `mlc pull repo` non-git, folder == alias | **PASS** — friendly refusal |
| 29.13 | §6.5 `mlc pull repo <alias>` where alias ≠ folder | **PASS** — refusal naming the real path |
| 29.14 | §6.3 `.git` present but `git: false` declared | **PASS** — declaration wins, refused |
| 29.15 | §6.9 `mlc pull repo` (no args) | **PASS** — pulled the one git repo, silently skipped all three non-git ones, rc=0 |
| 29.16 | §6.7 `mlc rm repo` non-git under the root, declined | **PASS** — folder kept, unregistered, removed from index |
| 29.17 | §6.8 `mlc rm repo --f` non-git | **PASS** — folder deleted |
| 29.18 | §7.1/7.2 index prefix-match (`pfx` vs `pfx1`) | **PASS** — after removing `pfx`, `pfx1` survives in `index_script.json` **and** `modified_times.json` (1 ref each, 0 for `pfx`) and still resolves |
| 29.19 | §7.3 index files under the repo root | **PASS** |
| 29.20 | §8 `mlc list repo` annotations | **PASS** — `(set by MLC_REPOS)`, `(auto: mlc-scripts 1.1.0 at …)`, `(default)`; §8.5 correct in both branches |
| 29.21 | §9.1/9.2 docker build context, normal case | **PASS** — `$MLC_CACHE/local/docker/…`, no stray `local/` under the repo root; and the N12 case above |
| 29.22 | §11 wheel contents | **PASS** — see the hygiene table |
| 29.23 | §11.9/11.11 D1 — RECORD overlap and engine survival | **PASS** — **0** overlapping paths in `venvDEP`; only `mlcflow` claims `automation/script/module.py`; `pip uninstall mlc-scripts` leaves `mlc --version` and `mlc list repo` working and `automation/script/module.py` on disk. Re-confirmed on `venvFL` |
| 29.24 | true dependency resolution (`pip install mlc-scripts --find-links`) | **PASS** — pip pulls `mlcflow 1.4.0`, `mlcr detect,os` rc=0 |
| 29.25 | §12 back-compat single-root user, `MLC_REPOS` only | **PASS** — legacy `get-legacy_1234abcd` cache found, `MLC_CACHE == MLC_REPOS`, nothing moved, `repos.json` gains only the packaged repo |
| 29.26 | §12.5 that user later sets `MLC_CACHE` | **PASS** — announced, new caches move, old tree left on disk |
| 29.27 | §14.1 24 concurrent `mlc list repo` × 4 trials | **PASS** — `repos.json` exactly 2 entries in every trial, 0 corruptions |
| 29.28 | §14.2 `mlc add script <name>` | **PASS** — `$MLC_CACHE/local/script/…`, no site-packages contamination |
| 29.29 | §14.3 `mlc cp script <src> local:<name>` | **PASS** — `$MLC_CACHE/local/script/…` |
| 29.30 | §14.x `mlc mv script` + `mlc find script` afterwards | **PASS** |
| 29.31 | N1 destination spellings — alias / uid / basename / unregistered | **PASS** — all three registered forms work and warn *"belongs to the installed mlc-scripts … use `local:` to keep it"*; `nosuchrepo:x` gives the clean "is not registered" error, no `UnboundLocalError` |
| 29.32 | N1 **bare** destination (no `<repo>:` prefix) | **FAIL — N17** (new) |
| 29.33 | D5/N6 damaged package meta — unparseable / empty / no uid / absent | **PASS** — all four messages distinct and correct; root never flips |
| 29.34 | §16.1/16.2 import side-effect freedom, 9 modules | **PASS** — none of the 9 creates `$MLC_REPOS` or `$MLC_CACHE` |
| 29.35 | §16.3 no import-time `Action()` | **PASS** — only the lazy `get_default_parent()` accessor |
| 29.36 | §16.5–16.7 CLI surface: `list repo/cache`, `find script/cache/repo`, `show cache`, `reindex`, `rm cache -f`, `add/cp/mv script`, `add/rm repo`, `--help`, no-args | **PASS** — all rc=0 except no-args (rc=1, correct usage error) |
| 29.37 | all console scripts | **PASS** — 18 present (`mlc`, `mlcflow`, and the 16 short commands); every one reaches the parser, rc=0 |
| 29.38 | §16.8 `mlc.access()` for find/list, `from mlc.action import access`, `get_default_parent()` identity | **PASS** — single shared instance |
| 29.39 | §4.5 `tests/test_script_action_apptainer.py` `ignore_on_conflict` contract | **PASS** (in the suites below) |
| 29.40 | N8 `remote_copy_mlc_repos` block | **PASS** — source unchanged since round 3's verification; skips `local`, keys on basename+alias+uid, warns per-name and on "nothing matched" |

## 30. Regression suites

| # | Invocation | Result |
|---|---|---|
| 30.1 | `env -u MLC_REPOS -u MLC_CACHE python3 -m pytest tests/ .github/scripts/ -q`, `HOME` redirected to scratch, `venvED` | **60 passed, 2 failed** (`test_find_repo`, `test_cp_script`) |
| 30.2 | same, roots pinned, `venvED` | **60 passed, 2 failed** — same two |
| 30.3 | same, roots pinned, `venvBARE` (no mlc-scripts) | **58 passed, 4 failed** — `test_find_repo`, `test_cp_script`, `test_add_script`, `test_mv_script`. **Byte-identical to rounds 1, 2 and 3** |
| 30.4 | `tests/` alone | **36 passed** |

All variation is confined to `.github/scripts/test_mlc_access.py`, whose
fixtures CI seeds with its own `mlc pull repo` steps (N7, agreed won't-fix). With
`mlc-scripts` installed two of those four find the content they need and pass;
`test_find_repo` still needs `anandhu-eng@mlperf-automations`, and `test_cp_script`
fails on a second run because its `my-os-detect` destination already exists from
the first (see N17). **No regression attributable to this change.**

The documented unpinned invocation was run with `HOME` redirected, so N7 could
not touch the real registry. Verified: `/home/user/MLC/repos/repos.json` mtime
is unchanged, and the writes landed in the scratch `fakehome`.

## 31. NEW findings in round 4

### N14 — **Low/Medium** — a failed `repos.json` write silently drops the packaged repo, then triggers a network auto-clone

`_sync_package_repo()` appends the package path to the in-memory list, calls
`_rewrite_repos_json()` (which now correctly warns and returns `False`), logs
**"Registered mlc-scripts 1.1.0 from …"** unconditionally, and then does
`self.repos = self.load_repos_and_meta()` — which re-reads `repos.json` **from
disk** and therefore drops the repo that was never persisted.

Consequences on a writable directory holding a read-only `repos.json` (the
N11 repro state):

* `mlc list repo` succeeds but does **not** list the packaged repo, one line
  after claiming it was registered;
* `mlcr detect,os` reports *"No script content repo registered"* and
  **auto-clones `mlcommons@mlperf-automations --branch=dev` from GitHub** — a
  ~40 s surprise network operation that writes a full checkout into the "read-only"
  root — then exits **rc=1** with
  `Error pulling repository: [Errno 13] Permission denied: …/repos.json`.

Not a crash and the final message names the file, but the "Registered …" line is
actively false, and the deployment the fix comment says it exists to support
(*"a shared, admin-managed root"*) only works if the package path is **already**
in `repos.json` — which an admin cannot arrange for an arbitrary per-venv
site-packages path. Confirmed working when it *is* pre-registered (28.10).

Cheapest fix: keep the appended entry in `self.repos` when the write fails, and
only log "Registered …" when `_rewrite_repos_json()` returned `True`.

### N15 — **Low** — the env hash for an editable `mlc-scripts` keys on the checkout's *parent*, so sibling checkouts collide

`resolve_repos_path()` hashes `os.path.dirname(package_repo_path)`. For a wheel
that is site-packages (correct). For an editable install `package_repo_path` is
now the **checkout root**, so the hash is of the directory *containing* the
checkout.

Verified: two editable installs of two different checkouts placed side by side
resolve to the **same** repo root `~/MLC/envs/20970d19872e`. Running the second
venv then prints *"Using …/mlperf-automations, shadowing mlc-scripts 1.1.0 at
…/mlperf-automations-fork2"* — i.e. venv 2 runs **venv 1's** content. Two
checkouts side by side in `~/MLC/repos/` is a normal fork workflow.

Mitigating: it is announced on every run by the shadow line, and setting
`MLC_REPOS` avoids it entirely. Not silent, not destructive.

### N16 — **Low** — the `find_package_repo` parent fallback is unbounded and can resolve to site-packages itself

The fallback fires when the candidate has **neither** `meta.yaml` **nor**
`script/`, and accepts the parent on `meta.yaml` + `script/` alone — it never
checks that the parent is plausibly a repo of *this* package.

Constructed in `venvFB`: a broken `mlc_scripts` (payload removed, `__init__.py`
only) plus an unrelated top-level `meta.yaml` and `script/` in site-packages.
Result: `find_package_repo()` returns **site-packages**, and
`mlc list repo` prints
*"Registered mlc-scripts 1.1.0 from …/site-packages"* and lists site-packages as
a repo under the unrelated `meta.yaml`'s alias. The repo root also moves to a
hash of `python3.12/`.

**Not destructive** — verified: `mlc rm repo <alias> --f` takes the
external-path branch and only unregisters; site-packages was untouched (31 entries
before and after). The cost is a bogus repo, a spurious index scan of
site-packages, and a moved repo root.

Preconditions are narrow (a broken payload **and** a package shipping a
top-level `meta.yaml` + `script/`). Cheap hardening: require the parent's
`meta.yaml` to carry the expected alias/uid, or refuse a parent whose basename is
`site-packages`/`dist-packages`.

### N17 — **Medium** — `mlc cp script <src> <dest>` with no repo prefix writes into the *source* repo — site-packages — with no warning

`Action.cp()` (`mlc/action.py`, the `else` branch of the `<repo>:` split) sets
`target_repo_path = result.repo.path` — the repo the **source** came from. The
package-ownership warning added by the D7/N1 work sits only in the prefixed
branch, so the bare form gets neither the `local` default that `mlc add script`
has nor the warning.

**Verified:** `mlc cp script detect-os bare-copy` on `venvPK` →
`…/site-packages/mlc_scripts/script/bare-copy`. `$MLC_CACHE/local/script/` was
never created. `mlc add script bare-added` in the same root correctly went to
`$MLC_CACHE/local/script/bare-added`.

This is **D3's symptom in a sibling command**: authored work written into
site-packages, lost on the next upgrade or uninstall, silently. The `else`
branch is unchanged from `HEAD` (the warning string does not exist at `HEAD` at
all), so the *logic* is pre-existing — but before this feature the source repo
was an ordinary checkout under `$MLC_REPOS` and writing there was harmless. It
is the same "a latent path becomes harmful" shape as N1, and it is what produces
the `script/my-os-detect/` artefact §24 had to clean by hand.

Workarounds exist and work (`local:`, alias, uid, basename — all verified in
29.31). Fix shape: apply the same `pkg_path` warning after both branches, and/or
default the bare form to the local repo as `mlc add script` does.

### N18 — **Low / latent** — `_repos_json_lock()` is not reentrant

Each call constructs a fresh `FileLock`, so a nested
`with self._repos_json_lock():` blocks for the full 60 s timeout before falling
through to the unlocked path. Not reachable today — neither `_ensure_local_registered`
nor `_sync_package_repo` nests, and no other code path enters it — but any future
nesting turns into a silent one-minute stall rather than an error.

### Correction to round-2 note 15.2h — stale cache entries do **not** self-heal

Round 2 recorded that after switching `MLC_CACHE` the old root's entries linger
in `index_cache.json` but "self-heal on a later run". Re-tested this round: they
do **not**, as long as the old cache tree exists on disk.

Repro: run with `MLC_CACHE=C1`, then switch to `C2`. `repos.json` is correctly
re-pointed to `C2/local` and `mlc list repo` correctly reports `C2` — but
`mlcr detect,os` kept resolving the `C1` entry on runs 1, 2 and 3, `C2/local/cache`
stayed empty, and `mlc find cache --tags=detect,os` reported the `C1` path. A
*new* script (`detect,cpu`) did land in `C2`, and deleting the `C1` tree made the
next `detect,os` run rebuild under `C2`.

So D2's core fix holds — the registry moves and new work lands in the new root —
but pre-existing entries keep being served from the old root indefinitely. Low:
the caches genuinely exist and are usable; it matters if the old root is on a
volume that later goes away. Nothing in this round's changes affects it.

### Release sequencing note

`pip install mlc-scripts` in a clean venv against real PyPI **fails**:
`No matching distribution found for mlcflow>=1.4.0` (PyPI tops out at 1.3.3).
The pin is doing exactly its job, but **mlcflow 1.4.0 must be published before
mlc-scripts 1.1.0**, or the first users to try the new wheel get a hard resolver
error. Verified working once 1.4.0 is resolvable (`venvFL`, via `--find-links`).

## 32. Defect index — final status

| ID | Severity | One-line | Final status |
|---|---|---|---|
| D1 | Critical | wheel ships a top-level `automation` package | **FIXED** — 0 RECORD overlap on a rebuilt wheel, engine survives uninstall (×3 envs) |
| D2 | High | `MLC_CACHE` only honoured on the first run | **FIXED** — registry re-points, new work follows; pre-existing index entries linger (see the 15.2h correction) |
| D3 | High | `mlc add script` writes into site-packages | **FIXED** for `add`; the `cp` bare form is **N17** |
| D4 | Medium | `pull_repo`'s non-git guard unreachable | **FIXED** |
| D5 | Medium | missing package `meta.yaml` flips the repo root | **FIXED** — holds under the new `find_package_repo` |
| D6 | Medium | packaged repo cannot be removed | **ADDRESSED** — accurate warning + two working escape hatches |
| D7 | Medium | `<repo>:` destinations resolve against `MLC_REPOS` | **FIXED** |
| D8 | Low | `repos.json` writes unlocked; `pull` bypasses `is_git_repo` | **FIXED** — locking, fallback and failure handling all verified |
| D9 | Low | `remote_copy_mlc_repos` copies nothing | **FIXED** |
| D10 | Low | wheel build depends on an untracked `__init__.py` | **FIXED** |
| N1 | Medium | `cp` destination matched by basename only | **FIXED** |
| N2 | High | second `local` defeats `MLC_CACHE` | **FIXED** |
| N3 | Medium | back-compat branch misreports and writes outside the local repo | **FIXED** |
| N4 | Medium | read-only repo root kills every command | **FIXED** — clean warning + `rc=0`; bootstrap raises an actionable `RuntimeError`. Residue is **N14** |
| N5 | Medium | error reporting double fault | **FIXED** |
| N6 | Low | unparseable-meta branch was dead code | **FIXED** |
| N7 | Low | `test_mlc_access.py` unpinned | **WON'T FIX** (agreed; follow-up: a `conftest.py` that pins both roots and pre-pulls) |
| N8 | Low | `remote_copy_mlc_repos` alias/empty forms | **FIXED** |
| N9 | Low | dead `build_py` fallback | **FIXED** |
| N10 | Medium | `pip install -e .` of mlc-scripts mis-resolves | **FIXED** — residue is **N15** |
| N11 | **High** | lock CM converted body `OSError` into `RuntimeError` | **FIXED** — the round-3 blocker is closed |
| N12 | Low | docker/apptainer hard-code the folder name `local` | **FIXED** |
| N13 | Low | `remote_copy_mlc_repos` basename collision on the remote | **OPEN — accepted follow-up** |
| N14 | Low/Med | failed registry write drops the packaged repo and triggers an auto-clone | **NEW — open** |
| N15 | Low | editable install hashes the checkout's parent; siblings collide | **NEW — open** |
| N16 | Low | `find_package_repo` parent fallback can resolve to site-packages | **NEW — open** |
| N17 | **Medium** | bare `mlc cp script` destination writes into site-packages, unwarned | **NEW — open** |
| N18 | Low | `_repos_json_lock()` not reentrant (latent) | **NEW — open, unreachable today** |

## 33. Round-4 environment hygiene

**Nothing was created outside the scratch dir.**

* `~/MLC/envs/` still contains only the four round-1 hashes — `518c9787f718`,
  `9068a9e0e7d4`, `939642a0024b`, `be33943c3d61`. Every CLI run pinned
  `MLC_REPOS` and `MLC_CACHE`; the auto-resolution checks either called
  `resolve_repos_path()` directly or redirected `HOME` into the scratch dir.
* `/home/user/MLC/repos/repos.json` verified byte-correct at the start **and**
  at the end, mtime unchanged at `2026-08-10 16:16:43` — i.e. untouched since
  before round 3 ended:

  ```
  [
    "/home/user/MLC/repos/local",
    "/home/user/MLC/repos/mlcommons@mlperf-automations"
  ]
  ```
* `/home/user/MLC/repos/my-new-repo/` does not exist.
* **Both working trees are byte-identical to how this round found them.**
  `git status --short` at the start and at the end match exactly: mlcflow — 16
  modified + untracked `TESTING.md` (this file); mlperf-automations — 5 modified
  + staged `mlc_scripts/__init__.py`. No file was created or deleted in either
  repo: the mlcflow wheel was built from a copy (`r4/srcflow/`), the editable
  installs used copies (`r4/edsrc/`), and the ignored `build/` and `*.egg-info/`
  directories in both repos still carry their pre-run mtimes.
* `.github/scripts/test_mlc_access.py` was **not** run against the real root.

## 34. Verdict

**SHIP.**

* **N11, the round-3 blocker, is closed** — verified with the exact repro plus
  nine context-manager property tests (body exceptions of three kinds propagate
  unchanged, no double release, no lock left held, unlocked fallback still
  propagates). No `RuntimeError: generator didn't stop after throw()` remains
  reachable.
* **N4's remaining symptom is fixed** — a non-writable registry now warns and
  continues with `rc=0`, and the bootstrap failure raises an explicit,
  actionable `RuntimeError` naming `MLC_REPOS`. The realistic admin-managed
  deployment (root read-only, package already registered) works end to end.
* **N10 and N12 are fixed**, and the `mlperf-automations` tree and wheel are
  clean — 371 script dirs, `top_level.txt` = `mlc_scripts`, no `automation/`,
  no `my-os-detect`, `app-image-corner-detection` present.
* **No new blocker.** The full sweep (40 checks) and all four pytest invocations
  show no regression; the `venvBARE` pinned run is byte-identical to rounds 1–3.

Recommended to fix **with** the release, cheaply:

* **N17** (Medium) — one line moves the existing "belongs to the installed
  mlc-scripts" warning below both `cp` branches. It is D3's symptom in a sibling
  command and it is the mechanism that produced the release artefact §24 had to
  clean by hand, so it will keep re-appearing in developers' trees.
* **N14** (Low/Med) — don't log "Registered …" when the write failed, and keep
  the entry in `self.repos` so a read-only registry stays usable instead of
  triggering a surprise clone.

**Release sequencing:** publish **mlcflow 1.4.0 to PyPI before mlc-scripts
1.1.0**, or `pip install mlc-scripts` fails on the `mlcflow>=1.4.0` pin.

Follow-ups, not blockers: **N13**, **N15**, **N16**, **N18**, the 15.2h stale
cache-index correction, and a `conftest.py` for `.github/scripts/` (**N7**).

---

## Round 5 — post-review fixes (implementer)

Applied after round 4's report. Verified by direct test; the full suite
(`tests/` + `.github/scripts/test_repo_pull_force.py` +
`test_error_guidance.py`) passes 47/47 with both root vars unset.

| Item | Change | Verified |
|---|---|---|
| N11 | `_repos_json_lock()` acquires explicitly; `yield` in its own `try/finally`. Body exceptions propagate; lock released and re-acquirable. | Body `OSError` surfaces as itself, not `generator didn't stop`; re-entry clean |
| N4 | `_rewrite_repos_json()` returns False and warns on `OSError`. Bootstrap failure raises `RootNotWritableError`, caught in `main()` → one-line error, exit 1 (no traceback) for both `mlc` and `mlcr` | `exit code = 1`, single ERROR line |
| N10 | `find_package_repo()` requires `meta.yaml` or `script/`; falls back to the parent when the candidate is the editable-install stub | `pip install -e` resolves to the checkout root; no bogus force-reinstall advice |
| N12 | `Action.local_repo_path` exposed; docker/apptainer contexts derive from it | `local_repo_path` / `cache_path` / `local_cache_path` all agree |
| N14 | No "Registered …" claim when the write failed; the package stays in `self.repos` for the run | Read-only registry still resolves `detect,os` |
| N17 | The packaged-destination warning moved below both `cp` branches | Fires for `mlc cp script X Y` with no prefix |
| — | `mlc --help` regression from the `main()`/`_main()` split | Fixed (`_main.__doc__`); all 8 console scripts OK |

Working-tree hygiene: `script/my-os-detect/` (QA artefact duplicating
`detect,os`) removed and `script/app-image-corner-detection/` restored in
mlperf-automations. A wheel built from the cleaned tree has 371 script dirs,
`top_level.txt` = `mlc_scripts`, no `automation/`.

Accepted as follow-ups, not blockers: N13, N15, N16, N18, and a `conftest.py`
for `.github/scripts/` (N7).

**Release sequencing:** publish mlcflow 1.4.0 to PyPI *before* mlc-scripts,
or `pip install mlc-scripts` fails on the `mlcflow>=1.4.0` pin.
