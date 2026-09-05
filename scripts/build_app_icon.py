"""Build ``assets/app-icon.ico`` from ``assets/app-icon.svg``.

Run once after editing the SVG (or as part of the build pipeline). Uses
PySide6 (already a dep) to rasterize the SVG, then Pillow to assemble
the multi-resolution ICO.

The resulting ``app-icon.ico`` is committed to the repo so end-users
don't need Pillow installed to run the app.

Usage (from project root)::

    .venv/Scripts/python.exe scripts/build_app_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure we can import PySide6 even if Pillow is missing.
try:
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QImageReader
    from PySide6.QtWidgets import QApplication
except ImportError as exc:
    sys.exit(f"PySide6 is required: {exc}")

try:
    from PIL import Image
except ImportError as exc:
    sys.exit(f"Pillow is required for ICO assembly: {exc}")


ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "app-icon.svg"
OUT_ICO = ROOT / "assets" / "app-icon.ico"
SIZES = [16, 32, 48, 64, 128, 256]


def main() -> int:
    if not SVG.exists():
        sys.exit(f"SVG not found: {SVG}")

    # QApplication is required for QImage I/O on some platforms.
    app = QApplication.instance() or QApplication([])

    # Load the SVG at the largest size; we downscale to each target.
    reader = QImageReader(str(SVG))
    reader.setScaledSize(QSize(max(SIZES), max(SIZES)))
    base = reader.read()
    if base.isNull():
        sys.exit(f"Failed to read {SVG}: {reader.errorString()}")

    # Generate one PNG per size, then combine into a single multi-res ICO.
    pngs: list[Path] = []
    for size in SIZES:
        scaled = base.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        png_path = SVG.with_name(f"app-icon-{size}.png")
        if not scaled.save(str(png_path), "PNG"):
            sys.exit(f"Failed to save {png_path}")
        pngs.append(png_path)
        print(f"  {png_path.relative_to(ROOT)} ({size}x{size})")

    images = [Image.open(str(p)) for p in pngs]
    images[0].save(
        str(OUT_ICO),
        format="ICO",
        sizes=[(s, s) for s in SIZES],
    )
    print(f"  {OUT_ICO.relative_to(ROOT)} (multi-resolution)")

    # Clean up the intermediate PNGs (the ICO already contains them).
    for png in pngs:
        png.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
