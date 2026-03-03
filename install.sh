#!/usr/bin/env bash
set -euo pipefail

LFP_BUILD_REPO_URL_DEFAULT="https://github.com/regbo/lfp-build-py.git"
# NOTE: The package metadata name is "lfp-build" (not "lfp-build-py").
LFP_BUILD_SPEC_DEFAULT="lfp-build @ git+${LFP_BUILD_REPO_URL_DEFAULT}"

ensure_home() {
  if [ -n "${HOME:-}" ] && [ -d "${HOME}" ]; then
    return 0
  fi

  for candidate in /home/app /home; do
    if [ -d "${candidate}" ]; then
      export HOME="${candidate}"
      return 0
    fi
  done

  export HOME="/tmp/home"
  mkdir -p "${HOME}"
}

ensure_bin_path() {
  mkdir -p "${HOME}/.local/bin"
  case ":${PATH}:" in
    *":${HOME}/.local/bin:"*) ;;
    *) export PATH="${HOME}/.local/bin:${PATH}" ;;
  esac
}

ensure_tool_bin_path() {
  if ! command -v uv >/dev/null 2>&1; then
    return 0
  fi
  local tool_bin
  tool_bin="$(uv tool dir --bin 2>/dev/null || true)"
  if [ -n "${tool_bin}" ]; then
    case ":${PATH}:" in
      *":${tool_bin}:"*) ;;
      *) export PATH="${tool_bin}:${PATH}" ;;
    esac
  fi
}

install_pixi() {
  if command -v pixi >/dev/null 2>&1; then
    return 0
  fi

  # Install pixi into $HOME/.local/bin without modifying shell startup files.
  curl -fsSL https://pixi.sh/install.sh | bash
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi

  curl -LsSf https://astral.sh/uv/install.sh | sh

  # uv installs to $HOME/.cargo/bin by default
  if [ -d "${HOME}/.cargo/bin" ]; then
    export PATH="${HOME}/.cargo/bin:${PATH}"
  fi
}

install_git() {
  if command -v git >/dev/null 2>&1; then
    return 0
  fi
  if ! command -v pixi >/dev/null 2>&1; then
    return 1
  fi

  # Install git via pixi global tools. With PIXI_HOME set to $HOME/.local,
  # binaries land in $HOME/.local/bin.
  pixi global install --channel conda-forge git
}

install_lfp_build() {
  local spec="${LFP_BUILD_SPEC:-${LFP_BUILD_SPEC_DEFAULT}}"
  uv tool install "${spec}"
}

activate_pixi_shell_hook() {
  if ! command -v pixi >/dev/null 2>&1; then
    return 0
  fi

  # Best-effort activation. Note: if you run this script via `curl | bash`,
  # the activation only affects this process. To persist, source the script:
  #   source ./install.sh
  if pixi shell-hook --shell bash >/dev/null 2>&1; then
    # shellcheck disable=SC1090
    eval "$(pixi shell-hook --shell bash)"
  fi
}

ensure_home
ensure_bin_path

# Keep pixi installs and pixi global tools in the same place.
export PIXI_HOME="${PIXI_HOME:-${HOME}/.local}"
export PIXI_BIN_DIR="${PIXI_BIN_DIR:-${HOME}/.local/bin}"
export PIXI_NO_PATH_UPDATE="${PIXI_NO_PATH_UPDATE:-1}"

install_pixi
install_uv
ensure_tool_bin_path
install_git
install_lfp_build
activate_pixi_shell_hook

echo "lfp-build is installed. Try: lfp-build --help"
echo "If 'lfp-build' is not found, add these to PATH:"
echo "  export PATH=\"${HOME}/.local/bin:$(command -v uv >/dev/null 2>&1 && uv tool dir --bin 2>/dev/null || true):\$PATH\""

