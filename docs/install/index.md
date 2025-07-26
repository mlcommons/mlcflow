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

## Install MLCFLow

If you are not using virtual ENV for installation, the latest `pip` install requires the `--break-system-packages` flag while installing.

```bash
pip install mlcflow
```
## Pull the Automation Repo
```bash
mlc pull repo mlcommons@mlperf-automations
```
* If you are forking https://github.com/mlcommons/mlperf-automations you can substitute the above command by `mlc pull repo <your_github_username>@mlperf-automations`.
   
!!! tip
    If you want to pull the latest changes (recommended), please do `mlc pull repo` periodically.


Now, you are ready to use the `mlc` commands. Currently, `mlc` is being used to automate the benchmark runs for:

* [MLPerf Inference](https://docs.mlcommons.org/inference/)

