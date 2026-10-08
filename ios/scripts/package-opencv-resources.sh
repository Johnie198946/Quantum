#!/bin/sh
set -eu

app="${TARGET_BUILD_DIR}/${WRAPPER_NAME}"
framework="${TARGET_BUILD_DIR}/${FRAMEWORKS_FOLDER_PATH}/opencv2.framework"
bundle="$app/OpenCVResources.bundle"
[ -d "$framework" ] || exit 0

# Xcode injects a codeless dylib for this static library's privacy resources.
# Refuse to remove OpenCV if a future package actually needs dynamic loading.
loads="$(xcrun otool -L "$app/${EXECUTABLE_NAME}")"
if printf '%s\n' "$loads" | /usr/bin/grep -q 'opencv2.framework/'; then
    echo 'error: OpenCV is dynamically linked; keep its framework and provide real dSYMs.' >&2
    exit 1
fi
symbols="$(xcrun nm -g "$framework/opencv2" 2>/dev/null)"
sections="$(xcrun otool -l "$framework/opencv2")"
if [ -n "$symbols" ] || ! printf '%s\n' "$sections" | /usr/bin/awk '
    $1 == "sectname" { text = ($2 == "__text") }
    text && $1 == "size" && $2 !~ /^0x0+$/ { exit 1 }
'; then
    echo 'error: OpenCV framework contains code; do not repackage it as resources.' >&2
    exit 1
fi

/usr/bin/plutil -lint "$framework/PrivacyInfo.xcprivacy"
/usr/bin/ditto "$framework" "$bundle"
/bin/rm -f "$bundle/opencv2"
/bin/rm -rf "$bundle/_CodeSignature"
/usr/libexec/PlistBuddy -c 'Delete :CFBundleExecutable' "$bundle/Info.plist"
/usr/libexec/PlistBuddy -c 'Set :CFBundlePackageType BNDL' "$bundle/Info.plist"
/usr/bin/cmp "$framework/PrivacyInfo.xcprivacy" "$bundle/PrivacyInfo.xcprivacy"
/bin/rm -rf "$framework"
