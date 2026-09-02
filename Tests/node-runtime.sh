#!/bin/sh

# Resolve the Node.js runtime used by JavaScript-backed repository checks.
# Callers may provide an absolute path through TERENTO_NODE_BIN; CI and local
# shells can otherwise use node or nodejs from PATH.

if [ -n "${TERENTO_NODE_BIN:-}" ]; then
    NODE_BIN="$TERENTO_NODE_BIN"
else
    NODE_BIN="$(command -v node 2>/dev/null || command -v nodejs 2>/dev/null || true)"
fi

case "$NODE_BIN" in
    /*|./*|../*)
        if [ ! -x "$NODE_BIN" ]; then
            echo "Node.js executable is not usable: $NODE_BIN" >&2
            exit 1
        fi
        ;;
    *)
        NODE_BIN="$(command -v "$NODE_BIN" 2>/dev/null || true)"
        if [ -z "$NODE_BIN" ]; then
            echo "Node.js is required. Install Node.js or set TERENTO_NODE_BIN to its executable." >&2
            exit 1
        fi
        ;;
esac

export NODE_BIN
export TERENTO_NODE_BIN="$NODE_BIN"
