set -euo pipefail

NVM_RUNTIME_DIR="${NVM_DIR:-$HOME/nvm}"

if [[ -s "$NVM_RUNTIME_DIR/nvm.sh" ]]; then
  unset npm_config_prefix
  # shellcheck source=/dev/null
  source "$NVM_RUNTIME_DIR/nvm.sh"
  nvm use --silent
fi

export PATH="${NVM_BIN:-/usr/local/bin}:/opt/homebrew/bin:$PATH"
export RUSTC="/opt/homebrew/bin/rustc"
export RUSTDOC="/opt/homebrew/bin/rustdoc"

exec "$@"
