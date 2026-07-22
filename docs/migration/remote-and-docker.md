# How to run remote/Docker scripts with no git clone

Verify — and use — the no-clone guarantee that Option B added to
`mlcrr`/`mlcre`/`mlcrd` (SSH remote execution) and `mlcd`/`mlca` (containers).

See [Reference](reference.md#remote-execution-mlcrr-mlcre-mlcrd-no-more-auto-clone)
for exactly what changed under the hood.

## Prerequisites

- `mlcflow>=2.0.0` and `mlc-scripts>=2.0.0` installed locally (`pip install
  mlcflow mlc-scripts`)
- For remote execution: SSH access to a target host (`--remote_host=127.0.0.1`
  works if local SSH is enabled — see the SSH setup snippet below)
- For containers: Docker or Apptainer/Singularity installed

## Verifying remote execution doesn't clone

1. Enable SSH to localhost if you don't have a second machine handy:

   ```bash
   [ -f ~/.ssh/id_rsa ] || ssh-keygen -t rsa -N "" -f ~/.ssh/id_rsa
   grep -qf ~/.ssh/id_rsa.pub ~/.ssh/authorized_keys 2>/dev/null || cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ssh -o BatchMode=yes 127.0.0.1 echo SSH_OK   # must print SSH_OK
   ```

2. Run a simple script remotely with `--verbose` so you can see the full SSH
   command stream:

   ```bash
   mlcrr detect,os --remote_host=127.0.0.1 --remote_user=$USER \
     --remote_ssh_key_file=~/.ssh/id_rsa -j --verbose
   ```

3. In the output, confirm you see:

   ```
   pip install -U mlc-scripts
   ```

   and that you do **not** see `git clone` or `mlc pull repo` anywhere in the
   bootstrap sequence.

## Verification

```bash
mlcrr detect,os --remote_host=127.0.0.1 --remote_user=$USER \
  --remote_ssh_key_file=~/.ssh/id_rsa -j 2>&1 | grep -c 'git clone\|pull repo'
# should print 0
```

If you *want* the remote host to also have the real `mlperf-automations` repo
(for example, to run tests that need files outside the `mlc-scripts` package),
add it back explicitly:

```bash
mlcrr detect,os --remote_host=127.0.0.1 --remote_user=$USER \
  --remote_ssh_key_file=~/.ssh/id_rsa --remote_pull_mlc_repos -j
```

This is a separate, explicit, additive step — it does not re-enable the old
implicit auto-clone-on-every-run behavior.

## Testing a local mlcflow/installer checkout before it's merged

If you're modifying `mlc/engine/remote_run.py` or
`docs/install/mlcflow_unix_installer.sh` and want to test your changes on the
remote host without pushing to `dev` first:

```bash
mlcrr detect,os --remote_host=127.0.0.1 --remote_user=$USER \
  --remote_ssh_key_file=~/.ssh/id_rsa \
  --remote_local_installer_path=./docs/install/mlcflow_unix_installer.sh \
  --remote_local_mlcflow_path=. \
  -j --verbose
```

This uses `cat <path>` to feed the remote your local installer script instead
of `curl`-ing it from GitHub, and installs your local mlcflow checkout on the
remote instead of pulling from PyPI.

## Verifying Docker/Apptainer builds don't clone

1. Build (or rebuild) the image and inspect the generated Dockerfile:

   ```bash
   mlcd detect,os -j
   ls "$MLC_REPOS/local/docker/"
   ```

2. Confirm `mlc-scripts` is installed and no clone/pull is present:

   ```bash
   grep -ri "mlc-scripts" "$MLC_REPOS"/local/docker/*/*.Dockerfile          # must be PRESENT
   grep -ri "mlc pull repo\|git clone.*mlperf-automations" \
            "$MLC_REPOS"/local/docker/*/*.Dockerfile                        # must be ABSENT
   ```

3. If you specifically need the real repo mounted or copied into the image
   (e.g. testing an unpublished script change), use one of the documented
   escape hatches instead of expecting an implicit clone:

   ```bash
   # Mount all host-registered MLC repos into the image
   mlcd detect,os --docker_host_mlc_repos -j

   # Copy one specific local repo checkout into the build context
   mlcd detect,os --env.MLC_REPO_PATH=/path/to/local/mlperf-automations -j
   ```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| SSH bootstrap still shows `git clone` | `--remote_pull_mlc_repos` was passed explicitly, or you're on a pre-2.0 mlcflow/installer version | Drop `--remote_pull_mlc_repos` if you didn't mean to set it; check `mlc --version` and re-run the installer |
| Dockerfile still has `RUN mlc pull repo` | `mlc-scripts` isn't in the image's `python-packages` list (custom `dockerinfo.json` override, or an old cached Dockerfile) | `mlcd detect,os --docker_rebuild -j` to force regeneration; confirm your `dockerinfo.json`'s `python-packages` includes `mlc-scripts` |
| Remote run fails with `pip: command not found` | The remote venv wasn't activated correctly, or `--remote_python_venv` points at a venv that doesn't exist yet | Check the installer output for venv creation; pass `--remote_python_venv=<name>` matching what the installer created |
| `sshpass` auth fails silently / hangs | `--remote_password` was used without `sshpass` installed on the local machine | Install `sshpass`, or switch to `--remote_ssh_key_file` (recommended — password auth over automated SSH is inherently fragile) |
