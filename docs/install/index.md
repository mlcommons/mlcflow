---
hide:
  - toc
---

# Installation

## Dependencies
MLCFlow needs `python>=3.7`, `python3-pip`, `python3-venv` and `git` installed on your system.

=== "Ubuntu"
    ```bash
    sudo apt-get install -y python3-dev python3-venv python3-pip git wget sudo unzip
    ```
=== "RedHat"
    ```bash
    sudo dnf install -y python3-dev python3-pip git wget sudo unzip binutils
    ```
=== "Arch"
    ```bash
    sudo pacman -Sy python python-pip git wget sudo binutils
    ```
=== "macOS"
    ```bash
    brew install python git wget binutils
    ```
=== "Windows"
    
    TBD
    

    


## Activate a Virtual ENV for MLCFlow (Optional)
This step is not mandatory. But the latest `pip` install requires this or else will need the `--break-system-packages` flag while installing.

```bash
python3 -m venv mlcflow
source mlcflow/bin/activate
```

## Install MLCFLow

If you are not using virtual ENV for installation, the latest `pip` install requires the `--break-system-packages` flag while installing.

```bash
   pip install mlcflow
```

> [!IMPORTANT]  
> If you want to pull the latest changes (recommended), please do `mlc pull repo` after the installation.


Now, you are ready to use the `mlc` commands. Currently, `mlc` is being used to automate the benchmark runs for:

* [MLPerf Inference](https://docs.mlcommons.org/inference/)

