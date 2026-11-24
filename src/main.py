"""
Main CLI & automated pipeline orchestrator for Auto-PBI Dashboard Studio.

Accepts ANY CSV (--csv) and ANY Requirement.md (--req) and runs, in order:
  1. Introspect the CSV + compile the Requirement.md into a blueprint
  2. Data profiling & quality audit
  3. ETL cleaning + Star Schema warehouse (Parquet + CSV)      <- skipped only when the very same CSV was already processed
  4. Independent KPI audit of every DAX measure in the Requirement  <- always re-run, so it always matches the current Requirement.md
  5. Power BI project (.pbip / .pbit) generation, optional launch + live data refresh
"""
import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.parser.spec_parser import SpecParser
from src.parser.universal_compiler import compile_blueprint_from_csv_and_markdown
from src.etl.profiler import run_profiling
from src.etl.warehouse_builder import build_data_warehouse
from src.pbi_connector.dax_validator import run_kpi_validation
from src.pbi_connector.live_refresh import refresh_running_powerbi
from src.pbi_generator.pbip_packager import generate_pbi_artifacts


def launch_powerbi_desktop(pbip_path: str, restart_if_open: bool = True) -> bool:
    """Open the generated .pbip with Power BI Desktop through the Windows shell (interactive desktop session)."""
    if restart_if_open:
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Stop-Process -Name PBIDesktop, msmdsrv, Microsoft.Mashup.Container* -Force -ErrorAction SilentlyContinue",
                ],
                capture_output=True,
            )
            time.sleep(1.5)
        except Exception:
            pass
    resolved = str(Path(pbip_path).resolve())
    try:
        subprocess.Popen(["cmd", "/c", "start", "", resolved], close_fds=True)
        print(f"[Auto-PBI] Launched Power BI Desktop via Windows Shell -> {resolved}")
        return True
    except Exception as e:
        print(f"[Auto-PBI] Could not auto-launch Power BI Desktop: {e}")
        return False


def _locate(root: Path, name: Optional[str], kind: str) -> Tuple[str, Path]:
    """Resolve a user supplied path: absolute, relative to the workspace, or inside <workspace>/inputs."""
    if not name:
        raise FileNotFoundError(f"Chưa chọn {kind}. Hãy tải file lên hoặc nhập đường dẫn.")
    p = Path(name)
    for cand in ([p] if p.is_absolute() else [root / p, root / "inputs" / p]):
        if cand.exists():
            return name, cand
    pattern = "*.csv" if kind == "file CSV" else "*.md"
    available = sorted({q.name for d in (root, root / "inputs") if d.exists() for q in d.glob(pattern)})
    raise FileNotFoundError(f"Không tìm thấy {kind}: '{name}'. Các file hiện có: {available or 'chưa có file nào'}")


