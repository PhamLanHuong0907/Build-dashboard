"""
Universal Requirement.md + CSV Schema Compiler.
Transforms ANY input CSV file + ANY Requirement.md specification into a complete,
executable Blueprint (project_blueprint.json).
Never bypasses the user's Requirement.md file: always parses its Title, DAX measures,
KPI tables, # DASHBOARD / ## DASHBOARD sections, Slicers, KPI Cards, and ### / #### Chart specs.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


from src.pbi_generator.visual_catalog import match_visual_type_from_text


def map_chart_type(raw_type: str) -> str:
    return match_visual_type_from_text(raw_type)


def inspect_csv_sample(csv_path: Path, sample_rows: int = 10000) -> Dict[str, Any]:
    """Fast inspection of any CSV file to classify columns into Date, Dimension, Measure, Flag, HHMM."""
    df = pd.read_csv(csv_path, nrows=sample_rows, low_memory=False)
    cols_info = []
    date_col = None
    dim_cols = []
    measure_cols = []
    flag_cols = []
    hhmm_cols = []

    for col in df.columns:
        s = df[col]
        dtype_str = str(s.dtype)
        nunique = int(s.nunique(dropna=True))
        clower = col.lower()

        is_date = False
        if ("date" in clower or "ngay" in clower) or (dtype_str == "object" and "time" in clower):
            sample_non_null = s.dropna().head(50).astype(str)
            if len(sample_non_null) > 0:
                parsed = pd.to_datetime(sample_non_null, errors="coerce")
                if parsed.notna().mean() > 0.8:
                    is_date = True
                    if date_col is None:
                        date_col = col

        is_numeric = pd.api.types.is_numeric_dtype(s)
        is_flag = False
        is_hhmm = False

        if is_numeric and not is_date:
            non_null_vals = s.dropna()
            unique_vals = set(non_null_vals.unique().tolist()) if nunique <= 5 else set()
            if unique_vals and unique_vals.issubset({0, 1, 0.0, 1.0}) and len(unique_vals) >= 1:
                is_flag = True
                flag_cols.append(col)
            elif any(k in clower for k in ["deptime", "arrtime", "wheelsoff", "wheelson", "hhmm"]):
                is_hhmm = True
                hhmm_cols.append(col)
            elif clower in ("year", "quarter", "month", "dayofmonth", "dayofweek") or (
                clower.endswith(("id", "key", "code", "no")) and nunique < sample_rows * 0.5
            ):
                dim_cols.append(col)
            else:
                measure_cols.append(col)
        elif not is_date:
            dim_cols.append(col)

        cols_info.append({
            "name": col,
            "dtype": dtype_str,
            "nunique_sample": nunique,
            "is_date": is_date,
            "is_numeric": is_numeric,
            "is_flag": is_flag,
            "is_hhmm": is_hhmm,
        })

    return {
        "columns": [c["name"] for c in cols_info],
        "columns_detail": cols_info,
        "primary_date_col": date_col,
        "dimension_cols": dim_cols,
        "measure_cols": measure_cols,
        "flag_cols": flag_cols,
        "hhmm_cols": hhmm_cols,
    }


def _parse_markdown_tables(md_text: str) -> List[List[Dict[str, str]]]:
    """Extract all GitHub-Flavored Markdown tables as list of dicts."""
    tables = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and line.endswith("|") and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            if sep.startswith("|") and "---" in sep:
                headers = [h.strip().strip("*`") for h in line.strip("|").split("|")]
                rows = []
                i += 2
                while i < len(lines):
                    rline = lines[i].strip()
                    if not (rline.startswith("|") and rline.endswith("|")):
                        break
                    cells = [c.strip() for c in rline.strip("|").split("|")]
                    if len(cells) == len(headers):
                        rows.append(dict(zip(headers, cells)))
                    i += 1
                if rows:
                    tables.append(rows)
                continue
        i += 1
    return tables


def _extract_dax_code_blocks(md_text: str, fact_table: str) -> List[Dict[str, str]]:
    """Extract DAX measures from ```DAX ... ``` code blocks in Requirement.md."""
    pattern = re.compile(r"```(?:dax|DAX)\s*\n(.*?)```", re.DOTALL)
    measures = []
    for match in pattern.finditer(md_text):
        block = match.group(1).strip()
        if "=" in block:
            parts = block.split("=", 1)
            m_name = parts[0].strip()
            m_expr = " ".join(parts[1].strip().split())
            m_expr = m_expr.replace("Fact_Flight_Operations", fact_table).replace("Fact_Flight", fact_table)
            low = m_name.lower()
            fmt = "0.00%" if any(w in low for w in ["%", "rate", "otp", "share", "pct", "percent", "tỷ lệ", "margin"]) else (
                "0.0" if any(w in low for w in ["avg", "average", "variance", "median", "p90", "p95", "(p)", "(mph)"]) else "#,##0"
            )
            measures.append({
                "name": m_name,
                "folder": "01. Requirement DAX Measures",
                "expression": m_expr,
                "formatString": fmt,
                "description": f"Trích xuất từ khối DAX trong Requirement.md ({m_name})",
            })
    return measures


def _apply_dictionary_overrides(csv_info: Dict[str, Any], md_text: str) -> Dict[str, Any]:
    """Honour the user's data dictionary: a table with columns `Thuộc tính` + `Nhóm` (Date/Dimension/Measure/Flag)."""
    by_lower = {c.lower(): c for c in csv_info["columns"]}
    lists = {"date": None, "dimension": "dimension_cols", "measure": "measure_cols", "flag": "flag_cols"}
    for tbl in _parse_markdown_tables(md_text):
        keys = {k.lower(): k for k in tbl[0]}
        name_k = next((keys[k] for k in keys if k.startswith("thuộc tính") or k in ("column", "attribute", "field", "cột")), None)
        grp_k = next((keys[k] for k in keys if k.startswith("nhóm") or k in ("group", "type")), None)
        if not name_k or not grp_k:
            continue
        for row in tbl:
            col = by_lower.get(row[name_k].strip().strip("`*").lower())
            grp = next((g for g in lists if row[grp_k].strip().strip("`*").lower().startswith(g)), None)
            if not col or not grp:
                continue
            for lname in ("dimension_cols", "measure_cols", "flag_cols"):
                if col in csv_info[lname]:
                    csv_info[lname].remove(col)
            if grp == "date":
                if not csv_info.get("primary_date_col"):
                    csv_info["primary_date_col"] = col
            else:
                csv_info[lists[grp]].append(col)
    return csv_info


_AGG_SHORT = {"SUM": "SUM", "AVG": "AVERAGE", "AVERAGE": "AVERAGE", "MIN": "MIN", "MAX": "MAX", "MEDIAN": "MEDIAN", "DISTINCTCOUNT": "DISTINCTCOUNT"}


def _shorthand_to_dax(raw: str, fact_table: str, col_lookup: Dict[str, str]) -> Optional[str]:
    f = raw.strip().strip("`").strip().replace("Fact_Flight_Operations", fact_table)
    if re.fullmatch(r"COUNTROWS\(\s*[^)]*\)", f, re.I):
        return f"COUNTROWS('{fact_table}')"
    m = re.fullmatch(r"(SUM|AVG|AVERAGE|MIN|MAX|MEDIAN|DISTINCTCOUNT)\(\s*'?([A-Za-z0-9_]+)'?\s*\)", f, re.I)
    if m:
        col = col_lookup.get(m.group(2).lower(), m.group(2))
        return f"{_AGG_SHORT[m.group(1).upper()]}('{fact_table}'[{col}])"
    if re.search(r"'[^']+'\[|\[[^\]]+\]", f) and re.match(r"(DIVIDE|CALCULATE|SUM|AVERAGE|COUNTROWS|IF|MAX|MIN|MEDIAN|PERCENTILE)", f, re.I):
        return f
    return None


