"""
Phase 6 & 8: Power BI Project (.pbip) & Power BI Template (.pbit) Packager.
Generates:
1. Full Power BI Project (.pbip) folder structure:
   - output_pbi/US_Flight_Operations.pbip
   - output_pbi/US_Flight_Operations.SemanticModel/model.bim & definition.pbidataset
   - output_pbi/US_Flight_Operations.Report/report.json & definition.pbir & BaseThemes/CY24SU06.json
2. Standalone Power BI Template (.pbit) ZIP archive:
   - output_pbi/US_Flight_Operations.pbit (can also be double-clicked in Power BI Desktop!)
"""
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Dict

from src.pbi_generator.bim_builder import build_model_bim
from src.pbi_generator.report_builder import ReportBuilder


BASE_THEME_JSON = {
    "name": "CY24SU06",
    "dataColors": [
        "#1D4ED8",
        "#0EA5E9",
        "#10B981",
        "#F59E0B",
        "#EF4444",
        "#8B5CF6",
        "#EC4899",
        "#64748B",
        "#14B8A6",
        "#F97316",
    ],
    "background": "#F1F5F9",
    "foreground": "#0F172A",
    "tableAccent": "#1D4ED8",
}


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="" />
  <Default Extension="xml" ContentType="" />
  <Override PartName="/Version" ContentType="" />
  <Override PartName="/DataModelSchema" ContentType="" />
  <Override PartName="/Report/Layout" ContentType="" />
  <Override PartName="/Settings" ContentType="" />
  <Override PartName="/Metadata" ContentType="" />
</Types>"""


def generate_pbi_artifacts(workspace_dir: str, blueprint: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(workspace_dir)
    out_dir = root / blueprint["project"].get("output_pbi_dir", "output_pbi")
    proj_name = blueprint["project"]["name"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Build Semantic Model (model.bim) and Report Layout (report.json)
    model_bim = build_model_bim(workspace_dir, blueprint)
    report_builder = ReportBuilder(blueprint, workspace_dir=workspace_dir)
    report_json = report_builder.build_report_json()

    # 2. Write Power BI Project (.pbip) Structure
    pbip_file = out_dir / f"{proj_name}.pbip"
    sm_dir = out_dir / f"{proj_name}.SemanticModel"
    rep_dir = out_dir / f"{proj_name}.Report"
    theme_dir = rep_dir / "StaticResources" / "SharedResources" / "BaseThemes"
    sm_dir.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)
    theme_dir.mkdir(parents=True, exist_ok=True)

    pbip_manifest = {
        "version": "1.0",
        "artifacts": [
            {
                "report": {
                    "path": f"{proj_name}.Report",
                }
            }
        ],
        "settings": {
            "enableAutoRecovery": True,
        },
    }
    pbip_file.write_text(json.dumps(pbip_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # SemanticModel directory files
    (sm_dir / "definition.pbidataset").write_text(
        json.dumps({"version": "1.0", "settings": {}}, indent=2), encoding="utf-8"
    )
    (sm_dir / ".platform").write_text(
        json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "SemanticModel", "displayName": proj_name},
            "config": {"version": "2.0", "logicalId": "9458a110-b60c-4fed-a22f-5a9445d28ed8"},
        }, indent=2),
        encoding="utf-8",
    )
    (sm_dir / "model.bim").write_text(
        json.dumps(model_bim, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Report directory files
    (rep_dir / "definition.pbir").write_text(
        json.dumps({
            "version": "1.0",
            "datasetReference": {
                "byPath": {"path": f"../{proj_name}.SemanticModel"},
                "byConnection": None,
            },
        }, indent=2),
        encoding="utf-8",
    )
    (rep_dir / ".platform").write_text(
        json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Report", "displayName": proj_name},
            "config": {"version": "2.0", "logicalId": "8458a110-b60c-4fed-a22f-5a9445d28ed7"},
        }, indent=2),
        encoding="utf-8",
    )
    (rep_dir / "report.json").write_text(
        json.dumps(report_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (theme_dir / "CY24SU06.json").write_text(
        json.dumps(BASE_THEME_JSON, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Copy any imported .pbiviz custom visuals into Report/CustomVisuals/<guid>/
    cv_src_dir = root / "custom_visuals"
    if cv_src_dir.exists() and report_json.get("publicCustomVisuals"):
        cv_out_dir = rep_dir / "CustomVisuals"
        cv_out_dir.mkdir(parents=True, exist_ok=True)
        for pbiviz_file in cv_src_dir.glob("*.pbiviz"):
            try:
                with zipfile.ZipFile(pbiviz_file, "r") as czf:
                    pkg_name = next((n for n in czf.namelist() if n.endswith("package.json")), None)
                    if pkg_name:
                        pkg = json.loads(czf.read(pkg_name).decode("utf-8-sig"))
                        guid = pkg.get("visual", {}).get("guid")
                        if guid and guid in report_json["publicCustomVisuals"]:
                            target_cv = cv_out_dir / guid
                            target_cv.mkdir(parents=True, exist_ok=True)
                            czf.extractall(target_cv)
            except Exception:
                continue

    # 3. Also package a standalone .pbit (Power BI Template ZIP package)
    pbit_path = out_dir / f"{proj_name}.pbit"
    with zipfile.ZipFile(pbit_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES_XML.encode("utf-8"))
        zf.writestr("Version", "1.28".encode("utf-16-le"))
        zf.writestr("DataModelSchema", json.dumps(model_bim, ensure_ascii=False).encode("utf-16-le"))
        zf.writestr("Report/Layout", json.dumps(report_json, ensure_ascii=False).encode("utf-16-le"))
        zf.writestr("Report/StaticResources/SharedResources/BaseThemes/CY24SU06.json", json.dumps(BASE_THEME_JSON).encode("utf-8"))
        zf.writestr("Settings", json.dumps({"Version": 4, "ReportSettings": {}}).encode("utf-16-le"))
        zf.writestr("Metadata", json.dumps({"Version": 5, "AutoCreatedRelationships": [], "CreatedFrom": "Cloud", "CreatedFromRelease": "2024.11"}).encode("utf-16-le"))

    n_pages = len(report_json["sections"])
    n_visuals = sum(len(s["visualContainers"]) for s in report_json["sections"])
    n_tables = len(model_bim["model"]["tables"])
    n_measures = sum(len(t.get("measures", [])) for t in model_bim["model"]["tables"])
    n_rels = len(model_bim["model"]["relationships"])

    summary = {
        "pbip_path": str(pbip_file),
        "pbit_path": str(pbit_path),
        "model_bim_path": str(sm_dir / "model.bim"),
        "report_json_path": str(rep_dir / "report.json"),
        "pages_count": n_pages,
        "visuals_count": n_visuals,
        "tables_count": n_tables,
        "dax_measures_count": n_measures,
        "relationships_count": n_rels,
    }
    print(
        f"[Phase 6] Generated Power BI Project (.pbip) & Template (.pbit): "
        f"{n_pages} pages, {n_visuals} visuals/slicers/cards, {n_tables} tables, {n_measures} DAX measures, {n_rels} Star Schema relationships."
    )
    return summary


if __name__ == "__main__":
    from src.parser.spec_parser import SpecParser
    root = Path(__file__).resolve().parents[2]
    bp = SpecParser(str(root)).load_blueprint()
    generate_pbi_artifacts(str(root), bp)
