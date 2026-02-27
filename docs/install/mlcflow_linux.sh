#!/usr/bin/env bash
# ==============================================================================
# MLCFlow Generic Installer (v1)
# Supports:
#   - Ubuntu 20.04+
#   - RHEL family (RHEL, Rocky, Alma, CentOS Stream)
#   - x86_64 and aarch64

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
    if [ ! -f /etc/os-release ]; then
        log_error "Cannot detect operating system."
        exit 1
    fi

    source /etc/os-release
    OS_ID="$ID"
    OS_VERSION="$VERSION_ID"

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

if [ "$EUID" -eq 0 ]; then
    USE_SUDO=false
else
    if command -v sudo >/dev/null 2>&1; then
        USE_SUDO=true
    else
        log_error "Root or sudo required to install system dependencies."
        exit 1
    fi
fi

run_root() {
    if $USE_SUDO; then
        sudo "$@"
    else
        "$@"
    fi
}

# ------------------------------------------------------------------------------
# System Dependencies
# ------------------------------------------------------------------------------

install_packages() {
    log_info "Installing system dependencies..."

    if [ "$PKG_MANAGER" = "apt" ]; then
        run_root apt update
        run_root apt install -y python3 python3-venv python3-pip git curl
    else
        run_root "$PKG_MANAGER" install -y python3 python3-pip git curl
    fi
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
        return
    fi

    PY_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    log_info "Detected Python version: $PY_VERSION"

    if version_ge "$PY_VERSION" "$MIN_PYTHON_VERSION"; then
        log_info "Python version is compatible."
    else
        log_warn "Python version < $MIN_PYTHON_VERSION"
        handle_python_install
    fi
}

handle_python_install() {
    if $INSTALL_PYTHON || $ASSUME_YES; then
        install_packages
        return
    fi

    if ! $INTERACTIVE; then
        log_error "Incompatible Python and non-interactive mode."
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

    pip install --upgrade pip
}

# ------------------------------------------------------------------------------
# Install / Upgrade MLCFlow
# ------------------------------------------------------------------------------

install_mlcflow() {
    if pip show mlcflow >/dev/null 2>&1; then
        if $UPGRADE; then
            log_info "Upgrading mlcflow..."
            pip install --upgrade mlcflow
        else
            log_info "mlcflow already installed. Skipping."
        fi
    else
        log_info "Installing mlcflow..."
        pip install mlcflow
    fi
}

# ------------------------------------------------------------------------------
# Pull Automation Repo
# ------------------------------------------------------------------------------

pull_repo() {
    log_info "Pulling automation repo:"
    log_info "  Repo   : ${MLC_REPO}"
    log_info "  Branch : ${MLC_BRANCH}"

    # Using correct CLI format:
    # mlc pull repo <repo_owner>@<repo_name> --branch <repo_branch>
    mlc pull repo ${MLC_REPO} --branch=${MLC_BRANCH}
}

# ------------------------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------------------------

main() {
    detect_os
    ensure_python
    setup_venv
    install_mlcflow
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
