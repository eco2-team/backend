#!/usr/bin/env bash

# Ensure shell exits on error or unset variables.
set -euo pipefail

# Resolve cert bundle path up front to avoid repeating costly python invocations.
_ca_bundle_path() {
  if [[ -n "${SSL_CERT_FILE:-}" ]]; then
    printf "%s" "${SSL_CERT_FILE}"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import certifi; print(certifi.where())"
    return
  fi

  echo "python3 is required to locate the certifi CA bundle" >&2
  exit 1
}

CA_BUNDLE="$(_ca_bundle_path)"

export SSL_CERT_FILE="${CA_BUNDLE}"
export REQUESTS_CA_BUNDLE="${CA_BUNDLE}"
export GIT_SSL_CAINFO="${CA_BUNDLE}"

echo "[ca-env] Exported SSL_CERT_FILE, REQUESTS_CA_BUNDLE, and GIT_SSL_CAINFO -> ${CA_BUNDLE}"
