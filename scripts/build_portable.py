"""Build a self-contained desktop folder and ZIP using the current interpreter."""

import argparse
import hashlib
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.desktop import VERSION


def main():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows portable distribution on Windows (Python 3.12+).")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--console", action="store_true", help="Diagnostic build with a console for startup errors.")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    work = ROOT / "build" / "portable"
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    # PyInstaller and Qt remain development dependencies, not prerequisites on
    # the machine that receives the resulting ZIP.
    from PySide6.QtWidgets import QApplication
    from src.desktop.theme import app_icon
    app = QApplication.instance() or QApplication([])
    icon = work / "depviz.ico"
    if not app_icon().pixmap(128, 128).save(str(icon), "ICO"):
        raise RuntimeError("Cannot create the application icon")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(output),
               "--workpath", str(work / "cache"), str(ROOT / "config/depviz.spec")]
    environment = os.environ.copy()
    environment["DEPVIZ_BUILD_CONSOLE"] = "1" if args.console else "0"
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    app_folder = output / "Depviz"
    # Ship the source and third-party license notices alongside replaceable Qt
    # libraries. Nothing is installed into Program Files or the Windows registry.
    notices = output / "Depviz" / "THIRD_PARTY_LICENSES"
    notices.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "docs/licenses", notices / "Qt", dirs_exist_ok=True)
    for name in ("PySide6-Essentials", "shiboken6", "graphviz", "pyinstaller"):
        distribution = importlib.metadata.distribution(name)
        for file in distribution.files or []:
            if any(part.lower() in ("licenses", "license", "license.txt", "license.md", "copying")
                   or part.lower().startswith("copying") for part in file.parts):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    destination = notices / name / str(file)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, notices / "PYTHON-LICENSE.txt")
    shutil.copy2(ROOT / "docs/desktop.md", output / "Depviz" / "README.md")
    shutil.copy2(ROOT / "docs/third-party.md", output / "Depviz" / "THIRD-PARTY.md")
    shutil.copytree(ROOT / "src", output / "Depviz" / "source" / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"), dirs_exist_ok=True)
    shutil.copy2(ROOT / "launch_gui.pyw", output / "Depviz" / "source" / "launch_gui.pyw")
    for file in ("requirements.txt", "requirements-gui.txt"):
        destination = output / "Depviz" / "source" / "config" / file
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "config" / file, destination)
    system = platform.system().lower()
    archive = output / f"Depviz-{VERSION}-{system}-{platform.machine().lower()}-portable"
    zip_path = Path(shutil.make_archive(str(archive), "zip", output, app_folder.name))
    with zip_path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    Path(str(zip_path) + ".sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    print(f"Portable application: {archive}.zip")


if __name__ == "__main__":
    main()
