#!/usr/bin/env python3
"""
Windows Build Script - PyInstaller packaging.

Usage:
    python build/build_windows.py

Steps:
1. PyInstaller packages src/ into a single directory executable
2. Copies config/ to the output directory
3. Downloads WebView2 Bootstrapper if not present
4. Generates Inno Setup script from template
5. Optionally runs Inno Setup to compile the installer

Requirements:
    pip install pyinstaller
"""

import os
import sys
import shutil
import subprocess
import urllib.request
import importlib
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
CONFIG_DIR = PROJECT_ROOT / "config"
TOOLS_DIR = PROJECT_ROOT / "tools"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
OUTPUT_DIR = DIST_DIR / "ForensicTool"
RESOURCES_DIR = BUILD_DIR / "resources"

# WebView2 Bootstrapper
WEBVIEW2_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_BOOTSTRAPPER_FILE = RESOURCES_DIR / "MicrosoftEdgeWebview2Setup.exe"

# App info
APP_NAME = "Android Automated Forensic Tool"
APP_VERSION = "2.0.0"
APP_PUBLISHER = "Forensic Team"
APP_EXE_NAME = "ForensicTool"


def check_pyinstaller():
    """Check if PyInstaller is installed."""
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("ERROR: PyInstaller not installed. Run: pip install pyinstaller")
        return False


def check_runtime_dependencies():
    """Validate critical runtime dependencies in the current build environment."""
    print("Checking runtime dependencies...")
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    required_modules = [
        ("webview", "pywebview"),
        ("cv2", "opencv-python"),
        ("numpy", "numpy"),
        ("uiautomator2", "uiautomator2"),
        ("paddle", "paddlepaddle"),
        ("paddleocr", "paddleocr"),
        ("paddlex", "paddlex"),
    ]

    all_ok = True
    for module_name, package_name in required_modules:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "unknown")
            module_path = getattr(module, "__file__", "<builtin>")
            print(f"  OK  {package_name}: version={version}, path={module_path}")
        except Exception as e:
            all_ok = False
            print(f"  ERR {package_name}: {e}")

    if not all_ok:
        print("ERROR: Current build environment is missing required runtime dependencies.")
        print("Run: python -m pip install -r requirements.txt")
        return False

    return True


def download_webview2_bootstrapper():
    """Download WebView2 Evergreen Bootstrapper if not present."""
    if WEBVIEW2_BOOTSTRAPPER_FILE.exists():
        print(f"WebView2 Bootstrapper already exists: {WEBVIEW2_BOOTSTRAPPER_FILE}")
        return True

    print(f"Downloading WebView2 Bootstrapper...")
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    try:
        urllib.request.urlretrieve(WEBVIEW2_BOOTSTRAPPER_URL, str(WEBVIEW2_BOOTSTRAPPER_FILE))
        print(f"Downloaded to: {WEBVIEW2_BOOTSTRAPPER_FILE}")
        return True
    except Exception as e:
        print(f"WARNING: Failed to download WebView2 Bootstrapper: {e}")
        print("You can manually download it from:")
        print("  https://developer.microsoft.com/en-us/microsoft-edge/webview2/")
        return False