def _extract_kpi_table_measures(md_text: str, fact_table: str, col_lookup: Dict[str, str]) -> List[Dict[str, str]]:
    """KPI tables (columns `KPI` + `Công thức`/`Formula`) -> DAX measures (only recognised shorthand or full DAX)."""
    out: List[Dict[str, str]] = []
    for tbl in _parse_markdown_tables(md_text):
        keys = {k.lower(): k for k in tbl[0]}
        f_k = next((keys[k] for k in keys if k.startswith("công thức") or k in ("formula", "dax")), None)
        if "kpi" not in keys or not f_k:
            continue
        u_k = next((keys[k] for k in keys if k.startswith("đơn vị") or k == "unit"), None)
        for row in tbl:
            name = row[keys["kpi"]].strip().strip("*`")
            dax = _shorthand_to_dax(row[f_k], fact_table, col_lookup)
            if not name or not dax:
                continue
            unit = row.get(u_k, "") if u_k else ""
            fmt = "0.00%" if ("%" in unit or "rate" in name.lower() or "%" in name) else ("0.00" if "avg" in name.lower() else "#,##0")
            out.append({"name": name, "folder": "01. Requirement KPI Table", "expression": dax, "formatString": fmt,
                        "description": f"Bảng KPI trong Requirement: {row[f_k].strip()}"})
    return out


def is_us_flight_dataset(csv_info: Dict[str, Any]) -> bool:
    """Check if the input CSV matches the US Flight Operations BTS schema."""
    cols = set(csv_info.get("columns", []))
    required = {"FlightDate", "Reporting_Airline", "Origin", "Dest", "DepDelay", "ArrDelay", "Cancelled", "Diverted"}
    return required.issubset(cols)


