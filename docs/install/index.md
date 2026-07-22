---
hide:
  - toc
---

# Installation

## Dependencies
MLCFlow needs `python>=3.7`, `python3-pip`, `python3-venv` and `git` installed on your system.

=== "Ubuntu"
    ```bash
    sudo apt-get install -y python3-dev python3-venv python3-pip git wget sudo unzip curl
    ```
=== "RedHat"
    ```bash
    sudo dnf install -y python3-dev python3-pip git wget sudo unzip binutils curl
    ```
=== "Arch"
    ```bash
    sudo pacman -Sy python python-pip git wget sudo binutils curl
    ```
=== "macOS"
    ```bash
    brew install python git wget binutils curl
    ```
=== "Windows"

    WinGet the Windows Package Manager is available on Windows 11, modern versions of Windows 10, and Windows Server 2025 as a part of the App Installer. For more information visit mirosoft's [site](https://learn.microsoft.com/en-us/windows/package-manager/winget/).

    ```bash
    winget install wget Git.Git python3 cURL.cURL unzip --accept-package-agreements
    ```
    
    

    


## Activate a Virtual ENV for MLCFlow (Optional)
This step is not mandatory. But the latest `pip` install requires this or else will need the `--break-system-packages` flag while installing.

=== "Unix"
    ```bash
    python3 -m venv mlcflow
    . mlcflow/bin/activate
    ```
    
=== "Windows"
    ```bash
    python -m venv mlcflow
    mlcflow\Scripts\activate.bat
    ```
    Run as Administrator
    ```bash
    git config --system core.longpaths true
    ```

## Install MLCFlow

If you are not using virtual ENV for installation, the latest `pip` install requires the `--break-system-packages` flag while installing.

```bash
pip install mlcflow mlc-scripts
```

`mlcflow` is the CLI and execution engine; `mlc-scripts` bundles the ~378
MLPerf automation script directories as pip package data. This single command
is everything you need — no git clone happens, and no network access beyond
PyPI is required. See the [Option B migration docs](../migration/index.md) if
you're curious why installation used to look different (a required
`mlc pull repo` step) and no longer does.

!!! note "Only needed if you're forking or actively developing scripts"
    If you maintain your own fork of
    [mlperf-automations](https://github.com/mlcommons/mlperf-automations), or
    you're actively editing scripts and want your local edits to take effect
    instead of the published `mlc-scripts` package's copies, register your
    fork/checkout as an additional repo:
    ```bash
    mlc pull repo <your_github_username>@mlperf-automations
    export MLC_PREFER_DEV_SCRIPTS=1   # let your repo win over the bundled package
    ```
    Most users installing `mlc-scripts` from PyPI don't need this step at all.

Now, you are ready to use the `mlc` commands. Currently, `mlc` is being used to automate the benchmark runs for:

* [MLPerf Inference](https://docs.mlcommons.org/inference/)