def run_pyinstaller():
    """Run PyInstaller to package the application."""
    print("\n" + "=" * 60)
    print("Running PyInstaller...")
    print("=" * 60)

    # Clean previous builds
    for d in [DIST_DIR, PROJECT_ROOT / "build" / "pyinstaller_build"]:
        if d.exists():
            shutil.rmtree(d)

    entry_point = SRC_DIR / "web_launcher.py"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_EXE_NAME,
        "--noconsole",
        "--onedir",
        "--distpath", str(DIST_DIR),
        "--workpath", str(PROJECT_ROOT / "build" / "pyinstaller_build"),
        "--specpath", str(BUILD_DIR),
        # Add all src modules as hidden imports
        "--hidden-import", "core",
        "--hidden-import", "core.adb_controller",
        "--hidden-import", "core.ui_locator",
        "--hidden-import", "core.recorder",
        "--hidden-import", "core.image_locator",
        "--hidden-import", "core.parallel_executor",
        "--hidden-import", "core.device_manager",
        "--hidden-import", "core.notifier",
        "--hidden-import", "platforms",
        "--hidden-import", "platforms.taobao_handler",
        "--hidden-import", "platforms.taobao_favorites",
        "--hidden-import", "platforms.base_handler",
        "--hidden-import", "platforms.router",
        "--hidden-import", "task",
        "--hidden-import", "task.task_model",
        "--hidden-import", "task.task_loader",
        "--hidden-import", "task.task_manager",
        "--hidden-import", "task.task_dispatcher",
        "--hidden-import", "task.shop_grouper",
        "--hidden-import", "task.grouped_executor",
        "--hidden-import", "task.db_connector",
        "--hidden-import", "task.db_task_loader",
        "--hidden-import", "antibot",
        "--hidden-import", "locales",
        "--hidden-import", "state",
        "--hidden-import", "main",
        "--hidden-import", "pymysql",
        "--hidden-import", "cv2",
        "--hidden-import", "numpy",
        "--hidden-import", "uiautomator2",
        "--hidden-import", "paddle",
        "--hidden-import", "paddleocr",
        "--hidden-import", "paddlex",
        "--collect-data", "uiautomator2",
        "--collect-all", "paddle",
        "--collect-all", "paddleocr",
        "--collect-all", "paddlex",
        # Add data files
        "--add-data", f"{CONFIG_DIR}{os.pathsep}config",
        "--add-data", f"{SRC_DIR / 'locales'}{os.pathsep}locales",
        # Path for imports
        "--paths", str(SRC_DIR),
        # Entry point
        str(entry_point),
    ]

    print(f"Command: {' '.join(cmd[:10])}...")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print("ERROR: PyInstaller failed!")
        return False

    print("PyInstaller completed successfully")
    return True


def copy_additional_files():
    """Copy additional files to the distribution directory."""
    print("\nCopying additional files...")

    output_app_dir = OUTPUT_DIR

    # Copy config directory (excluding database.json with credentials)
    config_dest = output_app_dir / "config"
    if config_dest.exists():
        # Config already included via --add-data, but ensure templates are there
        pass
    else:
        shutil.copytree(CONFIG_DIR, config_dest, dirs_exist_ok=True)

    # Remove database.json from distribution (contains local credentials)
    db_json = config_dest / "database.json"
    if db_json.exists():
        db_json.unlink()
        print("  Removed database.json from distribution")

    # Copy database.json.example
    example = CONFIG_DIR / "database.json.example"
    if example.exists():
        shutil.copy2(example, config_dest / "database.json.example")
        print("  Copied database.json.example")

    # Copy WebView2 bootstrapper
    if WEBVIEW2_BOOTSTRAPPER_FILE.exists():
        dest = output_app_dir / "MicrosoftEdgeWebview2Setup.exe"
        shutil.copy2(WEBVIEW2_BOOTSTRAPPER_FILE, dest)
        print("  Copied WebView2 Bootstrapper")

    # Copy runtime tools required by the packaged app
    adb_keyboard_apk = TOOLS_DIR / "ADBKeyboard.apk"
    if adb_keyboard_apk.exists():
        tools_dest = output_app_dir / "tools"
        tools_dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(adb_keyboard_apk, tools_dest / "ADBKeyboard.apk")
        print("  Copied tools/ADBKeyboard.apk")
    else:
        print("  WARNING: tools/ADBKeyboard.apk not found, packaged app cannot install ADBKeyboard")

    print("Additional files copied")


def generate_inno_setup_script():
    """Generate Inno Setup script for creating Windows installer."""
    print("\nGenerating Inno Setup script...")

    iss_template = BUILD_DIR / "installer.iss"
    if not iss_template.exists():
        print("  installer.iss template not found, skipping")
        return

    print(f"  Inno Setup script available at: {iss_template}")
    print("  To compile installer: iscc build/installer.iss")


def main():
    print(f"Building {APP_NAME} v{APP_VERSION}")
    print(f"Project root: {PROJECT_ROOT}")
    print()

    if not check_pyinstaller():
        sys.exit(1)

    if not check_runtime_dependencies():
        sys.exit(1)

    # Step 1: Download WebView2 bootstrapper
    download_webview2_bootstrapper()

    # Step 2: Run PyInstaller
    if not run_pyinstaller():
        sys.exit(1)

    # Step 3: Copy additional files
    copy_additional_files()

    # Step 4: Generate Inno Setup script
    generate_inno_setup_script()

    print("\n" + "=" * 60)
    print("Build complete!")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Executable: {OUTPUT_DIR / (APP_EXE_NAME + '.exe')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