def _get_base_aviation_dax_measures() -> List[Dict[str, Any]]:
    """Comprehensive base DAX measures for the US Flight Operations Star Schema, including aliases used across different Requirement.md versions."""
    return [
        {"name": "Total Flights", "folder": "01. Volume & Status", "expression": "COUNTROWS('Fact_Flight')", "formatString": "#,##0", "description": "Tổng số chuyến bay theo lịch trình"},
        {"name": "Cancelled Flights", "folder": "01. Volume & Status", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsCancelled] = 1)", "formatString": "#,##0", "description": "Tổng số chuyến bay bị hủy"},
        {"name": "Cancellation Rate", "folder": "01. Volume & Status", "expression": "DIVIDE([Cancelled Flights], [Total Flights])", "formatString": "0.00%", "description": "Tỷ lệ hủy chuyến"},
        {"name": "Cancellation Rate %", "folder": "01. Volume & Status", "expression": "DIVIDE([Cancelled Flights], [Total Flights])", "formatString": "0.00%", "description": "Tỷ lệ hủy chuyến (%)"},
        {"name": "Non-Cancelled Flights", "folder": "01. Volume & Status", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsCancelled] = 0)", "formatString": "#,##0", "description": "Số chuyến bay không bị hủy"},
        {"name": "Non-Cancelled Rate", "folder": "01. Volume & Status", "expression": "DIVIDE([Non-Cancelled Flights], [Total Flights])", "formatString": "0.00%", "description": "Tỷ lệ chuyến không bị hủy"},
        {"name": "Completion Factor %", "folder": "01. Volume & Status", "expression": "DIVIDE([Non-Cancelled Flights], [Total Flights])", "formatString": "0.00%", "description": "Tỷ lệ hoàn thành không bị hủy (Completion Factor %)"},
        {"name": "Diverted Flights", "folder": "01. Volume & Status", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsCancelled] = 0, 'Fact_Flight'[IsDiverted] = 1)", "formatString": "#,##0", "description": "Số chuyến bay chuyển hướng"},
        {"name": "Diversion Rate", "folder": "01. Volume & Status", "expression": "DIVIDE([Diverted Flights], [Non-Cancelled Flights])", "formatString": "0.00%", "description": "Tỷ lệ chuyển hướng"},
        {"name": "Diversion Rate %", "folder": "01. Volume & Status", "expression": "DIVIDE([Diverted Flights], [Non-Cancelled Flights])", "formatString": "0.00%", "description": "Tỷ lệ chuyển hướng (%)"},
        {"name": "Completed Flights", "folder": "01. Volume & Status", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsCompletedToDestination] = 1)", "formatString": "#,##0", "description": "Số chuyến hoàn thành tới sân bay đích dự kiến"},
        {"name": "Completion-to-Destination Rate", "folder": "01. Volume & Status", "expression": "DIVIDE([Completed Flights], [Total Flights])", "formatString": "0.00%", "description": "Tỷ lệ hoàn thành tới sân bay đích dự kiến"},
        {"name": "Operated Flights", "folder": "01. Volume & Status", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsCancelled] = 0, 'Fact_Flight'[IsDiverted] = 0)", "formatString": "#,##0", "description": "Số chuyến bay hoàn thành khai thác"},
        {"name": "Unknown Outcome Flights", "folder": "01. Volume & Status", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[FlightOutcome] = \"Unknown\")", "formatString": "#,##0", "description": "Số chuyến bay thiếu dữ liệu trạng thái cuối"},
        {"name": "Departure Eligible Flights", "folder": "02. On-Time Performance (OTP)", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsDepOTPEligible] = 1)", "formatString": "#,##0", "description": "Mẫu số hợp lệ tính Departure OTP"},
        {"name": "Departure Delay 15+ Flights", "folder": "02. On-Time Performance (OTP)", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsDepOTPEligible] = 1, 'Fact_Flight'[IsDepDelay15] = 1)", "formatString": "#,##0", "description": "Số chuyến chậm khởi hành >= 15 phút"},
        {"name": "Departure Delay 15+ Rate", "folder": "02. On-Time Performance (OTP)", "expression": "DIVIDE([Departure Delay 15+ Flights], [Departure Eligible Flights])", "formatString": "0.00%", "description": "Tỷ lệ chậm khởi hành >= 15 phút"},
        {"name": "DepDel15 Rate %", "folder": "02. On-Time Performance (OTP)", "expression": "DIVIDE([Departure Delay 15+ Flights], [Departure Eligible Flights])", "formatString": "0.00%", "description": "Tỷ lệ chuyến bay trễ khởi hành >= 15 phút"},
        {"name": "Departure OTP", "folder": "02. On-Time Performance (OTP)", "expression": "IF(ISBLANK([Departure Eligible Flights]), BLANK(), 1 - [Departure Delay 15+ Rate])", "formatString": "0.00%", "description": "Tỷ lệ khởi hành đúng giờ"},
        {"name": "Arrival Eligible Flights", "folder": "02. On-Time Performance (OTP)", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsArrOTPEligible] = 1)", "formatString": "#,##0", "description": "Mẫu số hợp lệ tính Arrival OTP"},
        {"name": "Arrival Delay 15+ Flights", "folder": "02. On-Time Performance (OTP)", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsArrOTPEligible] = 1, 'Fact_Flight'[IsArrDelay15] = 1)", "formatString": "#,##0", "description": "Số chuyến chậm đến >= 15 phút"},
        {"name": "Arrival Delay 15+ Rate", "folder": "02. On-Time Performance (OTP)", "expression": "DIVIDE([Arrival Delay 15+ Flights], [Arrival Eligible Flights])", "formatString": "0.00%", "description": "Tỷ lệ chậm hạ cánh >= 15 phút"},
        {"name": "ArrDel15 Rate %", "folder": "02. On-Time Performance (OTP)", "expression": "DIVIDE([Arrival Delay 15+ Flights], [Arrival Eligible Flights])", "formatString": "0.00%", "description": "Tỷ lệ chuyến bay trễ hạ cánh >= 15 phút"},
        {"name": "Arrival OTP", "folder": "02. On-Time Performance (OTP)", "expression": "IF(ISBLANK([Arrival Eligible Flights]), BLANK(), 1 - [Arrival Delay 15+ Rate])", "formatString": "0.00%", "description": "Tỷ lệ hạ cánh đúng giờ"},
        {"name": "OTP %", "folder": "02. On-Time Performance (OTP)", "expression": "IF(ISBLANK([Arrival Eligible Flights]), BLANK(), 1 - [Arrival Delay 15+ Rate])", "formatString": "0.00%", "description": "Tỷ lệ bay đúng giờ chuẩn FAA/BTS (<15p)"},
        {"name": "Total Departure Delay Minutes", "folder": "03. Delay Analysis & Severity", "expression": "SUM('Fact_Flight'[DepDelayMinutes])", "formatString": "#,##0", "description": "Tổng số phút chậm khởi hành"},
        {"name": "Total Arrival Delay Minutes", "folder": "03. Delay Analysis & Severity", "expression": "SUM('Fact_Flight'[ArrDelayMinutes])", "formatString": "#,##0", "description": "Tổng số phút chậm hạ cánh"},
        {"name": "Avg Departure Delay", "folder": "03. Delay Analysis & Severity", "expression": "AVERAGE('Fact_Flight'[DepDelayMinutes])", "formatString": "0.0", "description": "Số phút chậm khởi hành trung bình"},
        {"name": "Avg Arrival Delay", "folder": "03. Delay Analysis & Severity", "expression": "AVERAGE('Fact_Flight'[ArrDelayMinutes])", "formatString": "0.0", "description": "Số phút chậm đến trung bình"},
        {"name": "Median Arrival Delay", "folder": "03. Delay Analysis & Severity", "expression": "MEDIAN('Fact_Flight'[ArrDelayMinutes])", "formatString": "0.0", "description": "Trung vị số phút chậm hạ cánh"},
        {"name": "P90 Arrival Delay", "folder": "03. Delay Analysis & Severity", "expression": "PERCENTILE.INC('Fact_Flight'[ArrDelayMinutes], 0.90)", "formatString": "0.0", "description": "Phân vị P90 số phút chậm đến"},
        {"name": "P95 Arrival Delay", "folder": "03. Delay Analysis & Severity", "expression": "PERCENTILE.INC('Fact_Flight'[ArrDelayMinutes], 0.95)", "formatString": "0.0", "description": "Phân vị P95 số phút chậm đến"},
        {"name": "Severe Delay Flights", "folder": "03. Delay Analysis & Severity", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsSevereDelay] = 1)", "formatString": "#,##0", "description": "Số chuyến trễ nặng (>60 phút)"},
        {"name": "Severe Delay Rate", "folder": "03. Delay Analysis & Severity", "expression": "DIVIDE([Severe Delay Flights], [Arrival Eligible Flights])", "formatString": "0.00%", "description": "Tỷ lệ chuyến bay trễ nặng (>60 phút)"},
        {"name": "Severe Delay Rate (>60p)", "folder": "03. Delay Analysis & Severity", "expression": "DIVIDE([Severe Delay Flights], [Arrival Eligible Flights])", "formatString": "0.00%", "description": "Tỷ lệ chuyến bay trễ sâu trên 60 phút"},
        {"name": "Extreme Delay Flights", "folder": "03. Delay Analysis & Severity", "expression": "CALCULATE([Total Flights], 'Fact_Flight'[IsExtremeDelay] = 1)", "formatString": "#,##0", "description": "Số chuyến trễ rất nặng (>120 phút)"},
        {"name": "Extreme Delay Rate", "folder": "03. Delay Analysis & Severity", "expression": "DIVIDE([Extreme Delay Flights], [Arrival Eligible Flights])", "formatString": "0.00%", "description": "Tỷ lệ chuyến bay trễ rất nặng (>120 phút)"},
        {"name": "Total Delay Minutes", "folder": "04. Delay Causes", "expression": "SUM('Fact_Flight'[CarrierDelay]) + SUM('Fact_Flight'[WeatherDelay]) + SUM('Fact_Flight'[NASDelay]) + SUM('Fact_Flight'[SecurityDelay]) + SUM('Fact_Flight'[LateAircraftDelay])", "formatString": "#,##0", "description": "Tổng số phút chậm trễ của 5 nguyên nhân"},
        {"name": "Carrier Delay Minutes", "folder": "04. Delay Causes", "expression": "SUM('Fact_Flight'[CarrierDelay])", "formatString": "#,##0", "description": "Tổng phút chậm do hãng hàng không"},
        {"name": "Weather Delay Minutes", "folder": "04. Delay Causes", "expression": "SUM('Fact_Flight'[WeatherDelay])", "formatString": "#,##0", "description": "Tổng phút chậm do thời tiết"},
        {"name": "NAS Delay Minutes", "folder": "04. Delay Causes", "expression": "SUM('Fact_Flight'[NASDelay])", "formatString": "#,##0", "description": "Tổng phút chậm do hệ thống không lưu NAS"},
        {"name": "Security Delay Minutes", "folder": "04. Delay Causes", "expression": "SUM('Fact_Flight'[SecurityDelay])", "formatString": "#,##0", "description": "Tổng phút chậm do an ninh"},
        {"name": "Late Aircraft Delay Minutes", "folder": "04. Delay Causes", "expression": "SUM('Fact_Flight'[LateAircraftDelay])", "formatString": "#,##0", "description": "Tổng phút chậm dây chuyền do tàu bay đến muộn"},
        {"name": "Avg Late Aircraft Delay", "folder": "04. Delay Causes", "expression": "AVERAGE('Fact_Flight'[LateAircraftDelay])", "formatString": "0.0", "description": "Phút trễ dây chuyền trung bình mỗi chuyến có trễ"},
        {"name": "Carrier Delay %", "folder": "04. Delay Causes", "expression": "DIVIDE(SUM('Fact_Flight'[CarrierDelay]), [Total Delay Minutes])", "formatString": "0.00%", "description": "Tỷ trọng trễ do hãng (%)"},
        {"name": "Weather Delay %", "folder": "04. Delay Causes", "expression": "DIVIDE(SUM('Fact_Flight'[WeatherDelay]), [Total Delay Minutes])", "formatString": "0.00%", "description": "Tỷ trọng trễ do thời tiết (%)"},
        {"name": "NAS Delay %", "folder": "04. Delay Causes", "expression": "DIVIDE(SUM('Fact_Flight'[NASDelay]), [Total Delay Minutes])", "formatString": "0.00%", "description": "Tỷ trọng trễ do không lưu NAS (%)"},
        {"name": "Security Delay %", "folder": "04. Delay Causes", "expression": "DIVIDE(SUM('Fact_Flight'[SecurityDelay]), [Total Delay Minutes])", "formatString": "0.00%", "description": "Tỷ trọng trễ do an ninh (%)"},
        {"name": "Late Aircraft Delay %", "folder": "04. Delay Causes", "expression": "DIVIDE(SUM('Fact_Flight'[LateAircraftDelay]), [Total Delay Minutes])", "formatString": "0.00%", "description": "Tỷ trọng trễ dây chuyền (%)"},
        {"name": "Top Delay Cause (%)", "folder": "04. Delay Causes", "expression": "MAXX({[Carrier Delay %], [Weather Delay %], [NAS Delay %], [Security Delay %], [Late Aircraft Delay %]}, [Value])", "formatString": "0.00%", "description": "Tỷ trọng của nguyên nhân gây trễ lớn nhất"},
        {"name": "Total Cause Minutes (Unpivoted)", "folder": "04. Delay Causes", "expression": "SUM('Fact_DelayCause'[CauseMinutes])", "formatString": "#,##0", "description": "Tổng số phút của 5 nguyên nhân chậm chuyến (bảng Fact_DelayCause)"},
        {"name": "Delay Cause Share", "folder": "04. Delay Causes", "expression": "DIVIDE(SUM('Fact_DelayCause'[CauseMinutes]), CALCULATE(SUM('Fact_DelayCause'[CauseMinutes]), ALL('Fact_DelayCause'[CauseName])))", "formatString": "0.00%", "description": "Tỷ trọng đóng góp từng nguyên nhân trễ"},
        {"name": "Avg Taxi-Out", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[TaxiOut])", "formatString": "0.0", "description": "Thời gian lăn bánh khởi hành trung bình"},
        {"name": "Avg Taxi-Out (p)", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[TaxiOut])", "formatString": "0.0", "description": "Thời gian lăn bánh ra đường băng trung bình (phút)"},
        {"name": "Avg Taxi-In", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[TaxiIn])", "formatString": "0.0", "description": "Thời gian lăn bánh sau hạ cánh trung bình"},
        {"name": "Avg Taxi-In (p)", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[TaxiIn])", "formatString": "0.0", "description": "Thời gian lăn bánh vào cổng đỗ trung bình (phút)"},
        {"name": "Avg Ground Time", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[GroundTime])", "formatString": "0.0", "description": "Tổng thời gian mặt đất trung bình"},
        {"name": "Total Ground Time (p)", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[TaxiOut]) + AVERAGE('Fact_Flight'[TaxiIn])", "formatString": "0.0", "description": "Tổng thời gian mặt đất trung bình (phút)"},
        {"name": "Avg AirTime", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[AirTime])", "formatString": "0.0", "description": "Thời gian bay trên không trung bình (phút)"},
        {"name": "Avg Scheduled Elapsed", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[CRSElapsedTime])", "formatString": "0.0", "description": "Tổng thời gian hành trình theo lịch trung bình"},
        {"name": "Avg Actual Elapsed", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[ActualElapsedTime])", "formatString": "0.0", "description": "Tổng thời gian hành trình thực tế trung bình"},
        {"name": "Block Time Variance", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[BlockTimeVariance])", "formatString": "+0.0;-0.0;0.0", "description": "Độ lệch thời gian thực tế so với lịch trình"},
        {"name": "Block Time Variance (p)", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[BlockTimeVariance])", "formatString": "+0.0;-0.0;0.0", "description": "Chênh lệch thời gian bay thực tế so với kế hoạch (phút)"},
        {"name": "Total Distance", "folder": "05. Operational Efficiency", "expression": "SUM('Fact_Flight'[Distance])", "formatString": "#,##0", "description": "Tổng cự ly khai thác (Miles)"},
        {"name": "Avg Distance", "folder": "05. Operational Efficiency", "expression": "AVERAGE('Fact_Flight'[Distance])", "formatString": "#,##0.0", "description": "Cự ly chuyến bay trung bình (Miles)"},
        {"name": "Avg Air Speed", "folder": "05. Operational Efficiency", "expression": "DIVIDE(SUM('Fact_Flight'[Distance]), DIVIDE(SUM('Fact_Flight'[AirTime]), 60))", "formatString": "#,##0.0", "description": "Tốc độ bay trung bình (MPH)"},
        {"name": "Avg Flight Speed (mph)", "folder": "05. Operational Efficiency", "expression": "DIVIDE(SUM('Fact_Flight'[Distance]), DIVIDE(SUM('Fact_Flight'[AirTime]), 60))", "formatString": "#,##0.0", "description": "Tốc độ bay trung bình trên không (mph)"},
    ]


