# MLCFlow Unix Installer

A Bootstrap installer for MLCFlow that automatically detects your Unix-based operating system (Linux/macOS), installs required dependencies, sets up a Python virtual environment, and configures the MLCFLow automation framework.

> **Platform Note**: This installer is designed for **Unix-based systems only** (Linux distributions and macOS). It does not support Windows. Windows users should use WSL2 (Windows Subsystem for Linux) or a Linux virtual machine. We plan to release an installer script for Windows soon.

## Purpose

This installer provides a **one-command setup** for the MLCFlow package and the MLPerf automation repository. It handles all the complexity of:
- Detecting your Linux distribution or macOS
- Automatically detecting and using sudo when needed
- Installing missing system packages
- Validating Python installation and version
- Setting up isolated Python environments
- Installing MLCFlow and its dependencies
- Cloning the automation repository

**After installation, activate the virtual environment** to use MLCFlow commands:
```bash
source ~/.mlcflow_venv/bin/activate
```

## Supported Platforms

### Linux Distributions
- **Ubuntu**: 20.04, 22.04, 24.04 LTS
- **Debian**: 10+ (any version with Python 3.7+)
- **Rocky Linux**: 9.x
- **AlmaLinux**: 9.x
- **CentOS Stream**: 9
- **RHEL**: 9+ (Red Hat Enterprise Linux)

### macOS
- **macOS**: 11+ (Big Sur and later)
- **Requirement**: Homebrew must be installed

### Architecture
- **x86_64** (amd64)
- **aarch64** (arm64)

### Python Version
- **Minimum**: Python 3.7
- **Recommended**: Python 3.8+

> **Note**: RHEL/Rocky Linux 8 ships with Python 3.6 by default, which is below the minimum requirement. Users should install Python 3.8+ from AppStream modules or alternative sources.

## Installation Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Detect Operating System & Package Manager               │
│    ├─ Ubuntu/Debian    → apt                               │
│    ├─ RHEL/Rocky/Alma  → dnf/yum                           │
│    └─ macOS            → brew                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Check System Dependencies                               │
│    - git, curl/curl-minimal, wget, unzip                   │
│    - python3, python3-pip, python3-venv                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Install Missing Dependencies                            │
│    - Uses detected package manager                         │
│    - Requests sudo/root privileges if needed               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Validate Python Environment                             │
│    - Check Python version (≥ 3.7)                          │
│    - Verify pip module availability                        │
│    - Verify venv module availability                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Create Virtual Environment                              │
│    - Location: ~/.mlcflow_venv (or custom)                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Install MLCFlow Package                                 │
│    - Install mlcflow via pip                               │
│    - Install all dependencies                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Prompt for Repository Details (if interactive)          │
│    - Repo name (default: mlcommons@mlperf-automations)     │
│    - Branch (default: dev)                                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Clone Automation Repository                             │
│    - Uses 'mlc pull repo' command                          │
│    - Stored in ~/MLC/repos/ (mlc default location)         │
└─────────────────────────────────────────────────────────────┘
                              ↓
                      ✅ Installation Complete
```

## Usage

### Basic Installation (Interactive)
```bash
bash mlcflow_linux.sh
```
Prompts for repository name and branch, then proceeds with installation.

### Automated Installation (Non-Interactive)
```bash
bash mlcflow_linux.sh --yes
```
Uses all default values without prompting.

### Custom Virtual Environment Location
```bash
bash mlcflow_linux.sh --yes --venv-dir /opt/mlcflow_env
```

### Custom Repository and Branch
```bash
bash mlcflow_linux.sh \
  --yes \
  --mlc-repo myorganization@my-mlperf-fork \
  --mlc-repo-branch feature-branch
```

### Upgrade Existing Installation
```bash
bash mlcflow_linux.sh --yes --upgrade
```

### Verbose Mode (Debugging)
```bash
bash mlcflow_linux.sh --yes --verbose
```

### Quiet Mode (Minimal Output)
```bash
bash mlcflow_linux.sh --yes --quiet
```

## Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--yes` | Auto-confirm all prompts (non-interactive mode) | Interactive |
| `--upgrade` | Upgrade mlcflow if already installed | Skip if present |
| `--venv-dir <path>` | Custom virtual environment directory | `~/.mlcflow_venv` |
| `--mlc-repo <repo>` | Repository in format `owner@repo` | `mlcommons@mlperf-automations` |
| `--mlc-repo-branch <branch>` | Git branch to clone | `dev` |
| `--install-python` | Auto-install Python if incompatible | Prompt user |
| `--verbose` | Enable debug logging | Normal logging |
| `--quiet` | Minimal output (errors/warnings only) | Normal logging |
| `--help` | Display help message and exit | - |

## SUDO and Privilege Handling

The installer automatically detects your privilege level and handles system package installation accordingly. **You do not need to explicitly specify sudo** - the script handles it internally.

### How the Script Detects Privileges

When you run the script, it automatically checks:
1. **Are you running as root?** (EUID == 0)
2. **Is the `sudo` command available?**
3. **What package manager is being used?**

Based on this detection, it chooses the appropriate execution method.


### Privilege Detection Logic
```bash
# The installer detects privileges in this order:
1. Check if running as root (EUID == 0)
2. Check if 'sudo' command is available
3. For package managers:
   - apt/yum/dnf: Require root or sudo
   - brew (macOS): No sudo needed
4. For Python operations: No privileges required (user-space)
```

