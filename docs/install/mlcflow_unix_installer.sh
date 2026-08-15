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
# Deactivate any active virtual environment so checks use the system Python.
# The installer will activate the correct venv later.
# ------------------------------------------------------------------------------
if [ -n "${VIRTUAL_ENV:-}" ]; then
    ACTIVE_VENV="$VIRTUAL_ENV"
    # 'deactivate' may not be available (e.g. venv is broken), so fall back
    # to manually stripping the venv from PATH.
    if command -v deactivate >/dev/null 2>&1; then
        deactivate 2>/dev/null || true
    fi
    # Ensure the venv bin dir is removed from PATH even if deactivate failed
    PATH="$(echo "$PATH" | tr ':' '\n' | grep -v "^${ACTIVE_VENV}/" | paste -sd: - || true)"
    unset VIRTUAL_ENV
    unset ACTIVE_VENV
fi

# ------------------------------------------------------------------------------
# Default Configuration
# ------------------------------------------------------------------------------

MIN_PYTHON_VERSION="3.7"
DEFAULT_VENV_DIR="$HOME/mlcflow"
DEFAULT_REPO="mlcommons@mlperf-automations"
DEFAULT_BRANCH="main"
PYTHON_CMD="python3"

# What to hand to `pip install` for mlcflow itself. Defaults to the PyPI
# release; override to test an unreleased build, e.g.
#   MLCFLOW_PIP_SPEC="git+https://github.com/mlcommons/mlcflow@some-branch"
MLCFLOW_PIP_SPEC="${MLCFLOW_PIP_SPEC:-mlcflow}"

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
    $QUIET && return 0
    echo -e "${COLOR_GREEN}[INFO]${COLOR_RESET} $1"
}

log_warn() {
    echo -e "${COLOR_YELLOW}[WARN]${COLOR_RESET} $1"
}

log_error() {
    echo -e "${COLOR_RED}[ERROR]${COLOR_RESET} $1"
}

log_debug() {
    $VERBOSE || return 0
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
    "$PYTHON_CMD" -m pip --version >/dev/null 2>&1
}

have_venv_module() {
    "$PYTHON_CMD" -c 'import venv' >/dev/null 2>&1
}

check_missing_dependencies() {
    MISSING_DEPS=()

    command -v git >/dev/null 2>&1 || MISSING_DEPS+=("git")
    command -v curl >/dev/null 2>&1 || MISSING_DEPS+=("curl")
    command -v wget >/dev/null 2>&1 || MISSING_DEPS+=("wget")
    command -v unzip >/dev/null 2>&1 || MISSING_DEPS+=("unzip")

    if ! command -v python3 >/dev/null 2>&1; then
        MISSING_DEPS+=("python3")
    fi
    # Note: pip/venv module checks are deferred to ensure_python() which runs
    # after venv resolution. Checking them here would falsely flag them as
    # missing when a working venv already exists but the system python lacks
    # the modules (they are not needed if the venv is already set up).
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
    if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
        log_warn "Python3 not found."
        handle_python_install
    fi

    if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
        log_error "Python3 is still unavailable after attempted installation."
        exit 1
    fi

    PY_VERSION=$("$PYTHON_CMD" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    PY_MAJOR_MINOR="$(get_python_major_minor_version)"
    PY_ARCH="$(normalize_architecture "$("$PYTHON_CMD" -c 'import platform; print(platform.machine())')")"
    log_info "Detected Python version: $PY_VERSION"
    log_debug "Detected Python major.minor: $PY_MAJOR_MINOR"
    log_debug "Detected Python architecture: $PY_ARCH"

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

normalize_architecture() {
    local architecture="${1:-$(uname -m)}"

    case "$architecture" in
        x86_64|amd64)
            echo "x86_64"
            ;;
        aarch64|arm64)
            echo "aarch64"
            ;;
        *)
            echo "$architecture"
            ;;
    esac
}

get_python_major_minor_version() {
    "$PYTHON_CMD" -c 'import sys; print("{}.{}".format(sys.version_info[0], sys.version_info[1]))'
}

# $1 should be a Python executable (for example python3 or <venv>/bin/python).
# Returns a compatibility signature in the format architecture|major.minor
# (for example x86_64|3.11).
get_python_compatibility_signature() {
    "$1" -c 'import platform, sys; print("{}|{}.{}".format(platform.machine(), sys.version_info[0], sys.version_info[1]))' 2>/dev/null
}

get_venv_suffix() {
    "$PYTHON_CMD" -c 'import platform, sys; print("_{}_py{}.{}".format(platform.machine(), sys.version_info[0], sys.version_info[1]))'
}

is_compatible_venv() {
    local venv_dir="$1"
    local venv_python="$venv_dir/bin/python3"
    local current_signature
    local venv_signature

    if [ ! -x "$venv_python" ]; then
        venv_python="$venv_dir/bin/python"
    fi
    if [ ! -x "$venv_python" ]; then
        return 1
    fi

    # Verify the venv python is actually functional (not broken/dangling)
    if ! "$venv_python" -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        log_debug "Virtual environment python at $venv_python is broken."
        return 1
    fi

    # Verify pip is functional inside the venv
    if ! "$venv_python" -m pip --version >/dev/null 2>&1; then
        log_debug "Virtual environment at $venv_dir has broken or missing pip."
        return 1
    fi

    if ! current_signature="$(get_python_compatibility_signature "$PYTHON_CMD")"; then
        log_debug "Failed to determine compatibility signature for $PYTHON_CMD."
        return 1
    fi
    if ! venv_signature="$(get_python_compatibility_signature "$venv_python")"; then
        log_debug "Failed to determine compatibility signature for $venv_python."
        return 1
    fi

    [ "$venv_signature" = "$current_signature" ]
}