def _resolve_aviation_field(raw_text: str) -> Tuple[str, str]:
    """Map any aviation attribute/table reference from Requirement.md to (StarSchemaTable, ColumnName)."""
    s = raw_text.strip().strip("`'\"")
    low = s.lower()

    # Check if bracket notation like Dim_Date[FlightDate] or Dim_Airport[OriginState]
    m_br = re.search(r"([A-Za-z0-9_]+)\[([A-Za-z0-9_]+)\]", s)
    if m_br:
        col_part = m_br.group(2).lower()
    else:
        col_part = low

    if any(k in col_part for k in ["flightdate", "date", "year"]) and "month" not in col_part and "day" not in col_part:
        return ("Dim_Date", "Date")
    if "month" in col_part:
        return ("Dim_Date", "MonthName")
    if "quarter" in col_part:
        return ("Dim_Date", "QuarterLabel")
    if "dayofweek" in col_part or "dayname" in col_part or col_part == "day":
        return ("Dim_Date", "DayName")
    if "airline" in col_part:
        return ("Dim_Airline", "Reporting_Airline")
    if "originstate" in col_part:
        return ("Dim_OriginAirport", "State")
    if "deststate" in col_part:
        return ("Dim_DestinationAirport", "State")
    if "origincity" in col_part:
        return ("Dim_OriginAirport", "CityName")
    if "destcity" in col_part:
        return ("Dim_DestinationAirport", "CityName")
    if "airporttier" in col_part or "airportgroup" in col_part or "abc" in col_part:
        return ("Dim_OriginAirport", "AirportGroup")
    if col_part in ("origin", "origin airport", "originairport"):
        return ("Dim_OriginAirport", "AirportCode")
    if col_part in ("dest", "destination", "dest airport", "destairport"):
        return ("Dim_DestinationAirport", "AirportCode")
    if "distance" in col_part:
        return ("Dim_Route", "DistanceBand")
    if "route" in col_part:
        return ("Dim_Route", "RouteLabel")
    if "timeslot" in col_part or "timeblock" in col_part or "deptimeblock" in col_part:
        return ("Dim_TimeBlock", "DepTimeBlock")
    if "dephour" in col_part or "departure hour" in col_part or "hour" in col_part:
        return ("Dim_TimeBlock", "DepHour")
    if "delayseverity" in col_part or "arrdelayband" in col_part or "severity" in col_part:
        return ("Fact_Flight", "ArrDelayBand")
    if "cancelreason" in col_part or "cancellationcode" in col_part or "reason code" in col_part:
        return ("Fact_Flight", "CancellationReasonLabel")
    if "flightoutcome" in col_part or "outcome" in col_part:
        return ("Fact_Flight", "FlightOutcome")
    if "5 nhóm nguyên nhân" in low or "root cause" in low or "cause" in col_part:
        return ("Fact_DelayCause", "CauseName")
    if "flight_number" in col_part:
        return ("Fact_Flight", "Flight_Number_Reporting_Airline")
    return ("Dim_Airline", "Reporting_Airline")


def _resolve_universal_field(
    raw_text: str,
    dimensions_cfg: List[Dict[str, Any]],
    date_col: Optional[str],
    fact_table: str,
    all_csv_cols: List[str],
    is_aviation: bool,
) -> Tuple[str, str]:
    if is_aviation:
        return _resolve_aviation_field(raw_text)

    s = raw_text.strip().strip("`'\"")
    m_br = re.search(r"([A-Za-z0-9_]+)\[([A-Za-z0-9_]+)\]", s)
    cl = m_br.group(2).lower() if m_br else s.lower()

    if date_col and cl in (date_col.lower(), "date", "month", "monthname", "year", "quarter", "dayname", "dayofweek"):
        if "month" in cl:
            return ("Dim_Date", "MonthName")
        if "quarter" in cl:
            return ("Dim_Date", "QuarterLabel")
        if "year" in cl:
            return ("Dim_Date", "Year")
        if "day" in cl:
            return ("Dim_Date", "DayName")
        return ("Dim_Date", "Date")

    for dcfg in dimensions_cfg:
        if cl == dcfg["source_column"].lower() or cl == dcfg["table_name"].lower().replace("dim_", ""):
            return (dcfg["table_name"], dcfg["label_column"])

    for c in all_csv_cols:
        if c.lower() == cl:
            return (fact_table, c)

    for dcfg in dimensions_cfg:
        if cl in dcfg["source_column"].lower() or dcfg["source_column"].lower() in cl:
            return (dcfg["table_name"], dcfg["label_column"])

    if dimensions_cfg:
        return (dimensions_cfg[0]["table_name"], dimensions_cfg[0]["label_column"])
    return (fact_table, all_csv_cols[0] if all_csv_cols else "RecordKey")


def _resolve_measure_name(raw_name: str, dax_measures: List[Dict[str, Any]]) -> str:
    """Match a measure name mentioned in Requirement.md to an existing DAX measure in the model."""
    clean = re.sub(r"\$.*?\$", "", raw_name)  # strip inline LaTeX like ($>60$p)
    clean = re.sub(r"\(.*?\)", "", clean).strip().strip("`'\"* ")
    rl_exact = raw_name.strip().strip("`'\"* ").replace("$>60$p", ">60p").lower()
    rl_clean = clean.lower()

    for m in dax_measures:
        if m["name"].lower() == rl_exact or m["name"].lower() == rl_clean:
            return m["name"]

    # Common aliases in aviation requirements
    alias_map = {
        "scheduled flights": "Total Flights",
        "number of flights": "Total Flights",
        "flight count": "Total Flights",
        "route flight count": "Total Flights",
        "sum of cause minutes": "Total Cause Minutes (Unpivoted)",
        "cause minutes": "Total Cause Minutes (Unpivoted)",
        "% đóng góp của 5 nhóm nguyên nhân trễ": "Total Cause Minutes (Unpivoted)",
        "lateaircraftdelay minutes": "Late Aircraft Delay Minutes",
        "average taxi time": "Avg Taxi-Out",
        "avg(actualelapsedtime - crselapsedtime)": "Block Time Variance",
        "p90 delay": "P90 Arrival Delay",
    }
    if rl_clean in alias_map:
        target = alias_map[rl_clean]
        for m in dax_measures:
            if m["name"].lower() == target.lower():
                return m["name"]

    for m in dax_measures:
        if rl_clean and (rl_clean in m["name"].lower() or m["name"].lower() in rl_clean):
            return m["name"]

    return dax_measures[0]["name"] if dax_measures else "Total Flights"


