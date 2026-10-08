"""Keep static OpenCV privacy resources without shipping Xcode's empty dylib."""
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("xcrun"), reason="Requires macOS Mach-O tools")
@pytest.mark.parametrize("mode", ["codeless", "code", "linked"])
def test_opencv_resource_packaging_preserves_manifest_and_rejects_code(tmp_path, mode):
    app = tmp_path / "Test.app"
    framework = app / "Frameworks/opencv2.framework"
    framework.mkdir(parents=True)
    info = {"CFBundleIdentifier": "org.opencv", "CFBundleExecutable": "opencv2", "CFBundlePackageType": "FMWK"}
    (framework / "Info.plist").write_bytes(plistlib.dumps(info))
    manifest = plistlib.dumps({"NSPrivacyTracking": False, "NSPrivacyAccessedAPITypes": []})
    (framework / "PrivacyInfo.xcprivacy").write_bytes(manifest)
    library_source = tmp_path / "library.c"
    library_source.write_text("" if mode == "codeless" else "int opencv_probe(void) { return 42; }")
    subprocess.run(["xcrun", "clang", "-dynamiclib", "-install_name", "@rpath/opencv2.framework/opencv2",
                    str(library_source), "-o", str(framework / "opencv2")], check=True)
    app_source = tmp_path / "app.c"
    app_source.write_text("int main(void) { return 0; }" if mode != "linked" else
                          "extern int opencv_probe(void); int main(void) { return opencv_probe(); }")
    subprocess.run(["xcrun", "clang", str(app_source), *([str(framework / "opencv2")] if mode == "linked" else []),
                    "-o", str(app / "Test")], check=True)
    original_app = (app / "Test").read_bytes()
    env = {**os.environ, "TARGET_BUILD_DIR": str(tmp_path), "WRAPPER_NAME": "Test.app",
           "FRAMEWORKS_FOLDER_PATH": "Test.app/Frameworks", "EXECUTABLE_NAME": "Test"}
    command = ["/bin/sh", str(ROOT / "ios/scripts/package-opencv-resources.sh")]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    bundle = app / "OpenCVResources.bundle"
    assert (app / "Test").read_bytes() == original_app
    if mode != "codeless":
        assert result.returncode != 0
        assert framework.exists()
        assert not bundle.exists()
        assert "error:" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert not framework.exists()
        assert not (bundle / "opencv2").exists()
        assert (bundle / "PrivacyInfo.xcprivacy").read_bytes() == manifest
        packaged_info = plistlib.loads((bundle / "Info.plist").read_bytes())
        assert packaged_info["CFBundlePackageType"] == "BNDL"
        assert "CFBundleExecutable" not in packaged_info
        subprocess.run(command, env=env, check=True)
