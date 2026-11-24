"""
Phase 1: Business Analysis & Specification Parser.
Reads Requirement.md and project_blueprint.json / project_spec.yaml,
extracts metadata, KPIs, slicers, and dashboard specifications,
and allows programmatic or Web UI updates.
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


class SpecParser:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.blueprint_json_path = self.workspace_dir / "config" / "project_blueprint.json"
        self.spec_yaml_path = self.workspace_dir / "config" / "project_spec.yaml"
        self.requirement_md_path = self.workspace_dir / "Requirement.md"

    def load_blueprint(self) -> Dict[str, Any]:
        """Load the canonical blueprint from JSON (or YAML if JSON is older)."""
        if self.blueprint_json_path.exists():
            with open(self.blueprint_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Keep YAML copy synchronized for human readability
            self.save_yaml(data)
            return data
        elif self.spec_yaml_path.exists():
            with open(self.spec_yaml_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        raise FileNotFoundError(f"Blueprint not found at {self.blueprint_json_path}")

    def load_blueprint_or_empty(self) -> Dict[str, Any]:
        """Blueprint of the last run, or an empty skeleton on a fresh install (no data of any previous user)."""
        try:
            return self.load_blueprint()
        except FileNotFoundError:
            return {
                "project": {
                    "name": "My_Dashboard",
                    "title": "",
                    "source_csv": "",
                    "requirement_doc": "",
                    "warehouse_dir": "data_warehouse",
                    "clean_csv_dir": "data_warehouse/csv",
                    "output_pbi_dir": "output_pbi",
                    "fact_table_name": "Fact_Main",
                    "canvas": {"width": 1280, "height": 720, "aspect_ratio": "16:9"},
                },
                "dax_measures": [],
                "dashboards": [],
                "is_empty": True,
            }

    def save_blueprint(self, data: Dict[str, Any]) -> None:
        """Save updated blueprint to both JSON and YAML."""
        self.blueprint_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.blueprint_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.save_yaml(data)

    def save_yaml(self, data: Dict[str, Any]) -> None:
        self.spec_yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.spec_yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def parse_requirement_markdown(self, md_path: Optional[str] = None) -> Dict[str, Any]:
        """Extract structured sections from Requirement.md to verify completeness."""
        target_path = Path(md_path) if md_path else self.requirement_md_path
        if not target_path.exists():
            return {"exists": False, "path": str(target_path)}

        text = target_path.read_text(encoding="utf-8")
        headings = re.findall(r"^(#{1,3})\s+(.+)$", text, flags=re.MULTILINE)
        dashboards_found = re.findall(r"^#\s+DASHBOARD\s+\d+:\s+(.+)$", text, flags=re.MULTILINE)
        requirements_found = re.findall(r"^##\s+(R\d+\s+[–-]\s+.+)$", text, flags=re.MULTILINE)
        charts_found = re.findall(r"^###\s+([A-Z]{2}\d{2}-\d{2}\s+[–-]\s+.+)$", text, flags=re.MULTILINE)

        return {
            "exists": True,
            "path": str(target_path),
            "line_count": len(text.splitlines()),
            "headings_count": len(headings),
            "dashboards": [d.strip() for d in dashboards_found],
            "requirements": [r.strip() for r in requirements_found],
            "charts": [c.strip() for c in charts_found],
        }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    parser = SpecParser(str(root))
    bp = parser.load_blueprint()
    md_info = parser.parse_requirement_markdown()
    print(f"Loaded blueprint: {bp['project']['name']} ({len(bp['dashboards'])} pages, {len(bp['dax_measures'])} DAX measures)")
    print(f"Parsed Requirement.md: {md_info['line_count']} lines, {len(md_info['requirements'])} business requirements, {len(md_info['charts'])} chart specs.")