def _compute_grid_slots(n_charts: int) -> List[Tuple[int, int, int, int]]:
    """Compute optimal 16:9 canvas coordinates (x, y, w, h) for n_charts on a 1280x720 page."""
    if n_charts <= 1:
        return [(16, 212, 1248, 492)]
    if n_charts == 2:
        return [(16, 212, 618, 492), (646, 212, 618, 492)]
    if n_charts == 3:
        return [(16, 212, 410, 492), (436, 212, 410, 492), (856, 212, 408, 492)]
    if n_charts == 4:
        return [
            (16, 212, 618, 240),
            (646, 212, 618, 240),
            (16, 462, 618, 242),
            (646, 462, 618, 242),
        ]
    if n_charts == 5:
        return [
            (16, 212, 410, 240),
            (436, 212, 410, 240),
            (856, 212, 408, 240),
            (16, 462, 618, 242),
            (646, 462, 618, 242),
        ]
    if n_charts == 6:
        return [
            (16, 212, 410, 240),
            (436, 212, 410, 240),
            (856, 212, 408, 240),
            (16, 462, 410, 242),
            (436, 462, 410, 242),
            (856, 462, 408, 242),
        ]
    if n_charts == 7:
        return [
            (16, 212, 304, 240),
            (330, 212, 304, 240),
            (644, 212, 304, 240),
            (958, 212, 306, 240),
            (16, 462, 410, 242),
            (436, 462, 410, 242),
            (856, 462, 408, 242),
        ]
    # 8 or more charts: 4x2 grid
    return [
        (16, 212, 304, 240),
        (330, 212, 304, 240),
        (644, 212, 304, 240),
        (958, 212, 306, 240),
        (16, 462, 304, 242),
        (330, 462, 304, 242),
        (644, 462, 304, 242),
        (958, 462, 306, 242),
    ]


def _extract_prop(body: str, keys: List[str]) -> Optional[str]:
    """Extract property value from Markdown bullet or line (supports `- **Key:** Value` and `Key: Value`)."""
    for k in keys:
        pat = re.compile(rf"^\s*(?:[-*]\s*)?(?:\*\*)?{re.escape(k)}(?:\*\*)?\s*:(?:\*\*)?\s*(.+)$", re.MULTILINE | re.IGNORECASE)
        m = pat.search(body)
        if m:
            val = m.group(1).strip()
            # Clean trailing parenthetical explanation if after backtick
            return val
    return None


