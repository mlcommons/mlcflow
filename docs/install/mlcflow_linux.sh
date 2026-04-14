#!/usr/bin/env bash
# ==============================================================================
# MLCFlow Generic Installer (v1)
# Supports:
#   - Ubuntu 20.04+
#   - RHEL family (RHEL, Alma, CentOS Stream)
#   - macOS (with Homebrew)
#   - x86_64 and aarch64

# Exit if a command fails
# Treats unset variables as errors
# Makes pipeline fails if any command fails
set -euo pipefail

# ------------------------------------------------------------------------------
# Default Configuration
# ------------------------------------------------------------------------------

MIN_PYTHON_VERSION="3.7"
DEFAULT_VENV_DIR="$HOME/.mlcflow_venv"
DEFAULT_REPO="mlcommons@mlperf-automations"
DEFAULT_BRANCH="dev"

UPGRADE=false
ASSUME_YES=false
INSTALL_PYTHON=false
VERBOSE=false
QUIET=false
VENV_DIR="$DEFAULT_VENV_DIR"
MLC_REPO="$DEFAULT_REPO"
MLC_BRANCH="$DEFAULT_BRANCH"

# ------------------------------------------------------------------------------
# Logging System
# ------------------------------------------------------------------------------

INTERACTIVE=false
# checks if the stdout connected to a terminal
if [ -t 1 ]; then
    INTERACTIVE=true
fi

if $INTERACTIVE; then
    COLOR_RED="\033[0;31m"
    COLOR_GREEN="\033[0;32m"
    COLOR_YELLOW="\033[1;33m"
    COLOR_BLUE="\033[0;34m"
    COLOR_RESET="\033[0m"
else
    COLOR_RED=""
    COLOR_GREEN=""
    COLOR_YELLOW=""
    COLOR_BLUE=""
    COLOR_RESET=""
fi

log_info() {
    $QUIET && return
    echo -e "${COLOR_GREEN}[INFO]${COLOR_RESET} $1"
}

log_warn() {
    echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $1"
}

log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $1"
}

log_debug() {
    $VERBOSE || return
    echo -e "${COLOR_BLUE}[DEBUG]${COLOR_RESET} $1"
}

# ------------------------------------------------------------------------------
# Usage
# ------------------------------------------------------------------------------

usage() {
cat <<EOF
MLCFlow Installer

Options:
  --yes                   Auto-confirm prompts
  --upgrade               Upgrade mlcflow if already installed
  --venv-dir <path>       Custom virtual environment path
  --mlc-repo <repo>       Override automation repo
  --mlc-repo-branch <b>   Override repo branch
  --install-python        Auto-install Python if incompatible
  --verbose               Enable debug logs
  --quiet                 Minimal output
  --help                  Show this help

EOF
exit 0
}

# ------------------------------------------------------------------------------
# Argument Parsing
# ------------------------------------------------------------------------------

# Loops through the arguments provided
# If an option expects a value after it, reads it and skips for next iteration
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) ASSUME_YES=true ;;
        --upgrade) UPGRADE=true ;;
        --venv-dir) VENV_DIR="$2"; shift ;;
        --mlc-repo) MLC_REPO="$2"; shift ;;
        --mlc-repo-branch) MLC_BRANCH="$2"; shift ;;
        --install-python) INSTALL_PYTHON=true ;;
        --verbose) VERBOSE=true ;;
        --quiet) QUIET=true ;;
        --help) usage ;;
        *) log_error "Unknown argument: $1"; exit 1 ;;
    esac
    shift
done

# ------------------------------------------------------------------------------
# Detect OS and Package Manager
# ------------------------------------------------------------------------------

detect_os() {
    if [ "$(uname)" = "Darwin" ]; then
        OS_ID="macos"
        OS_VERSION="$(sw_vers -productVersion 2>/dev/null || echo unknown)"
    else
        if [ ! -f /etc/os-release ]; then
            log_error "Cannot detect operating system."
            exit 1
        fi
        # loads the content from os-release as variables
        source /etc/os-release
        OS_ID="$ID"
        OS_VERSION="$VERSION_ID"
    fi

    case "$OS_ID" in
        ubuntu|debian)
            PKG_MANAGER="apt"
            ;;
        rhel|rocky|almalinux|centos)
            if command -v dnf >/dev/null 2>&1; then
                PKG_MANAGER="dnf"
            else
                PKG_MANAGER="yum"
            fi
            ;;
        macos)
            PKG_MANAGER="brew"
            ;;
        *)
            log_error "Unsupported OS: $OS_ID"
            exit 1
            ;;
    esac

    log_info "Detected OS: $OS_ID $OS_VERSION"
    log_info "Using package manager: $PKG_MANAGER"
}

# ------------------------------------------------------------------------------
# Privilege Detection
# ------------------------------------------------------------------------------

# Handles the following cases:
# 1. If the script is already running as root (EUID=0), commands can be executed directly.
# 2. If the script is not running as root but the `sudo` command is available,
#    privileged commands will be executed using sudo.
# 3. If neither root privileges nor sudo are available, the script will fail
#    when attempting to run commands that require elevated permissions.
if [ "$EUID" -eq 0 ]; then
    USE_SUDO=false
elif command -v sudo >/dev/null 2>&1; then
    USE_SUDO=true
else
    USE_SUDO=false
fi

