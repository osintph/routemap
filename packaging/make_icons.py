"""
Draw the app icon and write it in every format the builds need.

    python packaging/make_icons.py

Writes routemap/gui/data/icon.png (1024 px, used for the window icon and the
Linux desktop entry), packaging/icon.ico (Windows) and packaging/icon.icns
(macOS). The motif is the app's own: a route of numbered stops on a dark map
tile, in the site-code teal. Drawn with Qt so it needs no image editor;
Pillow writes the multi-size ICO and ICNS.
"""
import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIZE = 1024


def draw() -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    tile = QRectF(64, 64, SIZE - 128, SIZE - 128)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#13202d"))
    p.drawRoundedRect(tile, 190, 190)
    # A hint of land: two soft blobs.
    p.setBrush(QColor("#1f3242"))
    p.drawEllipse(QRectF(150, 220, 430, 300))
    p.drawEllipse(QRectF(520, 470, 330, 330))
    stops = [QPointF(250, 720), QPointF(420, 420), QPointF(640, 560), QPointF(790, 290)]
    path = QPainterPath(stops[0])
    for point in stops[1:]:
        path.lineTo(point)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("#e8eef3"), 34, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)
    for i, point in enumerate(stops):
        color = QColor("#e8eef3") if i == 0 else QColor("#3cc3b4")
        if i == len(stops) - 1:
            color = QColor("#f0a440")
        p.setPen(QPen(QColor("#13202d"), 18))
        p.setBrush(color)
        p.drawEllipse(point, 66, 66)
    p.end()
    return image


def main() -> int:
    QGuiApplication(sys.argv[:1])
    png = ROOT / "routemap" / "gui" / "data" / "icon.png"
    draw().save(str(png))
    big = Image.open(png).convert("RGBA")
    big.save(ROOT / "packaging" / "icon.ico",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(ROOT / "packaging" / "icon.icns")
    print(png, ROOT / "packaging" / "icon.ico", ROOT / "packaging" / "icon.icns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