def _parse_explicit_dashboards_from_md(
    md_text: str,
    dimensions_cfg: List[Dict[str, Any]],
    date_col: Optional[str],
    dax_measures: List[Dict[str, Any]],
    fact_table: str,
    all_csv_cols: List[str],
    is_aviation: bool,
) -> List[Dict[str, Any]]:
    """
    Parse all `# DASHBOARD ...` or `## DASHBOARD ...` sections from Requirement.md!
    Handles both 3-hash (`### EX01-01`) and 4-hash (`#### EX01-01`) chart headers,
    bold bullets (`- **Loại:**`), and `Table[Column]` references.
    """
    dash_pattern = re.compile(r"^#{1,2}\s+DASHBOARD\s*\d*\s*[:–-]\s*(.+)$", re.MULTILINE | re.IGNORECASE)
    matches = list(dash_pattern.finditer(md_text))
    if not matches:
        return []

    parsed_dashboards = []
    for idx, m in enumerate(matches):
        header_text = m.group(1).strip()
        start_pos = m.end()
        end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(md_text)
        section_text = md_text[start_pos:end_pos]
        # Stop at next top-level `# ` section if not another DASHBOARD
        next_h1 = re.search(r"^#\s+(?!DASHBOARD)(.+)$", section_text, re.MULTILINE)
        if next_h1:
            section_text = section_text[:next_h1.start()]

        id_parts = re.split(r"\s+[–-]\s+", header_text, maxsplit=1)
        dash_id = id_parts[0].strip() if len(id_parts) > 1 else f"DB-0{idx+1}"
        dash_title_short = id_parts[1].strip() if len(id_parts) > 1 else header_text
        dash_tab_name = f"{dash_id} {dash_title_short}"[:30]

        # 1. Parse Slicers table
        slicers = []
        sec_tables = _parse_markdown_tables(section_text)
        for tbl in sec_tables:
            k_low = {k.lower(): k for k in tbl[0].keys()}
            if "slicer" in k_low and any(w in k_low for w in ["thuộc tính", "column", "trường", "field"]):
                col_k = next(k_low[w] for w in ["thuộc tính", "column", "trường", "field"] if w in k_low)
                mode_k = next((k_low[w] for w in ["kiểu", "mode", "type"] if w in k_low), None)
                for s_idx, r in enumerate(tbl[:6]):
                    s_title = r[k_low["slicer"]].strip().strip("*`")
                    s_col_raw = r[col_k].strip()
                    stbl, scol = _resolve_universal_field(s_col_raw, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                    raw_mode = r.get(mode_k, "Dropdown").strip() if mode_k else ""
                    smode = "Between" if ("between" in raw_mode.lower() or (stbl == "Dim_Date" and scol == "Date")) else "Dropdown"
                    slicers.append({
                        "id": f"S_{dash_id.replace('-','')}_{s_idx+1}",
                        "title": s_title,
                        "table": stbl,
                        "column": scol,
                        "mode": smode,
                        "sync_group": f"Sync_{stbl}_{scol}",
                    })
                break

        if not slicers:
            if date_col or is_aviation:
                slicers.append({"id": f"S_{idx}_DATE", "title": "Date Range", "table": "Dim_Date", "column": "Date", "mode": "Between", "sync_group": "Sync_Dim_Date_Date"})
            for d_i, dcfg in enumerate(dimensions_cfg[:4]):
                slicers.append({
                    "id": f"S_{idx}_{d_i}",
                    "title": dcfg["source_column"],
                    "table": dcfg["table_name"],
                    "column": dcfg["label_column"],
                    "mode": "Dropdown",
                    "sync_group": f"Sync_{dcfg['table_name']}_{dcfg['label_column']}",
                })

        # 2. Parse KPI Cards (from table or numbered list under `## KPI Cards` / `### KPI Cards`)
        kpis = []
        kpi_sec_match = re.search(r"^#{2,3}\s+[\d.]*\s*KPI\s*Cards?[^\n]*\n(.*?)(?=\n#{2,3}\s+|\Z)", section_text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        if kpi_sec_match:
            kpi_block = kpi_sec_match.group(1)
            kpi_tbls = _parse_markdown_tables(kpi_block)
            if kpi_tbls:
                k_low = {k.lower(): k for k in kpi_tbls[0][0].keys()}
                k_col = k_low.get("kpi", list(kpi_tbls[0][0].keys())[0])
                for k_i, r in enumerate(kpi_tbls[0][:6]):
                    raw_k = r[k_col].strip().strip("*`")
                    clean_title = re.sub(r"\$(.*?)\$", r"\1", raw_k)
                    m_resolved = _resolve_measure_name(raw_k, dax_measures)
                    kpis.append({"id": f"KPI_{dash_id.replace('-','')}_{k_i+1}", "title": clean_title, "measure": m_resolved, "tooltip_measures": []})
            else:
                num_items = re.findall(r"^\s*\d+\.\s*(.+?)\.?\s*$", kpi_block, re.MULTILINE)
                for k_i, raw_k in enumerate(num_items[:6]):
                    clean_title = re.sub(r"\$(.*?)\$", r"\1", raw_k.strip())
                    m_resolved = _resolve_measure_name(raw_k, dax_measures)
                    kpis.append({"id": f"KPI_{dash_id.replace('-','')}_{k_i+1}", "title": clean_title, "measure": m_resolved, "tooltip_measures": []})

        if not kpis:
            for k_i, m_obj in enumerate(dax_measures[:6]):
                kpis.append({"id": f"KPI_{dash_id.replace('-','')}_{k_i+1}", "title": m_obj["name"], "measure": m_obj["name"], "tooltip_measures": []})

        # 3. Parse Charts (`### EX01-01 – ...` OR `#### EX01-01 – ...`)
        chart_pattern = re.compile(r"^#{3,4}\s+([A-Z]{2,4}\d{2}-\d{2}\s+[–-]\s+.+)$", re.MULTILINE)
        chart_matches = list(chart_pattern.finditer(section_text))
        if not chart_matches:
            # Fallback to any ### or #### under Danh sách biểu đồ
            charts_sec = re.search(r"^#{2,3}\s+[\d.]*\s*Danh sách biểu đồ[^\n]*\n(.*?)(?=\n#{1,2}\s+|\Z)", section_text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
            if charts_sec:
                chart_matches = list(re.finditer(r"^#{3,4}\s+(.+)$", charts_sec.group(1), re.MULTILINE))
                c_text_base = charts_sec.group(1)
            else:
                c_text_base = section_text
        else:
            c_text_base = section_text

        n_charts = min(len(chart_matches), 8)
        slots = _compute_grid_slots(n_charts)
        visuals = []

        for c_i, cm in enumerate(chart_matches[:8]):
            c_header = cm.group(1).strip()
            c_start = cm.end()
            c_end = chart_matches[c_i + 1].start() if c_i + 1 < len(chart_matches) else len(c_text_base)
            c_body = c_text_base[c_start:c_end]

            c_parts = re.split(r"\s+[–-]\s+", c_header, maxsplit=1)
            c_id = c_parts[0].strip() if len(c_parts) > 1 else f"{dash_id.replace('-','')}-0{c_i+1}"
            c_title = f"{c_id}: {c_parts[1].strip()}" if len(c_parts) > 1 else c_header

            raw_type = _extract_prop(c_body, ["Loại", "Type"]) or "Bar Chart"
            pbi_vtype = map_chart_type(raw_type)

            raw_x = _extract_prop(c_body, ["X-axis", "Axis", "Category", "Location"])
            raw_y = _extract_prop(c_body, ["Y-axis", "Value", "Values", "Bubble Size"])
            raw_col_y = _extract_prop(c_body, ["Column Y-axis", "Column"])
            raw_line_y = _extract_prop(c_body, ["Line Y-axis", "Line"])
            raw_legend = _extract_prop(c_body, ["Legend", "Series"])
            raw_rows = _extract_prop(c_body, ["Rows"])
            raw_cols = _extract_prop(c_body, ["Columns"])
            raw_details = _extract_prop(c_body, ["Details"])
            raw_size = _extract_prop(c_body, ["Size", "Bubble Size"])
            raw_breakdown = _extract_prop(c_body, ["Breakdown"])
            raw_small_mult = _extract_prop(c_body, ["Small multiples", "Small Multiples"])
            raw_play = _extract_prop(c_body, ["Play Axis", "Play"])
            raw_target = _extract_prop(c_body, ["Target", "Goal", "Target Value"])
            raw_explain = _extract_prop(c_body, ["Explain by", "ExplainBy"])
            raw_tooltips = _extract_prop(c_body, ["Tooltip", "Tooltips"])

            slot = slots[c_i]
            vis_fmt: Dict[str, Any] = {
                "title_show": True,
                "legend_show": True,
                "legend_position": "Top",
                "data_labels_show": False,
                "x_axis_show": True,
                "y_axis_show": True,
                "bg_color": "#FFFFFF",
                "border_show": True,
                "border_color": "#CBD5E1",
                "border_radius": 6,
            }
            # Auto-detect Top N filter from chart header/type (e.g. "Top 10" or "Top N Filter = 10")
            top_m = re.search(r"Top\s*(?:N\s*Filter\s*=\s*)?(\d+)", c_header + " " + raw_type, re.IGNORECASE)
            if top_m:
                vis_fmt["top_n"] = int(top_m.group(1))
                vis_fmt["top_n_direction"] = "Top"
                vis_fmt["sort_direction"] = "Descending"
            # Auto-detect Constant/Target Line (e.g. "mục tiêu 80%" or "đường chuẩn 80%")
            const_m = re.search(r"(?:mục tiêu|đường chuẩn|target|constant line)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*(%)?", c_body, re.IGNORECASE)
            if const_m:
                cv = float(const_m.group(1))
                if const_m.group(2) == "%":
                    cv = round(cv / 100.0, 4)
                vis_fmt["constant_line_value"] = cv
                vis_fmt["constant_line_label"] = f"Target ({const_m.group(1)}{const_m.group(2) or ''})"

            vis_obj: Dict[str, Any] = {
                "id": c_id,
                "title": c_title,
                "type": pbi_vtype,
                "x": slot[0], "y": slot[1], "w": slot[2], "h": slot[3],
                "format": vis_fmt,
            }
            if raw_breakdown:
                b_tbl, b_col = _resolve_universal_field(raw_breakdown, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                vis_obj["breakdown"] = {"table": b_tbl, "column": b_col}
            if raw_small_mult:
                sm_tbl, sm_col = _resolve_universal_field(raw_small_mult, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                vis_obj["small_multiples"] = {"table": sm_tbl, "column": sm_col}
            if raw_play:
                pl_tbl, pl_col = _resolve_universal_field(raw_play, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                vis_obj["play_axis"] = {"table": pl_tbl, "column": pl_col}
            if raw_target:
                vis_obj["target_value"] = {"table": fact_table, "measure": _resolve_measure_name(raw_target, dax_measures)}
            if raw_explain:
                exp_list = []
                for etok in raw_explain.split(","):
                    et_tbl, et_col = _resolve_universal_field(etok, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                    exp_list.append({"table": et_tbl, "column": et_col})
                vis_obj["explain_by"] = exp_list
            if raw_tooltips:
                vis_obj["tooltips"] = [_resolve_measure_name(t, dax_measures) for t in raw_tooltips.split(",") if t.strip()]

            if pbi_vtype == "tableEx":
                col_items = []
                if raw_cols:
                    # Comma-separated list of columns/measures
                    for token in raw_cols.split(","):
                        tok = token.strip().strip("`'\"* ")
                        if not tok:
                            continue
                        # Check if token matches a measure
                        m_cand = _resolve_measure_name(tok, dax_measures)
                        if any(m["name"].lower() == tok.replace("$>60$p", ">60p").lower() for m in dax_measures) or any(w in tok.lower() for w in ["%", "total", "avg", "rate", "otp", "delay", "flights", "variance"]):
                            col_items.append({"table": fact_table, "measure": m_cand})
                        else:
                            ctbl, ccol = _resolve_universal_field(tok, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                            col_items.append({"table": ctbl, "column": ccol})
                else:
                    # Bullet list of columns
                    bullet_cols = re.findall(r"^\s*-\s*([A-Za-z0-9_]+)\.?\s*$", c_body, re.MULTILINE)
                    for bc in bullet_cols[:10]:
                        ctbl, ccol = _resolve_universal_field(bc, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                        col_items.append({"table": ctbl, "column": ccol})
                if not col_items:
                    ctbl, ccol = _resolve_universal_field(raw_x or "Airline", dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                    col_items = [
                        {"table": ctbl, "column": ccol},
                        {"table": fact_table, "measure": dax_measures[0]["name"]},
                    ]
                vis_obj["columns"] = col_items

            elif pbi_vtype == "matrix":
                r_tbl, r_col = _resolve_universal_field(raw_rows or raw_x or "Origin", dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                vis_obj["rows"] = [{"table": r_tbl, "column": r_col}]
                if raw_cols and "," not in raw_cols:
                    c_tbl, c_col = _resolve_universal_field(raw_cols, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                    if (c_tbl, c_col) != (r_tbl, r_col):
                        vis_obj["columns"] = [{"table": c_tbl, "column": c_col}]
                v_list = []
                if raw_y:
                    for tok in raw_y.split(","):
                        tok_clean = tok.strip().strip("`'\"* ")
                        if not tok_clean:
                            continue
                        if any(k in tok_clean.lower() for k in ["distancegroup", "distanceband", "airportgroup"]):
                            continue
                        m_res = _resolve_measure_name(tok_clean, dax_measures)
                        if not any(x.get("measure") == m_res for x in v_list):
                            v_list.append({"table": fact_table, "measure": m_res})
                if not v_list:
                    v_list = [{"table": fact_table, "measure": dax_measures[0]["name"]}]
                vis_obj["values"] = v_list[:5]

            elif pbi_vtype == "lineStackedColumnComboChart":
                cat_tbl, cat_col = _resolve_universal_field(raw_x or "Month", dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                m_col = _resolve_measure_name(raw_col_y or raw_y or dax_measures[0]["name"], dax_measures)
                m_line = _resolve_measure_name(raw_line_y or (dax_measures[1]["name"] if len(dax_measures) > 1 else m_col), dax_measures)
                vis_obj["category"] = {"table": cat_tbl, "column": cat_col}
                vis_obj["column_values"] = [{"table": fact_table, "measure": m_col}]
                vis_obj["line_values"] = [{"table": fact_table, "measure": m_line}]

            elif pbi_vtype == "scatterChart":
                det_tbl, det_col = _resolve_universal_field(raw_details or raw_legend or "Airline", dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                m_x = _resolve_measure_name(raw_x or dax_measures[0]["name"], dax_measures)
                m_y = _resolve_measure_name(raw_y or (dax_measures[1]["name"] if len(dax_measures) > 1 else m_x), dax_measures)
                vis_obj["details"] = {"table": det_tbl, "column": det_col}
                vis_obj["x_axis"] = {"table": fact_table, "measure": m_x}
                vis_obj["y_axis"] = {"table": fact_table, "measure": m_y}
                if raw_size:
                    m_sz = _resolve_measure_name(raw_size, dax_measures)
                    vis_obj["size"] = {"table": fact_table, "measure": m_sz}

            else:
                # For Horizontal Bar Chart, user might write Y-axis: Dimension and X-axis: Measure!
                cat_raw = raw_x
                val_raw = raw_y
                if pbi_vtype in ("clusteredBarChart", "hundredPercentStackedBarChart") and raw_y and raw_x:
                    # Check if raw_y looks like a dimension (e.g. Dim_Airline[Reporting_Airline], Origin, Dest)
                    if any(k in raw_y.lower() for k in ["dim_", "airline", "origin", "dest", "state", "route"]):
                        cat_raw = raw_y
                        val_raw = raw_x
                if pbi_vtype == "donutChart" and raw_legend and not raw_x:
                    cat_raw = raw_legend

                cat_tbl, cat_col = _resolve_universal_field(cat_raw or "Airline", dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                vis_obj["category"] = {"table": cat_tbl, "column": cat_col}

                # Check if legend/series is present (and different from category)
                if raw_legend and pbi_vtype != "donutChart":
                    s_tbl, s_col = _resolve_universal_field(raw_legend, dimensions_cfg, date_col, fact_table, all_csv_cols, is_aviation)
                    if (s_tbl, s_col) != (cat_tbl, cat_col):
                        vis_obj["series"] = {"table": s_tbl, "column": s_col}

                # Special case: if category or series is Fact_DelayCause.CauseName, use Total Cause Minutes (Unpivoted)
                uses_unpivoted_cause = (
                    vis_obj["category"]["table"] == "Fact_DelayCause"
                    or (vis_obj.get("series", {}).get("table") == "Fact_DelayCause")
                )
                if uses_unpivoted_cause:
                    vis_obj["values"] = [{"table": "Fact_DelayCause", "measure": "Total Cause Minutes (Unpivoted)"}]
                else:
                    v_measures = []
                    if val_raw:
                        for tok in val_raw.split(","):
                            tok_c = tok.strip()
                            if not tok_c or "% share" in tok_c.lower() or "grand total" in tok_c.lower():
                                continue
                            m_res = _resolve_measure_name(tok_c, dax_measures)
                            if not any(x["measure"] == m_res for x in v_measures):
                                v_measures.append({"table": fact_table, "measure": m_res})
                    if not v_measures:
                        v_measures = [{"table": fact_table, "measure": dax_measures[0]["name"]}]
                    vis_obj["values"] = v_measures[:3]

            visuals.append(vis_obj)

        if visuals:
            parsed_dashboards.append({
                "id": dash_id,
                "name": dash_tab_name,
                "title": f"{dash_id}: {dash_title_short.upper()}",
                "subtitle": f"Biên dịch tự động theo đặc tả {dash_id} ({len(slicers)} Slicers, {len(kpis)} KPI Cards, {len(visuals)} Biểu đồ)",
                "slicers": slicers,
                "kpis": kpis,
                "visuals": visuals,
            })

    return parsed_dashboards


def compile_blueprint_from_csv_and_markdown(
    workspace_dir: str,
    csv_path: str,
    req_md_path: str,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Universal compiler:
    ALWAYS parses the provided `req_md_path` file so that any new or modified Requirement.md
    immediately generates its exact Dashboards, Slicers, KPI Cards, Visuals, and DAX Measures!
    """
    root = Path(workspace_dir)
    c_path = Path(csv_path) if Path(csv_path).is_absolute() else (root / csv_path)
    m_path = Path(req_md_path) if Path(req_md_path).is_absolute() else (root / req_md_path)

    csv_info = inspect_csv_sample(c_path)
    md_text = m_path.read_text(encoding="utf-8") if m_path.exists() else ""
    csv_info = _apply_dictionary_overrides(csv_info, md_text)

    title_match = re.search(r"^##\s+(?:Đề tài:|Project:|Tiêu đề:)\s*(.+)$", md_text, flags=re.MULTILINE | re.IGNORECASE)
    if not title_match:
        title_match = re.search(r"^#\s+(.+)$", md_text, flags=re.MULTILINE)
    doc_title = title_match.group(1).strip() if title_match else c_path.stem.replace("_", " ").title()

    is_aviation = is_us_flight_dataset(csv_info)
    fact_table = "Fact_Flight" if is_aviation else "Fact_Main"
    dataset_mode = "aviation_star_schema" if is_aviation else "universal_star_schema"
    proj_slug = project_name or ("US_Flight_Operations" if is_aviation else re.sub(r"[^A-Za-z0-9_]+", "_", c_path.stem).strip("_"))

    date_col = csv_info["primary_date_col"]
    dim_cols = csv_info["dimension_cols"][:8]
    measure_cols = csv_info["measure_cols"]
    flag_cols = csv_info["flag_cols"]

    dimensions_cfg = []
    for dcol in dim_cols:
        clean_dim = re.sub(r"[^A-Za-z0-9]+", "", dcol)
        dimensions_cfg.append({
            "table_name": f"Dim_{clean_dim}",
            "source_column": dcol,
            "key_column": f"{clean_dim}Key",
            "label_column": dcol,
            "enable_pareto_abc": True,
        })

    # Build DAX Measures: combine base measures + explicit DAX blocks from the user's Requirement.md
    if is_aviation:
        dax_measures = _get_base_aviation_dax_measures()
    else:
        dax_measures = [
            {
                "name": "Total Records",
                "folder": "01. Core Volume",
                "expression": f"COUNTROWS('{fact_table}')",
                "formatString": "#,##0",
                "description": f"Tổng số bản ghi trong bảng {fact_table}",
            }
        ]

    seen_measure_names = {m["name"].lower(): idx for idx, m in enumerate(dax_measures)}

    # Override or add DAX measures extracted directly from the user's Requirement.md
    col_lookup = {c.lower(): c for c in csv_info["columns"]}
    for tm in _extract_kpi_table_measures(md_text, fact_table, col_lookup):
        if tm["name"].lower() not in seen_measure_names:
            seen_measure_names[tm["name"].lower()] = len(dax_measures)
            dax_measures.append(tm)

    for md_m in _extract_dax_code_blocks(md_text, fact_table):
        m_low = md_m["name"].lower()
        if m_low in seen_measure_names:
            dax_measures[seen_measure_names[m_low]]["expression"] = md_m["expression"]
        else:
            seen_measure_names[m_low] = len(dax_measures)
            dax_measures.append(md_m)

    if not is_aviation:
        for mcol in measure_cols[:12]:
            for mn, expr, fmt, desc in [
                (f"Total {mcol}", f"SUM('{fact_table}'[{mcol}])", "#,##0.00", f"Tổng {mcol}"),
                (f"Avg {mcol}", f"AVERAGE('{fact_table}'[{mcol}])", "0.00", f"Trung bình {mcol}"),
                (f"P90 {mcol}", f"PERCENTILE.INC('{fact_table}'[{mcol}], 0.90)", "0.00", f"Phân vị P90 của {mcol}"),
            ]:
                if mn.lower() not in seen_measure_names:
                    seen_measure_names[mn.lower()] = len(dax_measures)
                    dax_measures.append({"name": mn, "folder": "02. Numeric Metrics", "expression": expr, "formatString": fmt, "description": desc})

        for fcol in flag_cols[:8]:
            cnt_name = f"{fcol} Count"
            rate_name = f"{fcol} Rate"
            for mn, expr, fmt, desc in [
                (cnt_name, f"CALCULATE([Total Records], '{fact_table}'[{fcol}] = 1)", "#,##0", f"Số bản ghi có {fcol} = 1"),
                (rate_name, f"DIVIDE([{cnt_name}], [Total Records])", "0.00%", f"Tỷ lệ {fcol} = 1"),
            ]:
                if mn.lower() not in seen_measure_names:
                    seen_measure_names[mn.lower()] = len(dax_measures)
                    dax_measures.append({"name": mn, "folder": "03. Flag & Rate KPIs", "expression": expr, "formatString": fmt, "description": desc})

    # Parse explicit `# DASHBOARD` / `## DASHBOARD` sections from the user's Requirement.md
    explicit_dashboards = _parse_explicit_dashboards_from_md(
        md_text, dimensions_cfg, date_col, dax_measures, fact_table, csv_info["columns"], is_aviation
    )

    if explicit_dashboards:
        dashboards = explicit_dashboards
        # If the user's Requirement.md also mentions Data Quality (like Requirement.md Section 10.3), append DQ page
        if "trang data quality" in md_text.lower() or "data quality page" in md_text.lower():
            dashboards.append({
                "id": "DQ-05",
                "name": "DQ-05 Data Quality",
                "title": "DQ-05: DATA QUALITY & RECONCILIATION – KIỂM TOÁN CHẤT LƯỢNG DỮ LIỆU",
                "subtitle": "Kiểm soát 20 tiêu chí chất lượng dữ liệu, tỷ lệ thiếu giá trị (Missing Rate) và đối soát tổng dòng",
                "slicers": [
                    {"id": "S_DQ_CAT", "title": "Audit Category", "table": "Data_Quality_Stats", "column": "Category", "mode": "Dropdown", "sync_group": ""},
                    {"id": "S_DQ_ST", "title": "Status", "table": "Data_Quality_Stats", "column": "Status", "mode": "Dropdown", "sync_group": ""},
                ],
                "kpis": dashboards[0]["kpis"][:6],
                "visuals": [
                    {
                        "id": "DQ05-01",
                        "title": "DQ05-01: Kết quả kiểm toán 20 tiêu chí Chất lượng dữ liệu",
                        "type": "tableEx",
                        "x": 16, "y": 212, "w": 1248, "h": 492,
                        "columns": [
                            {"table": "Data_Quality_Stats", "column": "CheckID"},
                            {"table": "Data_Quality_Stats", "column": "Category"},
                            {"table": "Data_Quality_Stats", "column": "CheckName"},
                            {"table": "Data_Quality_Stats", "column": "RecordCount"},
                            {"table": "Data_Quality_Stats", "column": "Percentage"},
                            {"table": "Data_Quality_Stats", "column": "Status"},
                        ],
                    }
                ],
            })
    else:
        dashboards = _compile_default_dashboards(dimensions_cfg, date_col, dax_measures, doc_title, fact_table)

    blueprint = {
        "project": {
            "name": proj_slug,
            "title": doc_title,
            "version": "2.0",
            "platform": "Power BI Desktop",
            "dataset_mode": dataset_mode,
            "source_csv": str(c_path.relative_to(root)) if c_path.is_relative_to(root) else str(c_path),
            "requirement_doc": str(m_path.relative_to(root)) if m_path.is_relative_to(root) else str(m_path),
            "warehouse_dir": "data_warehouse",
            "clean_csv_dir": "data_warehouse/csv",
            "output_pbi_dir": "output_pbi",
            "primary_date_col": date_col,
            "fact_table_name": fact_table,
            "canvas": {"width": 1280, "height": 720, "aspect_ratio": "16:9"},
        },
        "universal_schema": {
            "csv_info": csv_info,
            "dimensions": dimensions_cfg,
        },
        "dax_measures": dax_measures,
        "dashboards": dashboards,
    }
    return blueprint


def _compile_default_dashboards(
    dimensions_cfg: List[Dict[str, Any]],
    date_col: Optional[str],
    dax_measures: List[Dict[str, Any]],
    doc_title: str,
    fact_table: str,
) -> List[Dict[str, Any]]:
    common_slicers = []
    if date_col:
        common_slicers.append({"id": "S_DATE", "title": "Date Range", "table": "Dim_Date", "column": "Date", "mode": "Between", "sync_group": "Sync_Date"})
    for idx, dcfg in enumerate(dimensions_cfg[:5]):
        common_slicers.append({
            "id": f"S_DIM_{idx+1}",
            "title": dcfg["source_column"],
            "table": dcfg["table_name"],
            "column": dcfg["label_column"],
            "mode": "Dropdown",
            "sync_group": f"Sync_{dcfg['source_column']}",
        })

    m_names = [m["name"] for m in dax_measures]
    top_kpis = [{"id": f"KPI_MAIN_{idx+1}", "title": mn, "measure": mn, "tooltip_measures": []} for idx, mn in enumerate(m_names[:6])]
    dim1 = dimensions_cfg[0] if dimensions_cfg else {"table_name": fact_table, "label_column": "RecordKey"}
    dim2 = dimensions_cfg[1] if len(dimensions_cfg) > 1 else dim1
    m1 = m_names[0]
    m2 = m_names[1] if len(m_names) > 1 else m1
    m3 = m_names[2] if len(m_names) > 2 else m1
    grid_slots = _compute_grid_slots(6)

    return [
        {
            "id": "DB-01",
            "name": "01 Executive Overview",
            "title": f"01: EXECUTIVE OVERVIEW – {doc_title.upper()}",
            "subtitle": "Tổng quan quy mô, xu hướng theo thời gian và phân bổ theo các chiều dữ liệu chính",
            "slicers": common_slicers,
            "kpis": top_kpis,
            "visuals": [
                {"id": "DB01-01", "title": f"Xu hướng {m1} theo Thời gian", "type": "lineChart", "x": grid_slots[0][0], "y": grid_slots[0][1], "w": grid_slots[0][2], "h": grid_slots[0][3], "category": {"table": "Dim_Date" if date_col else dim1["table_name"], "column": "Date" if date_col else dim1["label_column"]}, "values": [{"table": fact_table, "measure": m1}]},
                {"id": "DB01-02", "title": f"Cơ cấu {m1} theo {dim1['label_column']}", "type": "donutChart", "x": grid_slots[1][0], "y": grid_slots[1][1], "w": grid_slots[1][2], "h": grid_slots[1][3], "category": {"table": dim1["table_name"], "column": dim1["label_column"]}, "values": [{"table": fact_table, "measure": m1}]},
                {"id": "DB01-03", "title": f"So sánh {m2} theo {dim1['label_column']}", "type": "clusteredBarChart", "x": grid_slots[2][0], "y": grid_slots[2][1], "w": grid_slots[2][2], "h": grid_slots[2][3], "category": {"table": dim1["table_name"], "column": dim1["label_column"]}, "values": [{"table": fact_table, "measure": m2}]},
                {"id": "DB01-04", "title": f"Phân tích {m2} & {m3} theo {dim2['label_column']}", "type": "clusteredColumnChart", "x": grid_slots[3][0], "y": grid_slots[3][1], "w": grid_slots[3][2], "h": grid_slots[3][3], "category": {"table": dim2["table_name"], "column": dim2["label_column"]}, "values": [{"table": fact_table, "measure": m2}, {"table": fact_table, "measure": m3}]},
                {"id": "DB01-05", "title": f"Phân nhóm Pareto ABC theo {dim1['label_column']}", "type": "clusteredBarChart", "x": grid_slots[4][0], "y": grid_slots[4][1], "w": grid_slots[4][2], "h": grid_slots[4][3], "category": {"table": dim1["table_name"], "column": "ParetoGroup"}, "values": [{"table": fact_table, "measure": m1}]},
                {"id": "DB01-06", "title": f"Bảng tổng hợp hiệu suất theo {dim1['label_column']}", "type": "tableEx", "x": grid_slots[5][0], "y": grid_slots[5][1], "w": grid_slots[5][2], "h": grid_slots[5][3], "columns": [{"table": dim1["table_name"], "column": dim1["label_column"]}, {"table": dim1["table_name"], "column": "ParetoGroup"}, {"table": fact_table, "measure": m1}, {"table": fact_table, "measure": m2}]},
            ],
        }
    ]
