"""Build AutoPBI_Studio.exe standalone Windows Desktop App (no Python required for end users).

Outputs:
  - dist/AutoPBI_Studio_App/AutoPBI_Studio.exe  (ready-to-run folder)
  - dist/AutoPBI_Studio_App_Windows.zip         (clean distributable ZIP, zero personal data)
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

from build_package import (
    EMPTY_WORK_DIRS,
    audit_staged_files,
    ensure_sample_sales_csv,
)

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
BUILD_TMP = ROOT / "build" / "pyinstaller_app"
APP_NAME = "AutoPBI_Studio"
APP_OUT_DIR = DIST_DIR / "AutoPBI_Studio_App"
APP_ZIP_PATH = DIST_DIR / "AutoPBI_Studio_App_Windows.zip"
ICON_PATH = ROOT / "assets" / "app_icon.ico"

APP_EXTRA_FILES = [
    "Requirement_Template.md",
    "HUONG_DAN_REQUIREMENT.md",
    "config/appsource_marketplace_index.json",
    "sample_data/sample_sales.csv",
]

APP_README = """# Auto-PBI Dashboard Studio (Windows Desktop App)

Ung dung tao Dashboard Power BI (`.pbip` & `.pbit`) tu dong tu **bat ky file `.csv` nao** + **file dac ta `Requirement.md`** — **khong can cai Python, khong gui du lieu ra ngoai**.

---

## Cach Chay (2 Buoc)
1. Giai nen toan bo thu muc nay vao mot vi tri bat ky tren may Windows cua ban (vi du `D:\\AutoPBI_Studio_App`).
2. Nhap dup vao **`AutoPBI_Studio.exe`**:
   - Ung dung se tu dong mo cua so Desktop App.
   - Bam **Xem mau** / **Copy mau** `Requirement_Template.md` ngay tai khung nap CSV (hoac thu ngay file mau `sample_data/sample_sales.csv` + `Requirement_Template.md`).
   - Bam **"Chay Tu Dong Toan Trinh A-Z"** -> Kiem tra doi soat KPI -> Bam **"Mo Truc Tiep Tren Power BI Desktop"**.

## Yeu Cau
- Windows 10 / 11 (64-bit)
- Power BI Desktop (de mo file `.pbip` / `.pbit` dau ra)
- Khong can cai Python hay thu vien bo sung.