def _csv_fingerprint(csv_full: Path) -> Dict[str, Any]:
    st = csv_full.stat()
    return {"path": str(csv_full.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _etl_cache_valid(root: Path, blueprint: Dict[str, Any], csv_full: Path) -> bool:
    """The warehouse can be reused only if it was built from this exact CSV (path + size + mtime) in the same mode."""
    manifest = root / "reports" / "etl_cache.json"
    if not manifest.exists():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return False
    proj = blueprint["project"]
    wh = root / proj.get("warehouse_dir", "data_warehouse")
    return (
        data.get("csv") == _csv_fingerprint(csv_full)
        and data.get("dataset_mode") == proj.get("dataset_mode")
        and (wh / f"{proj.get('fact_table_name', 'Fact_Main')}.parquet").exists()
        and (wh / "Data_Quality_Stats.parquet").exists()
        and (root / "reports" / "profiling_summary.json").exists()
    )


def _write_etl_cache(root: Path, blueprint: Dict[str, Any], csv_full: Path) -> None:
    manifest = root / "reports" / "etl_cache.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({"csv": _csv_fingerprint(csv_full), "dataset_mode": blueprint["project"].get("dataset_mode")}, indent=2),
        encoding="utf-8",
    )


def run_full_pipeline(
    workspace_dir: str,
    csv_path: Optional[str] = None,
    req_md_path: Optional[str] = None,
    project_name: Optional[str] = None,
    skip_etl: bool = False,
    open_pbi: bool = False,
) -> Dict[str, Any]:
    t0 = time.time()
    root = Path(workspace_dir)
    parser = SpecParser(workspace_dir)

    if csv_path or req_md_path:
        target_csv, csv_full = _locate(root, csv_path, "file CSV")
        target_req, req_full = _locate(root, req_md_path, "file Requirement .md")
        print(f"[Phase 1] Compiling blueprint from CSV='{target_csv}' and Requirement='{target_req}'...")
        blueprint = compile_blueprint_from_csv_and_markdown(workspace_dir, str(csv_full), str(req_full), project_name=project_name)
        parser.save_blueprint(blueprint)
        if not skip_etl and _etl_cache_valid(root, blueprint, csv_full):
            print("[Auto-PBI] Same CSV already processed -> reusing cached Star Schema warehouse (KPI audit is still recomputed).")
            skip_etl = True
    else:
        blueprint = parser.load_blueprint()
        target_csv = blueprint["project"].get("source_csv", "")
        target_req = blueprint["project"].get("requirement_doc", "")
        csv_full = Path(target_csv) if Path(target_csv).is_absolute() else root / target_csv
        req_full = Path(target_req) if Path(target_req).is_absolute() else root / target_req

    md_info = parser.parse_requirement_markdown(str(req_full))
    results: Dict[str, Any] = {
        "blueprint_project": blueprint["project"]["name"],
        "dataset_mode": blueprint["project"].get("dataset_mode"),
        "source_csv": target_csv,
        "requirement_doc": md_info,
        "etl_reused": bool(skip_etl),
    }

    if not skip_etl:
        results["profiling"] = run_profiling(workspace_dir, csv_rel_or_abs=str(csv_full))
        results["warehouse"] = build_data_warehouse(workspace_dir, csv_rel_or_abs=str(csv_full), blueprint=blueprint)
        if csv_full.exists():
            _write_etl_cache(root, blueprint, csv_full)

    # Always re-audit: the KPI audit must follow the *current* Requirement.md, not the one used for the last ETL.
    results["kpi_validation"] = run_kpi_validation(workspace_dir, blueprint=blueprint)

    results["pbi_artifacts"] = generate_pbi_artifacts(workspace_dir, blueprint)
    results["total_elapsed_seconds"] = round(time.time() - t0, 2)

    if open_pbi:
        launch_powerbi_desktop(results["pbi_artifacts"]["pbip_path"])
        results["live_refresh"] = refresh_running_powerbi(wait_for_model_seconds=25)

    return results


def main():
    argp = argparse.ArgumentParser(description="Auto-PBI Dashboard Studio (any CSV + Requirement.md -> Power BI)")
    argp.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]), help="Workspace root directory")
    argp.add_argument("--csv", default=None, help="Path to the input CSV file")
    argp.add_argument("--req", default=None, help="Path to the Requirement.md specification")
    argp.add_argument("--project-name", default=None, help="Optional Power BI project name")
    argp.add_argument("--skip-etl", action="store_true", help="Skip profiling & ETL (reuse existing data_warehouse)")
    argp.add_argument("--open-pbi", action="store_true", help="Open the generated .pbip in Power BI Desktop and refresh data")
    argp.add_argument("--web", action="store_true", help="Start the Web UI")
    argp.add_argument("--port", type=int, default=8505, help="Web UI port (default 8505; the next free port is used if busy)")
    argp.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically with --web")
    args = argp.parse_args()

    if args.web:
        from src.web_ui import start_web_server
        start_web_server(args.workspace, port=args.port, open_browser=not args.no_browser)
    else:
        run_full_pipeline(
            args.workspace,
            csv_path=args.csv,
            req_md_path=args.req,
            project_name=args.project_name,
            skip_etl=args.skip_etl,
            open_pbi=args.open_pbi,
        )


if __name__ == "__main__":
    main()
