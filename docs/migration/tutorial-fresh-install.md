# Tutorial: fresh install to first script run

You'll install `mlcflow` 2.0.0 and `mlc-scripts` 2.0.0 from scratch into a
clean virtual environment, run your first script, and confirm that nothing
was cloned from GitHub to make it work — the core guarantee of the Option B
migration. By the end you'll understand where the engine and script content
actually live on disk.

## What you'll need

- Python 3.7+ and `pip`
- No prior `~/MLC/repos` setup required — this tutorial starts from nothing

## Step 1: Install into a clean venv

```bash
python3 -m venv mlcflow-tutorial
source mlcflow-tutorial/bin/activate
pip install -U pip
pip install mlcflow mlc-scripts
```

Confirm both packages loaded correctly:

```bash
python -c "from mlc.engine import ScriptAutomation; print('engine OK')"
python -c "import mlc_scripts, os; print('scripts:', sum(1 for e in os.scandir(mlc_scripts.SCRIPTS_DIR) if e.is_dir()))"
```

You should see:

```
engine OK
scripts: 371
```

(the exact count grows over time as new scripts get published — the important
part is that it's a real, non-zero number, read straight out of the installed
package's `SCRIPTS_DIR`, not fetched from anywhere).

## Step 2: Run your first script

```bash
mlcr detect,os -j
```

Real output from this exact command:

```
[.... index.py: 335 WARN ] - Missing index files: script, cache, experiment. Forcing full index rebuild...
[.... script_utils.py: 88 INFO ] - * mlcr detect,os
[.... module.py: 1881 INFO ] -   - cache UID: c31147a2fc454878
[.... module.py: 1912 INFO ] - {
  "return": 0,
  "env": {
    "MLC_HOST_OS_TYPE": "linux",
    "MLC_HOST_OS_BITS": "64",
    "MLC_HOST_OS_FLAVOR": "ubuntu",
    "MLC_HOST_OS_VERSION": "24.04",
    "MLC_HOST_SYSTEM_NAME": "your-hostname",
    ...
  },
  "new_env": { ... same keys ... },
  "state": {
    "os_uname_machine": "x86_64",
    "os_uname_all": "Linux your-hostname 6.x.x-generic ... x86_64 GNU/Linux"
  },
  "deps": []
}
```

The `Missing index files ... Forcing full index rebuild` warning is expected
and only happens once — `mlcflow` is building its tag index for the first
time. `"return": 0` means the script ran successfully; the `env`/`new_env`
dictionaries are the actual detected OS facts on your machine.

## Step 3: Confirm nothing was cloned

```bash
cat "${MLC_REPOS:-$HOME/MLC/repos}/repos.json"
```

Real output:

```json
[
  "/path/to/your/MLC_REPOS/local"
]
```

Just one entry — your own `local` repo (created automatically to hold
anything you personally add), no `mlcommons@mlperf-automations` git clone.
The `detect,os` script you just ran came entirely from the `mlc-scripts`
package you `pip install`ed in Step 1: mlcflow registers it internally as a
read-only synthetic repo, but that registration never touches disk or the
network — see [Reference](reference.md#how-mlcflow-discovers-mlc-scripts-content)
for exactly how.

## What you built

You have a working `mlcr` install that ran a real script (`detect,os`) end to
end — dependency resolution, `preprocess`/`postprocess`, and caching all
happened — using only what `pip install` gave you. No git clone, no network
call beyond PyPI, and the result would be identical on a fully offline
machine with the two wheels pre-downloaded.

From here:

- Run a real benchmark: try `mlcr run-mlperf,inference,_submission,_short,_r6.0-dev
  --model=resnet50 --implementation=mlcommons-python --backend=onnxruntime
  --device=cpu --scenario=Offline --test_query_count=10 --target_qps=1
  --hw_name=my-machine --quiet` — this exercises an 8-12 deep dependency
  chain, still entirely from the pip package.
- Try it over SSH or in Docker: [Running remote/Docker without a clone](remote-and-docker.md)
- Already had `mlcflow` installed before 2.0.0? [Upgrading from pre-2.0 mlcflow](upgrading.md)
- Want the full technical picture? [Reference](reference.md)
