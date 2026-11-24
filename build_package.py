"""Build a clean, multi-user local portable ZIP package of Auto-PBI Dashboard Studio.

Excludes ALL personal datasets, user requirements, generated warehouses, reports,
Power BI outputs, and caches. Includes a synthetic sample dataset matching
Requirement_Template.md so any new user can test immediately after unzipping.
"""

from __future__ import annotations

import csv
import random
import shutil
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
STAGE_DIR = DIST_DIR / "AutoPBI_Studio_Portable"
ZIP_PATH = DIST_DIR / "AutoPBI_Studio_Portable.zip"

# Files/folders explicitly included in the portable distribution
INCLUDE_FILES = [
    "README.md",
    "requirements.txt",
    "run_studio.bat",
    "run_auto_pbi.bat",
    "Requirement_Template.md",
    "HUONG_DAN_REQUIREMENT.md",
    "config/appsource_marketplace_index.json",
    "sample_data/sample_sales.csv",
]

EMPTY_WORK_DIRS = [
    "inputs",
    "custom_visuals",
    "data_warehouse",
    "output_pbi",
    "reports",
]

FORBIDDEN_STRINGS = [
    "MALV2025",
    "merged_flights.csv",
    "c_t_ph_n_t_ch_nghi_p_v_v_thi_t_k_dashboard_power_bi",
]


def ensure_sample_sales_csv(dest: Path) -> None:
    """Generate a clean synthetic sample_sales.csv matching Requirement_Template.md."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    regions = ["North", "South", "Central", "East", "West", "Highland"]
    categories = ["Electronics", "Furniture", "Office Supplies", "Appliances", "Accessories"]
    segments = ["Enterprise", "SMB", "Consumer"]
    start_dt = date(2025, 1, 1)

    rows = []
    for i in range(240):
        order_dt = start_dt + timedelta(days=rng.randint(0, 364))
        region = rng.choice(regions)
        category = rng.choice(categories)
        segment = rng.choice(segments)
        qty = rng.randint(1, 18)
        unit_price = {
            "Electronics": rng.uniform(180, 950),
            "Furniture": rng.uniform(120, 680),
            "Office Supplies": rng.uniform(15, 140),
            "Appliances": rng.uniform(90, 520),
            "Accessories": rng.uniform(20, 160),
        }[category]
        revenue = round(qty * unit_price, 2)
        margin_ratio = rng.uniform(0.18, 0.42)
        cost = round(revenue * (1.0 - margin_ratio), 2)
        is_returned = 1 if rng.random() < 0.075 else 0
        rows.append([
            order_dt.isoformat(),
            region,
            category,
            segment,
            revenue,
            cost,
            qty,
            is_returned,
        ])

    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["OrderDate", "Region", "Category", "CustomerSegment", "Revenue", "Cost", "Quantity", "IsReturned"])
        w.writerows(rows)


def copy_src_tree(src_root: Path, dst_root: Path) -> None:
    for p in src_root.rglob("*"):
        if "__pycache__" in p.parts or p.suffix in {".pyc", ".pyo"}:
            continue
        rel = p.relative_to(src_root)
        target = dst_root / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)


def audit_staged_files(stage_dir: Path) -> list[str]:
    issues: list[str] = []
    text_exts = {".py", ".md", ".bat", ".txt", ".json", ".yaml", ".yml", ".csv"}
    for p in stage_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in text_exts:
            continue
        if p.name == "appsource_marketplace_index.json":
            continue
        content = p.read_text(encoding="utf-8", errors="ignore")
        for bad in FORBIDDEN_STRINGS:
            if bad.lower() in content.lower():
                issues.append(f"{p.relative_to(stage_dir)} contains '{bad}'")
    return issues


def build_package() -> Path:
    sample_csv = ROOT / "sample_data" / "sample_sales.csv"
    ensure_sample_sales_csv(sample_csv)

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Copy source code cleanly
    copy_src_tree(ROOT / "src", STAGE_DIR / "src")

    # Copy allowed top-level & config files
    for rel in INCLUDE_FILES:
        src = ROOT / rel
        if not src.exists():
            raise FileNotFoundError(f"Missing required package file: {rel}")
        dst = STAGE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Create clean empty user directories
    for d in EMPTY_WORK_DIRS:
        dd = STAGE_DIR / d
        dd.mkdir(parents=True, exist_ok=True)
        (dd / ".gitkeep").write_text("", encoding="utf-8")

    # Privacy & portability audit
    issues = audit_staged_files(STAGE_DIR)
    if issues:
        raise RuntimeError("Privacy/portability audit failed:\n  - " + "\n  - ".join(issues))

    # Build ZIP archive
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(STAGE_DIR.rglob("*")):
            if p.is_file():
                arcname = Path("AutoPBI_Studio_Portable") / p.relative_to(STAGE_DIR)
                zf.write(p, arcname.as_posix())

    print(f"[OK] Built portable package: {ZIP_PATH} ({ZIP_PATH.stat().st_size / 1024:.1f} KB)")
    return ZIP_PATH


if __name__ == "__main__":
    build_package()
