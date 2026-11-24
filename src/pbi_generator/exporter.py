"""Standalone Power BI Dashboard Exporter.

Solves Power BI Desktop's PBIR -> PBIX "Save As" limitation by packaging the
active dashboard (.pbip + .Report + .SemanticModel + .pbi/cache.abf, and
optionally compact Parquet files with rewritten M paths) into a self-contained
folder under saved_dashboards/ (or any custom destination path) BEFORE the user
cleans up temporary workspace data (data_warehouse/, inputs/, output_pbi/).
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _folder_size_bytes(path: Path) -> int:
    total = 0
    if path.exists():
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    return total


def inspect_dashboard_export_status(root: Path, blueprint: Dict[str, Any]) -> Dict[str, Any]:
    proj = (blueprint or {}).get("project") or {}
    proj_name = proj.get("name") or ""
    out_dir = root / proj.get("output_pbi_dir", "output_pbi")
    pbip_path = out_dir / f"{proj_name}.pbip" if proj_name else None
    cache_abf = out_dir / f"{proj_name}.SemanticModel" / ".pbi" / "cache.abf" if proj_name else None

    has_pbip = bool(pbip_path and pbip_path.is_file())
    has_cache = bool(cache_abf and cache_abf.is_file() and cache_abf.stat().st_size > 0)
    cache_mb = round(cache_abf.stat().st_size / (1024 * 1024), 2) if has_cache else 0.0

    wh_dir = root / proj.get("warehouse_dir", "data_warehouse")
    parquet_bytes = sum(p.stat().st_size for p in wh_dir.glob("*.parquet")) if wh_dir.exists() else 0

    saved_root = root / "saved_dashboards"
    saved_items: List[Dict[str, Any]] = []
    if saved_root.exists():
        for item in sorted(saved_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not item.is_dir():
                continue
            pbips = list(item.glob("*.pbip"))
            if not pbips:
                continue
            sz = _folder_size_bytes(item)
            saved_items.append({
                "folder_name": item.name,
                "path": str(item),
                "pbip_path": str(pbips[0]),
                "mb": round(sz / (1024 * 1024), 2),
                "has_cache": any(item.rglob("cache.abf")),
                "has_parquet": (item / "data").exists() and any((item / "data").glob("*.parquet")),
                "modified": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })

    return {
        "project_name": proj_name,
        "has_pbip": has_pbip,
        "has_cache_abf": has_cache,
        "cache_mb": cache_mb,
        "parquet_mb": round(parquet_bytes / (1024 * 1024), 2),
        "default_export_root": str(saved_root),
        "saved_dashboards": saved_items,
    }


def _rewrite_model_bim_parquet_paths(bim_path: Path, data_dir: Path) -> None:
    """Point Parquet.Document(File.Contents(...)) expressions in model.bim to exported data/ folder."""
    if not bim_path.is_file():
        return
    bim = json.loads(bim_path.read_text(encoding="utf-8"))
    pattern = re.compile(r'File\.Contents\("([^"]+?([A-Za-z0-9_]+\.parquet))"\)')

    def repl(match: re.Match[str]) -> str:
        fname = match.group(2)
        new_p = (data_dir / fname).resolve()
        if new_p.exists():
            escaped = str(new_p).replace("\\", "\\\\")
            return f'File.Contents("{escaped}")'
        return match.group(0)

    for tbl in bim.get("model", {}).get("tables", []):
        for part in tbl.get("partitions", []):
            src = part.get("source") or {}
            expr = src.get("expression")
            if isinstance(expr, list):
                src["expression"] = [pattern.sub(repl, line) for line in expr]
            elif isinstance(expr, str):
                src["expression"] = pattern.sub(repl, expr)

    bim_path.write_text(json.dumps(bim, indent=2, ensure_ascii=False), encoding="utf-8")


def export_standalone_dashboard(
    root: Path,
    blueprint: Dict[str, Any],
    dest_dir: str | None = None,
    include_parquet: bool | None = None,
    make_zip: bool = False,
) -> Dict[str, Any]:
    proj = (blueprint or {}).get("project") or {}
    proj_name = proj.get("name")
    if not proj_name or blueprint.get("is_empty"):
        raise ValueError("Chưa có dự án Power BI nào để lưu. Hãy chạy 'Chạy Tự Động A–Z' trước.")

    out_dir = root / proj.get("output_pbi_dir", "output_pbi")
    pbip_src = out_dir / f"{proj_name}.pbip"
    rep_src = out_dir / f"{proj_name}.Report"
    sm_src = out_dir / f"{proj_name}.SemanticModel"
    if not pbip_src.is_file() or not rep_src.is_dir() or not sm_src.is_dir():
        raise FileNotFoundError(f"Không tìm thấy dự án {proj_name}.pbip trong {out_dir}. Hãy sinh Power BI trước.")

    cache_abf = sm_src / ".pbi" / "cache.abf"
    has_cache = cache_abf.is_file() and cache_abf.stat().st_size > 0

    # If Power BI hasn't cached data in cache.abf yet, always bundle compact Parquet so it works standalone
    bundle_parquet = (not has_cache) if include_parquet is None else bool(include_parquet)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if dest_dir and dest_dir.strip():
        target = Path(dest_dir.strip())
        if not target.is_absolute():
            target = root / target
        # Avoid overwriting an existing folder if user pointed to a parent directory like D:\Dashboards
        if target.exists() and any(target.iterdir()) and not (target / f"{proj_name}.pbip").exists():
            target = target / f"{proj_name}_{stamp}"
    else:
        target = root / "saved_dashboards" / f"{proj_name}_{stamp}"

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    # Copy .pbip, .Report, .SemanticModel (including .pbi/cache.abf if present!)
    shutil.copy2(pbip_src, target / f"{proj_name}.pbip")
    shutil.copytree(rep_src, target / f"{proj_name}.Report")
    shutil.copytree(sm_src, target / f"{proj_name}.SemanticModel")

    # Optionally bundle compact Parquet files (5-10x smaller than CSV) and rewrite M paths
    if bundle_parquet:
        wh_dir = root / proj.get("warehouse_dir", "data_warehouse")
        data_dst = target / "data"
        data_dst.mkdir(parents=True, exist_ok=True)
        if wh_dir.exists():
            for pq_file in wh_dir.glob("*.parquet"):
                shutil.copy2(pq_file, data_dst / pq_file.name)
        _rewrite_model_bim_parquet_paths(target / f"{proj_name}.SemanticModel" / "model.bim", data_dst)

    # Copy lightweight markdown audit reports
    rep_md_dir = root / "reports"
    if rep_md_dir.exists():
        docs_dst = target / "audit_reports"
        copied_md = False
        for md in rep_md_dir.glob("*.md"):
            docs_dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(md, docs_dst / md.name)
            copied_md = True
        if not copied_md and docs_dst.exists():
            shutil.rmtree(docs_dst)

    (target / "CACH_MO_DASHBOARD.txt").write_text(
        f"Dashboard: {proj_name}\n"
        f"Luu luc  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Du lieu  : {'Da nhung san cache.abf' if has_cache else 'Chua co cache.abf'}"
        f"{' + Kem Parquet gọn nhe trong thu muc data/' if bundle_parquet else ''}\n\n"
        f"Cach mo  : Nhap dup vao file '{proj_name}.pbip' de mo bang Power BI Desktop.\n"
        f"Ban co the xoa sach du lieu tam trong Auto-PBI Studio ma khong anh huong thu muc nay.\n",
        encoding="utf-8",
    )

    zip_path_str = ""
    if make_zip:
        zp = target.with_suffix(".zip")
        with zipfile.ZipFile(zp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for p in sorted(target.rglob("*")):
                if p.is_file():
                    zf.write(p, (Path(target.name) / p.relative_to(target)).as_posix())
        zip_path_str = str(zp)

    total_mb = round(_folder_size_bytes(target) / (1024 * 1024), 2)
    return {
        "export_dir": str(target),
        "pbip_path": str(target / f"{proj_name}.pbip"),
        "zip_path": zip_path_str,
        "total_mb": total_mb,
        "has_cache_abf": has_cache,
        "bundled_parquet": bundle_parquet,
        "status_info": inspect_dashboard_export_status(root, blueprint),
    }
