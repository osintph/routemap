# PyInstaller build for the desktop app.
#
#   pyinstaller packaging/routemap.spec --noconfirm
#
# macOS: one-dir, wrapped in "Route Map.app". Windows and Linux: one file.
# The display name and bundle id below are build-time copies of
# routemap/__about__.py (see docs/renaming.md).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from routemap.__about__ import DISPLAY_NAME, NAME, __version__  # noqa: E402

datas = collect_data_files("routemap", includes=["**/*.tsv", "**/*.json", "**/*.gz",
                                                 "**/*.txt", "**/*.png", "**/README.md"])

# Qt modules the app never imports. PyInstaller's PySide6 hooks only collect what
# is imported, so this is a backstop against something pulling them in.
EXCLUDES = [
    "tkinter", "unittest", "pydoc_data", "PIL",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtGraphs", "PySide6.QtBluetooth", "PySide6.QtSensors", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtNetwork",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvgWidgets", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtHttpServer", "PySide6.QtNfc",
]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["routemap.gui.app", "routemap.engine.sitegen", "jsonschema"],
    excludes=EXCLUDES,
    noarchive=False,
)
# Two Qt plugins drag in whole frameworks the app never uses: the PDF image
# format plugin (QtPdf) and the virtual keyboard input context (QtQuick, QtQml).
# PDF export uses QPdfWriter from QtGui, not QtPdf. Dropping them saves ~20 MB.
DROP = ("QtPdf", "QtQuick", "QtQml", "QtVirtualKeyboard", "QtNetwork", "qpdf",
        "virtualkeyboard", "Qt6Pdf", "Qt6Quick", "Qt6Qml", "Qt6VirtualKeyboard", "Qt6Network")
a.binaries = [b for b in a.binaries if not any(token in b[0] for token in DROP)]
a.datas = [d for d in a.datas if not any(token in d[0] for token in DROP)]

pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False,
              icon=str(ROOT / "packaging" / "icon.icns"), target_arch=None,
              codesign_identity=None, entitlements_file=None)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME, strip=False, upx=False)
    app = BUNDLE(
        coll,
        name=f"{DISPLAY_NAME}.app",
        icon=str(ROOT / "packaging" / "icon.icns"),
        bundle_identifier="info.osintph.routemap",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": DISPLAY_NAME,
            "CFBundleShortVersionString": __version__,
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "LSMinimumSystemVersion": "12.0",
        },
    )
else:
    # A console binary on Windows so the CLI can print; double-clicked, it drops
    # its console window at startup (routemap.cli._hide_console_for_gui).
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=True,
              icon=str(ROOT / "packaging" / "icon.ico") if sys.platform.startswith("win") else None,
              strip=False, upx=False, runtime_tmpdir=None)
