# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "scripts/portable_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "examples/advanced"), "examples/advanced"),
           (str(root / "docs/desktop.md"), "docs")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "PySide6.QtTest"],
    noarchive=False,
    optimize=0,
)
# Qt 6.10's Windows wheel imports the unversioned ICU API supplied by Windows.
# A build interpreter can ship a different icuuc.dll with versioned exports
# (e.g. u_strToUpper_78). Bundling it shadows Windows' DLL and breaks QtCore.
# Use the OS component, as the unfrozen Qt application does, and omit the
# unrelated ICU data DLL pulled in by that build-environment copy.
a.binaries = [item for item in a.binaries
              if Path(item[0]).name.lower() != "icuuc.dll"
              and not Path(item[0]).name.lower().startswith("icudt")]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Depviz",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=os.environ.get("DEPVIZ_BUILD_CONSOLE") == "1",
    disable_windowed_traceback=False,
    icon=[str(root / "build/portable/depviz.ico")],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Depviz")
