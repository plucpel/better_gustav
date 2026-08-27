"""
Build script to package Gustav into a 100% standalone, zero-dependency
portable Windows folder and ZIP archive from macOS.

Does not require Windows to build or run. The final ZIP contains an embedded
Python runtime and all dependencies, runnable by double-clicking 'Lancer_Gustav.bat'.
"""

import os
import sys
import shutil
import zipfile
import urllib.request
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_DIR, "dist")
PORTABLE_DIR = os.path.join(DIST_DIR, "Gustav_Windows_Portable")
ZIP_OUTPUT = os.path.join(DIST_DIR, "Gustav_Windows_Portable.zip")

PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"

def build():
    print("=" * 65)
    print("  📦 Packaging Gustav for Windows (Zero-Install Portable Bundle)")
    print("=" * 65)

    if os.path.exists(PORTABLE_DIR):
        shutil.rmtree(PORTABLE_DIR)
    os.makedirs(PORTABLE_DIR, exist_ok=True)
    os.makedirs(DIST_DIR, exist_ok=True)

    # 1. Download Windows Embedded Python
    zip_embed_path = os.path.join(DIST_DIR, "python_embed.zip")
    if not os.path.exists(zip_embed_path):
        print("\n[1/5] Downloading Windows Embedded Python (python-3.11.9-embed-amd64.zip)...")
        urllib.request.urlretrieve(PYTHON_EMBED_URL, zip_embed_path)
    else:
        print("\n[1/5] Using cached Windows Embedded Python archive...")

    # 2. Extract Embedded Python
    print("\n[2/5] Extracting Python runtime...")
    with zipfile.ZipFile(zip_embed_path, 'r') as zip_ref:
        zip_ref.extractall(PORTABLE_DIR)

    # Enable site-packages in python311._pth
    pth_file = os.path.join(PORTABLE_DIR, "python311._pth")
    if os.path.exists(pth_file):
        with open(pth_file, "r", encoding="utf-8") as f:
            pth_content = f.read()
        # Uncomment import site
        pth_content = pth_content.replace("#import site", "import site")
        pth_content += "\nLib\\site-packages\n.\n"
        with open(pth_file, "w", encoding="utf-8") as f:
            f.write(pth_content)

    # 3. Download and install Windows wheels into Lib/site-packages
    site_packages_dir = os.path.join(PORTABLE_DIR, "Lib", "site-packages")
    os.makedirs(site_packages_dir, exist_ok=True)

    print("\n[3/5] Downloading and installing Windows x64 binary wheels into portable bundle...")
    packages = [
        "fastapi==0.110.0",
        "uvicorn==0.28.0",
        "starlette==0.36.3",
        "pydantic==2.6.4",
        "pydantic-core==2.16.3",
        "typing-extensions>=4.8.0",
        "anyio>=3.4.0",
        "sniffio>=1.1",
        "idna>=2.8",
        "click>=7.0",
        "h11>=0.8",
        "pymupdf>=1.23.0"
    ]

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", site_packages_dir,
        "--platform", "win_amd64",
        "--only-binary=:all:",
        "--python-version", "3.11",
        "--no-compile"
    ] + packages

    subprocess.check_call(cmd)

    # 4. Copy Application Source Code, Data and Static Files
    print("\n[4/5] Copying Gustav application files...")
    shutil.copy2(os.path.join(PROJECT_DIR, "app.py"), PORTABLE_DIR)
    shutil.copy2(os.path.join(PROJECT_DIR, "tube_calculator.py"), PORTABLE_DIR)
    shutil.copy2(os.path.join(PROJECT_DIR, "medical_dictionary.py"), PORTABLE_DIR)
    shutil.copy2(os.path.join(PROJECT_DIR, "requisition_filler.py"), PORTABLE_DIR)
    shutil.copy2(os.path.join(PROJECT_DIR, "profiles_manager.py"), PORTABLE_DIR)
    shutil.copy2(os.path.join(PROJECT_DIR, "clinics_manager.py"), PORTABLE_DIR)

    # Copy data/
    shutil.copytree(os.path.join(PROJECT_DIR, "data"), os.path.join(PORTABLE_DIR, "data"), dirs_exist_ok=True)
    # Copy static/
    shutil.copytree(os.path.join(PROJECT_DIR, "static"), os.path.join(PORTABLE_DIR, "static"), dirs_exist_ok=True)

    # Create 1-click Windows batch launcher
    bat_content = """@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GUSTAV - Calculateur de Tubes Sanguins (CHU de Québec)

echo =====================================================================
echo   🏥 GUSTAV - Calculateur de Tubes de Prélèvement (CHU de Québec)
echo =====================================================================
echo.
echo [*] Démarrage de Gustav en cours...
echo [*] Serveur local : http://127.0.0.1:8000
echo.
echo [INFO] Pour fermer l'application, fermez simplement cette fenêtre.
echo.

:: Ouvre le navigateur après 1 seconde
start "" timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000

:: Lance le Python embarqué (aucun Python système requis)
python.exe app.py

pause
"""
    with open(os.path.join(PORTABLE_DIR, "Lancer_Gustav.bat"), "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Create VBScript silent launcher (optional no terminal window)
    vbs_content = """Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "Lancer_Gustav.bat", 1, False
"""
    with open(os.path.join(PORTABLE_DIR, "Lancer_Gustav_Raccourci.vbs"), "w", encoding="utf-8") as f:
        f.write(vbs_content)

    # 5. Create Zip Archive
    print("\n[5/5] Creating final portable ZIP archive...")
    if os.path.exists(ZIP_OUTPUT):
        os.remove(ZIP_OUTPUT)

    shutil.make_archive(os.path.join(DIST_DIR, "Gustav_Windows_Portable"), "zip", PORTABLE_DIR)

    zip_size_mb = os.path.getsize(ZIP_OUTPUT) / (1024 * 1024)
    print(f"\n SUCCESS! Portable Windows package created:")
    print(f"  📁 Folder : {PORTABLE_DIR}")
    print(f"  📦 ZIP    : {ZIP_OUTPUT} ({zip_size_mb:.1f} MB)")
    print("\nThis package contains Python, all dependencies, and the Gustav application.")
    print("Anyone on Windows can simply unzip and double-click 'Lancer_Gustav.bat'.")

if __name__ == "__main__":
    build()