## Bao Mat & Doc Lap
- Moi file ban nap va ket qua sinh ra (`inputs/`, `data_warehouse/`, `output_pbi/`, `reports/`, `custom_visuals/`) chi luu cuc bo ngay trong thu muc ung dung tren may cua ban.
"""


def _make_png_rgba(size: int) -> bytes:
    """Create a crisp dark-navy + gold-bar Power BI style icon as PNG bytes."""
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type 0
        for x in range(size):
            nx, ny = x / size, y / size
            # Rounded dark-navy background
            dx = max(0.0, abs(nx - 0.5) - 0.36)
            dy = max(0.0, abs(ny - 0.5) - 0.36)
            in_card = (dx * dx + dy * dy) <= (0.14 * 0.14)
            if not in_card:
                row.extend((0, 0, 0, 0))
                continue
            # Background gradient (#0f172a -> #1e3a8a)
            r = int(15 + 15 * ny)
            g = int(23 + 35 * ny)
            b = int(42 + 96 * ny)
            # 3 rising golden bars (Power BI aesthetic)
            bar1 = 0.18 <= nx <= 0.34 and 0.52 <= ny <= 0.80
            bar2 = 0.42 <= nx <= 0.58 and 0.35 <= ny <= 0.80
            bar3 = 0.66 <= nx <= 0.82 and 0.20 <= ny <= 0.80
            if bar1:
                r, g, b = 245, 158, 11  # amber-500
            elif bar2:
                r, g, b = 251, 191, 36  # amber-400
            elif bar3:
                r, g, b = 253, 224, 71  # yellow-300
            row.extend((r, g, b, 255))
        rows.append(bytes(row))

    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def generate_icon(ico_path: Path) -> None:
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    sizes = [32, 64, 256]
    pngs = [_make_png_rgba(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = []
    for s, data in zip(sizes, pngs):
        dim = 0 if s >= 256 else s
        entries.append(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    ico_path.write_bytes(header + b"".join(entries) + b"".join(pngs))


def build_desktop_app() -> Path:
    ensure_sample_sales_csv(ROOT / "sample_data" / "sample_sales.csv")
    generate_icon(ICON_PATH)

    pyinstaller_dist = BUILD_TMP / "dist"
    pyinstaller_work = BUILD_TMP / "work"
    pyinstaller_spec = BUILD_TMP / "spec"
    stage_app_dir = BUILD_TMP / "stage_app"
    if stage_app_dir.exists():
        shutil.rmtree(stage_app_dir)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onedir",
        "--noconfirm",
        "--name", APP_NAME,
        "--icon", str(ICON_PATH),
        "--distpath", str(pyinstaller_dist),
        "--workpath", str(pyinstaller_work),
        "--specpath", str(pyinstaller_spec),
        "--paths", str(ROOT),
        "--hidden-import", "pyarrow.vendored.version",
        "--hidden-import", "pyarrow._compute",
        "--hidden-import", "pyarrow.parquet",
        "--hidden-import", "pyarrow.csv",
        "--hidden-import", "pandas",
        "--hidden-import", "numpy",
        "--hidden-import", "flask",
        "--hidden-import", "yaml",
        "--hidden-import", "requests",
        "--exclude-module", "scipy",
        "--exclude-module", "numba",
        "--exclude-module", "llvmlite",
        "--exclude-module", "matplotlib",
        "--exclude-module", "PIL",
        "--exclude-module", "tkinter",
        "--exclude-module", "pytest",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        "--exclude-module", "lxml",
        "--exclude-module", "sqlalchemy",
        "--exclude-module", "sklearn",
        "--exclude-module", "torch",
        "--exclude-module", "cv2",
        "--collect-submodules", "src",
        str(ROOT / "src" / "app_launcher.py"),
    ]
    print("[Build App] Running PyInstaller...")
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"PyInstaller failed with exit code {proc.returncode}")

    built_dir = pyinstaller_dist / APP_NAME
    if not (built_dir / f"{APP_NAME}.exe").exists():
        raise FileNotFoundError(f"Expected EXE not found at {built_dir / f'{APP_NAME}.exe'}")

    shutil.copytree(built_dir, stage_app_dir)

    # Copy user-facing docs, template, marketplace index, sample CSV
    for rel in APP_EXTRA_FILES:
        src = ROOT / rel
        dst = stage_app_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    (stage_app_dir / "README.md").write_text(APP_README, encoding="utf-8")

    # Create clean empty working directories
    for d in EMPTY_WORK_DIRS:
        dd = stage_app_dir / d
        dd.mkdir(parents=True, exist_ok=True)
        (dd / ".gitkeep").write_text("", encoding="utf-8")

    # Audit user-facing text files (exclude binary _internal/)
    issues = []
    for sub in ("sample_data", "config"):
        sub_p = stage_app_dir / sub
        if sub_p.exists():
            issues.extend(audit_staged_files(sub_p))
    if issues:
        raise RuntimeError("Privacy audit failed:\n" + "\n".join(issues))

    # Zip the standalone app directly from clean staging dir
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    if APP_ZIP_PATH.exists():
        APP_ZIP_PATH.unlink()
    print(f"[Build App] Zipping {stage_app_dir} -> {APP_ZIP_PATH} ...")
    with zipfile.ZipFile(APP_ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(stage_app_dir.rglob("*")):
            if p.is_file():
                arcname = Path("AutoPBI_Studio_App") / p.relative_to(stage_app_dir)
                zf.write(p, arcname.as_posix())

    # Update dist/AutoPBI_Studio_App folder if not currently locked by a running instance
    try:
        if APP_OUT_DIR.exists():
            shutil.rmtree(APP_OUT_DIR)
        shutil.copytree(stage_app_dir, APP_OUT_DIR)
    except OSError:
        print(f"[Note] {APP_OUT_DIR} dang mo boi tien trinh khac -> da cap nhat file ZIP moi nhat tai {APP_ZIP_PATH}")

    size_mb = APP_ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"[OK] Standalone Windows App built!")
    print(f"     ZIP    : {APP_ZIP_PATH} ({size_mb:.1f} MB)")
    return APP_ZIP_PATH


if __name__ == "__main__":
    build_desktop_app()