### Summary: What Requires Privileges?

| Operation | Requires Root/Sudo |
|-----------|-------------------|
| Install system packages | Yes |
| Install system packages | Yes |
| Install system packages |
| Create Python venv | No |
| Install pip packages | No |
| Clone git repositories | No |

## What Gets Installed

### System Packages
**Ubuntu/Debian**:
- `python3`, `python3-pip`, `python3-venv`
- `git`, `curl`, `wget`, `unzip`

**RHEL/Rocky/Alma/CentOS**:
- `python3`, `python3-pip`, `python3-venv`
- `git`, `curl-minimal`, `wget`, `unzip`

> **Note**: Uses `curl-minimal` on RHEL systems to avoid package conflicts with pre-installed `curl-minimal`.

**macOS (via Homebrew)**:
- `python`, `git`, `curl`, `wget`, `unzip`

### Python Packages (in virtual environment)
- `mlcflow` - Main automation CLI
- `requests` - HTTP library
- `pyyaml` - YAML parser
- `giturlparse` - Git URL utilities
- `colorama` - Cross-platform colored terminal output

### Automation Repository
- Cloned via `mlc pull repo` command
- Default location: `~/MLC/repos/mlcommons@mlperf-automations/`
- Contains MLPerf automation scripts and configurations

## Post-Installation

### Activate Virtual Environment (Required)

**Important**: To use MLCFlow commands, you must activate the virtual environment:

```bash
# Activate the virtual environment
source ~/.mlcflow_venv/bin/activate

# Your prompt should change to show (mlcflow_venv) or similar
```

### Verify Installation
```bash
# After activating the virtual environment:
mlc --help

# Verify version
mlc version

# List available scripts
mlc list scripts
```

### Deactivate Virtual Environment
```bash
# When you're done working with MLCFlow
deactivate
```

### File Locations
- **Virtual Environment**: `~/.mlcflow_venv` (or custom path)
- **Automation Repository**: `~/MLC/repos/mlcommons@mlperf-automations/`
- **MLC Cache**: `~/MLC/repos/`

## Troubleshooting

### "Python version < 3.7"
**Problem**: System Python is too old (e.g., Python 3.6 on RHEL 8)

**Solution**:
```bash
# RHEL 8 / Rocky 8
sudo dnf module install python38
# or
sudo dnf install python39

# Then rerun installer
bash mlcflow_linux.sh --yes
```

### "mlc: command not found" after installation
**Problem**: Virtual environment is not activated

**Solution**:
```bash
# Activate the virtual environment
source ~/.mlcflow_venv/bin/activate

# Now mlc command should be available
mlc --help
```

### Package conflicts on RHEL/Rocky
**Problem**: `curl` and `curl-minimal` conflict

**Solution**: The installer now uses `curl-minimal` automatically. If you encounter issues:
```bash
# Remove conflicting package
sudo dnf remove curl

# Rerun installer
bash mlcflow_linux.sh --yes
```

### "Homebrew not found" on macOS
**Problem**: Homebrew is not installed

**Solution**:
```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Rerun installer
bash mlcflow_linux.sh --yes
```

### Permission denied errors
**Problem**: Missing sudo privileges and required packages are not installed

**Solution**:
```bash
# If you don't have sudo AND packages are missing
# Ask your system administrator to install these packages:
# - Ubuntu/Debian: python3 python3-pip python3-venv git curl wget unzip
# - RHEL/Rocky: python3 python3-pip python3-venv git curl-minimal wget unzip
# Then run:
bash mlcflow_linux.sh --yes
```

### Virtual environment creation fails
**Problem**: `python3-venv` module missing

**Solution**: The installer should detect and install it, but if manual installation is needed:
```bash
# Ubuntu/Debian
sudo apt install python3-venv

# RHEL/Rocky
sudo dnf install python3-venv

# Rerun installer
bash mlcflow_linux.sh --yes
```

## Testing and CI

### Automated Testing

The installer is continuously tested via GitHub Actions across all supported platforms using the exact distribution method that users will use in production (`curl <url>/mlcflow_linux.sh | bash`). The CI workflow validates:

- **Operating Systems**: Ubuntu 20.04/22.04/24.04, macOS 13, Debian 11/12, Rocky Linux 9, AlmaLinux 9, CentOS Stream 9

### Known Testing Limitations

**TODO**: The CI workflow currently only tests **non-interactive mode** (with `--yes` flag). The interactive installation path, which prompts users for repository name and branch, is not covered by automated tests.

If you discover issues with interactive mode, please report them via GitHub Issues [here](https://github.com/mlcommons/mlcflow/issues).

## Support

For issues, feature requests, or contributions:
- **Repository**: https://github.com/mlcommons/mlperf-automations
- **Issues**: https://github.com/mlcommons/mlperf-automations/issues
- **Documentation**: https://mlcommons.github.io/mlperf-automations/

## License

This installer script is part of the MLPerf Automations project and is distributed under the same license as the main project.

## Changelog

### v1.0 (Current)
- Initial release with comprehensive OS support (Linux/macOS)
- Automatic dependency detection and installation
- pip/venv module validation
- Automatic sudo detection and privilege handling
- macOS support with Homebrew
- Interactive and non-interactive modes
- RHEL package conflict resolution (curl-minimal)
- Manual virtual environment activation required

---