resolve_venv_dir() {
    local requested_venv_dir="$1"
    local resolved_venv_dir="$requested_venv_dir"
    local compatible_venv_dir="${requested_venv_dir}$(get_venv_suffix)"

    if [ -d "$requested_venv_dir" ]; then
        if is_compatible_venv "$requested_venv_dir"; then
            echo "$resolved_venv_dir"
            return
        fi

        # Default venv exists but is broken or incompatible — try the
        # platform/python-versioned alternative
        log_debug "Virtual environment at $requested_venv_dir is broken or incompatible." >&2
        resolved_venv_dir="$compatible_venv_dir"
        if [ -d "$resolved_venv_dir" ]; then
            if is_compatible_venv "$resolved_venv_dir"; then
                echo "$resolved_venv_dir"
                return
            fi
            log_warn "Removing stale/incompatible virtual environment: $resolved_venv_dir" >&2
            rm -rf "$resolved_venv_dir"
        fi
        echo "$resolved_venv_dir"
        return
    fi

    if [ -d "$compatible_venv_dir" ] && is_compatible_venv "$compatible_venv_dir"; then
        resolved_venv_dir="$compatible_venv_dir"
    fi

    echo "$resolved_venv_dir"
}

is_venv_compatible() {
    is_compatible_venv "$1"
}

resolve_default_venv_dir() {
    local shared_venv_dir="${DEFAULT_VENV_DIR}$(get_venv_suffix)"

    VENV_DIR="$(resolve_venv_dir "$DEFAULT_VENV_DIR")"

    if [ "$VENV_DIR" = "$DEFAULT_VENV_DIR" ] && [ -d "$DEFAULT_VENV_DIR" ]; then
        log_info "Reusing default virtual environment: $DEFAULT_VENV_DIR"
        return
    fi

    if [ "$VENV_DIR" != "$DEFAULT_VENV_DIR" ]; then
        if [ -d "$DEFAULT_VENV_DIR" ]; then
            log_warn "Default virtual environment is incompatible with Python ${PY_MAJOR_MINOR} (${PY_ARCH})."
        fi
        if [ "$VENV_DIR" = "$shared_venv_dir" ] && [ -d "$shared_venv_dir" ]; then
            log_info "Reusing platform/python-specific virtual environment: $VENV_DIR"
        else
            log_info "Using platform/python-specific virtual environment: $VENV_DIR"
        fi
    fi
}

setup_venv() {
    local requested_venv_dir="$VENV_DIR"
    VENV_DIR="$(resolve_venv_dir "$VENV_DIR")"
    log_info "Setting up virtual environment at: $VENV_DIR"
    if [ "$VENV_DIR" != "$requested_venv_dir" ]; then
        log_warn "Virtual environment at $requested_venv_dir is incompatible with current Python/platform. Using $VENV_DIR instead."
    fi

    if [ -d "$VENV_DIR" ] && is_compatible_venv "$VENV_DIR"; then
        log_info "Reusing existing virtual environment."
    else
        "$PYTHON_CMD" -m venv "$VENV_DIR"
    fi

    # Activate venv
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
}

# ------------------------------------------------------------------------------
# Install / Upgrade MLCFlow
# ------------------------------------------------------------------------------

install_mlcflow() {
    if "$PYTHON_CMD" -m pip show mlcflow >/dev/null 2>&1; then
        if $UPGRADE; then
            log_info "Upgrading mlcflow (${MLCFLOW_PIP_SPEC})..."
            "$PYTHON_CMD" -m pip install --upgrade "$MLCFLOW_PIP_SPEC"
        else
            log_info "mlcflow already installed. Skipping."
        fi
    else
        log_info "Installing mlcflow (${MLCFLOW_PIP_SPEC})..."
        "$PYTHON_CMD" -m pip install "$MLCFLOW_PIP_SPEC"
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
    log_info "  Branch : ${MLC_BRANCH:-(default)}"

    # Initialize the command array with base arguments
    local cmd=(mlc pull repo "${MLC_REPO}")

    # Append the checkout flag only if MLC_BRANCH is not empty
    if [ -n "${MLC_BRANCH}" ]; then
        cmd+=(--checkout="${MLC_BRANCH}")
    fi

    # Execute the command array safely
    "${cmd[@]}"
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

    # If a compatible venv already exists at the target path, we can skip
    # the pip/venv system-package requirement — just activate and go.
    local target_venv
    target_venv="$(resolve_venv_dir "$VENV_DIR")"
    if [ -d "$target_venv" ] && is_compatible_venv "$target_venv"; then
        log_info "Found working virtual environment at: $target_venv"
        VENV_DIR="$target_venv"
        # shellcheck disable=SC1090
        source "$VENV_DIR/bin/activate"
    else
        # We need pip and venv to create a new environment
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
        setup_venv
    fi

    install_mlcflow

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

if [[ "${BASH_SOURCE[0]:-$0}" == "$0" ]]; then
    main
fi
