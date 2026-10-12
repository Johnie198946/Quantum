#!/bin/sh
set -eu
travel_client="$SRCROOT/../clients/travel-space"
if [ ! -d "$travel_client/node_modules/esbuild" ]; then
    echo "error: Install the TravelSpace dependencies with npm ci --prefix clients/travel-space before building iOS." >&2
    exit 1
fi
if command -v node >/dev/null 2>&1; then
    travel_node="$(command -v node)"
elif [ -x /opt/homebrew/bin/node ]; then
    travel_node=/opt/homebrew/bin/node
elif [ -x /usr/local/bin/node ]; then
    travel_node=/usr/local/bin/node
else
    echo "error: Node.js is required to bundle the approved TravelSpace renderer." >&2
    exit 1
fi
QUANTUM_TRAVEL_OUT="$TARGET_BUILD_DIR/$UNLOCALIZED_RESOURCES_FOLDER_PATH/TravelSpace" "$travel_node" "$travel_client/build.mjs"