run_root() {
    if $USE_SUDO; then
        sudo "$@"
    elif [ "$EUID" -eq 0 ]; then
        "$@"
    else
        log_error "Root or sudo required to install system dependencies."
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# System Dependencies
# ------------------------------------------------------------------------------

require_root_if_needed() {
    if [ "$PKG_MANAGER" = "brew" ]; then
        return
    fi

    if [ "$EUID" -ne 0 ] && ! $USE_SUDO; then
        log_error "Root or sudo required to install missing dependencies."
        exit 1
    fi
}

have_pip_module() {
    python3 -m pip --version >/dev/null 2>&1
}

have_venv_module() {
    python3 -c 'import venv' >/dev/null 2>&1
}

check_missing_dependencies() {
    MISSING_DEPS=()

    command -v git >/dev/null 2>&1 || MISSING_DEPS+=("git")
    command -v curl >/dev/null 2>&1 || MISSING_DEPS+=("curl")
    command -v wget >/dev/null 2>&1 || MISSING_DEPS+=("wget")
    command -v unzip >/dev/null 2>&1 || MISSING_DEPS+=("unzip")

    if ! command -v python3 >/dev/null 2>&1; then
        MISSING_DEPS+=("python3")
    else
        have_pip_module || MISSING_DEPS+=("python3-pip")
        have_venv_module || MISSING_DEPS+=("python3-venv")
    fi
}

install_packages() {
    log_info "Installing system dependencies..."

    case "$PKG_MANAGER" in
        apt)
            require_root_if_needed
            run_root apt update
            run_root apt install -y python3 python3-pip python3-venv git curl wget unzip
            ;;
        yum|dnf)
            require_root_if_needed
            # RHEL-family images may ship curl-minimal and conflict with curl package.
            run_root "$PKG_MANAGER" install -y python3 python3-pip git curl-minimal wget unzip
            # Some RHEL-family variants package venv separately
            run_root "$PKG_MANAGER" install -y python3-venv >/dev/null 2>&1 || true
            ;;
        brew)
            if ! command -v brew >/dev/null 2>&1; then
                log_error "Homebrew is required on macOS. Please install it from https://brew.sh"
                exit 1
            fi
            brew update
            brew install python git curl wget unzip
            ;;
    esac
}

# ------------------------------------------------------------------------------
# Python Validation
# ------------------------------------------------------------------------------

version_ge() {
    [ "$(printf '%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

ensure_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        log_warn "Python3 not found."
        handle_python_install
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        log_error "Python3 is still unavailable after attempted installation."
        exit 1
    fi

    PY_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    log_info "Detected Python version: $PY_VERSION"

    if version_ge "$PY_VERSION" "$MIN_PYTHON_VERSION"; then
        log_info "Python version is compatible."
    else
        log_warn "Python version < $MIN_PYTHON_VERSION"
        handle_python_install
    fi

    if ! have_pip_module; then
        log_warn "python3 pip module is missing. Installing..."
        install_packages
    fi

    if ! have_venv_module; then
        log_warn "python3 venv module is missing. Installing..."
        install_packages
    fi

    if ! have_pip_module || ! have_venv_module; then
        log_error "pip/venv modules are still missing after attempted installation."
        exit 1
    fi
}

handle_python_install() {
    if $INSTALL_PYTHON || $ASSUME_YES; then
        install_packages
        return
    fi

    if ! $INTERACTIVE; then
        log_error "Incompatible Python and non-interactive mode. Run with --install-python to automatically install."
        exit 1
    fi

    read -p "Install compatible Python? [y/N]: " response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        install_packages
    else
        log_error "Cannot proceed without compatible Python."
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# Virtual Environment
# ------------------------------------------------------------------------------

setup_venv() {
    log_info "Setting up virtual environment at: $VENV_DIR"

    if [ -d "$VENV_DIR" ]; then
        log_info "Reusing existing virtual environment."
    else
        python3 -m venv "$VENV_DIR"
    fi

    # Activate venv
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
}

# ------------------------------------------------------------------------------
# Install / Upgrade MLCFlow
# ------------------------------------------------------------------------------

install_mlcflow() {
    if python3 -m pip show mlcflow >/dev/null 2>&1; then
        if $UPGRADE; then
            log_info "Upgrading mlcflow..."
            python3 -m pip install --upgrade mlcflow
        else
            log_info "mlcflow already installed. Skipping."
        fi
    else
        log_info "Installing mlcflow..."
        python3 -m pip install mlcflow
    fi
}

# ------------------------------------------------------------------------------
# Pull Automation Repo
# ------------------------------------------------------------------------------

prompt_repo_details() {
    if ! $INTERACTIVE || $ASSUME_YES; then
        return
    fi

    read -r -p "Automation repo [${MLC_REPO}]: " repo_input
    if [ -n "${repo_input}" ]; then
        MLC_REPO="${repo_input}"
    fi

    read -r -p "Automation branch [${MLC_BRANCH}]: " branch_input
    if [ -n "${branch_input}" ]; then
        MLC_BRANCH="${branch_input}"
    fi
}

pull_repo() {
    log_info "Pulling automation repo:"
    log_info "  Repo   : ${MLC_REPO}"
    log_info "  Branch : ${MLC_BRANCH}"

    mlc pull repo "${MLC_REPO}" --branch="${MLC_BRANCH}"
}

# ------------------------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------------------------

main() {
    detect_os
    check_missing_dependencies
    if [ "${#MISSING_DEPS[@]}" -gt 0 ]; then
        log_warn "Missing dependencies: ${MISSING_DEPS[*]}"
        install_packages
    else
        log_info "All base dependencies are present."
    fi

    ensure_python
    setup_venv
    install_mlcflow
    prompt_repo_details
    pull_repo

    log_info "Installation completed successfully."
    echo ""
    echo "Virtual environment:"
    echo "  $VENV_DIR"
    echo ""
    echo "Activate with:"
    echo "  source $VENV_DIR/bin/activate"
    echo ""
    echo "Verify:"
    echo "  mlc --help"
}

main
