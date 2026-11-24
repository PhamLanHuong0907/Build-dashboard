"""
In-app Power BI custom-visual marketplace.

Lets the user search ~1,300 AppSource custom visuals and install one with a single click:
the .pbiviz package is downloaded straight into <workspace>/custom_visuals and validated, so
the user never has to open AppSource / GitHub and import manually.

Source of the index: the community-maintained DataChant/PowerBI-Visuals-Marketplace repository
(it archives the .pbiviz files published on Microsoft AppSource). A snapshot is shipped in
config/appsource_marketplace_index.json and can be refreshed from the network.
"""
import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from src.pbi_generator.visual_catalog import inspect_pbiviz_package

INDEX_REL = Path("config") / "appsource_marketplace_index.json"
REMOTE_CSV = "https://raw.githubusercontent.com/DataChant/PowerBI-Visuals-Marketplace/master/Visuals%20Summary.csv"
BLOB_PREFIX = "https://github.com/DataChant/PowerBI-Visuals-Marketplace/blob/main/"
RAW_PREFIX = "https://raw.githubusercontent.com/DataChant/PowerBI-Visuals-Marketplace/main/"


def _rows_to_records(text: str) -> List[Dict[str, Any]]:
    records = []
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        url = (r.get("Versioned pbiviz") or "").strip().replace(BLOB_PREFIX, RAW_PREFIX)
        guid = (r.get("Visual GUID") or "").strip()
        if guid and url.startswith("http"):
            records.append({
                "name": (r.get("Custom Visual") or "").strip(),
                "publisher": (r.get("Publisher") or "").strip(),
                "description": (r.get("Description") or "").strip()[:240],
                "version": (r.get("Version") or "").strip(),
                "certified": str(r.get("Is Certified", "")).strip().lower() == "true",
                "guid": guid,
                "pbiviz_url": url,
            })
    return records


def load_index(root: Path, refresh: bool = False) -> List[Dict[str, Any]]:
    path = Path(root) / INDEX_REL
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    resp = requests.get(REMOTE_CSV, timeout=30)
    resp.raise_for_status()
    records = _rows_to_records(resp.text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return records


def installed_guids(root: Path) -> set:
    cv = Path(root) / "custom_visuals"
    return {p.stem for p in cv.glob("*.pbiviz")} if cv.exists() else set()


def search(root: Path, query: str = "", limit: int = 60) -> Dict[str, Any]:
    index = load_index(root)
    done = installed_guids(root)
    q = (query or "").strip().lower()
    hits = []
    for rec in index:
        hay = f"{rec['name']} {rec['publisher']} {rec['description']} {rec['guid']}".lower()
        if not q or q in hay:
            hits.append(dict(rec, installed=rec["guid"] in done))
    hits.sort(key=lambda r: (not r["certified"], r["name"].lower()))
    return {"total": len(index), "matched": len(hits), "items": hits[:limit]}


def install(root: Path, guid: str) -> Dict[str, Any]:
    index = load_index(root)
    rec: Optional[Dict[str, Any]] = next((r for r in index if r["guid"] == guid), None)
    if rec is None:
        raise ValueError(f"Visual '{guid}' không có trong danh mục")
    cv = Path(root) / "custom_visuals"
    cv.mkdir(parents=True, exist_ok=True)
    dest = cv / f"{guid}.pbiviz"
    resp = requests.get(rec["pbiviz_url"], timeout=90)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    try:
        meta = inspect_pbiviz_package(dest)
    except Exception as exc:  # corrupted / not a zip
        dest.unlink(missing_ok=True)
        raise ValueError(f"File tải về không phải gói .pbiviz hợp lệ: {exc}") from exc
    if not meta:
        dest.unlink(missing_ok=True)
        raise ValueError("Gói .pbiviz không chứa package.json hợp lệ")
    return {"visual": meta, "size_bytes": len(resp.content), "source": rec["pbiviz_url"]}
