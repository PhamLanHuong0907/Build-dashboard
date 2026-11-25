"""Requirement-Driven ETL Data Cleaning Parser & Execution Engine.

Parses structured and natural-language cleaning rules from Requirement.md
(Section II: QUY TẮC LÀM SẠCH DỮ LIỆU) into a normalized list of executable
rules stored in blueprint["cleaning_rules"], then executes them deterministically
during Phase 3 ETL before building the Star Schema Data Warehouse.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


def _parse_md_tables(md_text: str) -> List[List[Dict[str, str]]]:
    tables: List[List[Dict[str, str]]] = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        if "|" in lines[i] and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$", lines[i + 1]):
            headers = [h.strip() for h in lines[i].strip().strip("|").split("|")]
            i += 2
            rows: List[Dict[str, str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                vals = [v.strip() for v in lines[i].strip().strip("|").split("|")]
                if len(vals) < len(headers):
                    vals += [""] * (len(headers) - len(vals))
                rows.append({headers[j]: vals[j] for j in range(len(headers))})
                i += 1
            if rows:
                tables.append(rows)
        else:
            i += 1
    return tables


def _extract_cleaning_section(md_text: str) -> str:
    """Return text under the Cleaning Rules heading (if present), else full doc."""
    pat = re.compile(
        r"^#{1,3}\s+.*?(?:làm sạch|cleaning|chất lượng dữ liệu|data quality|etl).*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pat.search(md_text)
    if not m:
        return md_text
    start = m.start()
    rest = md_text[m.end():]
    nxt = re.search(r"^#\s+", rest, re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(md_text)
    return md_text[start:end]


def _resolve_col(raw: str, col_lookup: Dict[str, str]) -> str:
    cleaned = raw.strip().strip("`*\"'[]")
    return col_lookup.get(cleaned.lower(), cleaned)


def _normalize_action(raw_action: str, raw_target: str, raw_cond: str) -> str:
    a = raw_action.strip().strip("`*").lower()
    t = raw_target.strip().lower()
    c = raw_cond.strip().lower()
    combined = f"{a} {t} {c}"

    if a in (
        "drop_duplicates", "drop_invalid_date", "format_date", "parse_date",
        "clean_numeric", "cast_type", "filter",
        "fillna", "drop_null", "trim", "trim_upper", "trim_lower", "trim_title",
        "drop_outliers", "clip_outliers", "flag_01",
    ):
        return "format_date" if a == "parse_date" else a
    if a in ("to_int", "to_float", "to_string", "to_text", "to_bool", "type", "dtype"):
        return "cast_type"
    if a in ("drop", "dedup", "deduplicate") and ("dup" in t or "trùng" in combined):
        return "drop_duplicates"
    if "trùng" in combined or "duplicate" in combined:
        return "drop_duplicates"
    if re.search(r"\b(dd[/\-.]mm[/\-.]yyyy|mm[/\-.]dd[/\-.]yyyy|yyyy[/\-.]mm[/\-.]dd)\b", combined, re.I):
        return "format_date"
    if ("ngày" in combined or "date" in combined) and any(w in combined for w in ("định dạng", "format", "chuẩn hóa")):
        return "format_date"
    if ("ngày" in combined or "date" in combined) and any(w in combined for w in ("loại", "xóa", "drop", "lỗi", "invalid")):
        return "drop_invalid_date"
    if any(w in combined for w in ("ép kiểu", "cast_type", "kiểu số nguyên", "kiểu chuỗi", "kiểu số thực", "kiểu boolean")):
        return "cast_type"
    if any(w in combined for w in ("clean_numeric", "ký tự", "tiền tệ", "currency", "ép kiểu số")):
        return "clean_numeric"
    if "outlier" in combined or "ngoại lai" in combined:
        return "clip_outliers" if any(w in combined for w in ("clip", "cắt ngưỡng", "giới hạn")) else "drop_outliers"
    if "flag" in a or ("cờ" in t and "{0, 1}" in combined) or "{0,1}" in combined.replace(" ", ""):
        return "flag_01"
    if any(w in combined for w in ("chữ hoa", "upper", "in hoa")):
        return "trim_upper"
    if any(w in combined for w in ("chữ thường", "lower")):
        return "trim_lower"
    if any(w in combined for w in ("title", "viết hoa đầu")):
        return "trim_title"
    if any(w in combined for w in ("khoảng trắng", "trim", "strip")):
        return "trim"
    if any(w in combined for w in ("xóa null", "loại null", "drop_null", "không được trống", "not null")):
        return "drop_null"
    if any(w in combined for w in ("điền", "fillna", "thay null", "thay bằng", "replace null")) and "không thay" not in combined:
        return "fillna"
    if re.search(r"(>=|<=|!=|==|>|<|between\s)", c, re.I):
        return "filter"
    return ""


def parse_cleaning_rules(md_text: str, csv_columns: List[str]) -> List[Dict[str, Any]]:
    """Parse Requirement.md cleaning rules into normalized executable rule dicts."""
    col_lookup = {c.lower(): c for c in csv_columns}
    section = _extract_cleaning_section(md_text)
    rules: List[Dict[str, Any]] = []
    seen = set()

    def _add(target: str, action: str, condition: str, description: str) -> None:
        if not action:
            return
        key = (target.lower(), action, condition.strip().lower())
        if key in seen:
            return
        seen.add(key)
        rules.append({
            "column": target,
            "action": action,
            "condition": condition.strip(),
            "description": description.strip(),
        })

    # 1. Structured Markdown tables in the Cleaning section
    for tbl in _parse_md_tables(section):
        keys = {k.lower(): k for k in tbl[0]}
        col_k = next((keys[k] for k in keys if any(w in k for w in ("quy tắc", "cột", "thuộc tính", "rule", "column", "target"))), None)
        act_k = next((keys[k] for k in keys if any(w in k for w in ("hành động", "action", "xử lý", "cách"))), None)
        cond_k = next((keys[k] for k in keys if any(w in k for w in ("điều kiện", "giá trị", "tham số", "condition", "value", "param"))), None)
        if not col_k or not act_k:
            continue

        for row in tbl:
            raw_target = row.get(col_k, "").strip().strip("`*")
            raw_action = row.get(act_k, "").strip().strip("`*")
            raw_cond = row.get(cond_k, "").strip().strip("`*") if cond_k else ""
            if not raw_target and not raw_action:
                continue

            action = _normalize_action(raw_action, raw_target, raw_cond)
            if not action:
                continue

            if action == "drop_duplicates":
                # Check if condition specifies subset columns matching CSV columns
                subset_cols = [
                    col_lookup[tok.strip().strip("`*").lower()]
                    for tok in re.split(r"[,;+]", raw_cond)
                    if tok.strip().strip("`*").lower() in col_lookup
                ]
                cond = ", ".join(subset_cols) if subset_cols else "ALL"
                _add("ALL", action, cond, f"{raw_target}: {raw_action}")
                continue

            # Resolve target column (must exist in CSV or be ALL / ALL_DIMENSIONS / ALL_MEASURES)
            target_low = raw_target.lower()
            if target_low in col_lookup:
                target = col_lookup[target_low]
            elif any(w in target_low for w in ("all", "toàn bộ", "tất cả")):
                target = "ALL"
            else:
                # Try finding a CSV column name mentioned inside raw_target or raw_action
                matched_col = next((c for c in csv_columns if re.search(rf"\b{re.escape(c)}\b", f"{raw_target} {raw_action}", re.I)), None)
                if not matched_col:
                    continue
                target = matched_col

            # Extract condition if it's embedded in raw_action for 2-column tables
            cond = raw_cond
            if not cond and action == "filter":
                m_op = re.search(r"(>=|<=|!=|==|>|<)\s*([\-+]?\d+(?:\.\d+)?)", f"{raw_action} {raw_target}")
                if m_op:
                    cond = f"{m_op.group(1)} {m_op.group(2)}"
            if not cond and action == "fillna":
                m_val = re.search(r"(?:bằng|with|=)\s*['\"`]?([^'\"`,;]+)['\"`]?", raw_action, re.I)
                if m_val:
                    cond = m_val.group(1).strip()
            if not cond and action == "format_date":
                m_fmt = re.search(r"(dd[/\-.]mm[/\-.]yyyy|mm[/\-.]dd[/\-.]yyyy|yyyy[/\-.]mm[/\-.]dd)", f"{raw_action} {raw_target}", re.I)
                if m_fmt:
                    cond = m_fmt.group(1)
            if not cond and action == "cast_type":
                act_low = raw_action.lower()
                if act_low in ("to_int", "to_float", "to_string", "to_text", "to_bool"):
                    cond = act_low.replace("to_", "")
                else:
                    m_ty = re.search(r"\b(int64|int|integer|float_vn|float|double|decimal|string|text|str|bool|boolean|date)\b", f"{raw_action} {raw_target}", re.I)
                    if m_ty:
                        cond = m_ty.group(1).lower()

            _add(target, action, cond, f"{raw_target} -> {raw_action} {raw_cond}".strip())

    # 2. Inline bullet rules inside Cleaning section (e.g., "- Revenue >= 0", "- Loại bỏ Quantity <= 0")
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith(("-", "*")):
            continue
        body = s.lstrip("-* ").strip()
        m_cmp = re.search(r"\b([A-Za-z0-9_]+)\s*(>=|<=|!=|==|>|<)\s*([\-+]?\d+(?:\.\d+)?)", body)
        if m_cmp and m_cmp.group(1).lower() in col_lookup:
            col = col_lookup[m_cmp.group(1).lower()]
            op, val = m_cmp.group(2), m_cmp.group(3)
            # If sentence says "Loại bỏ / Xóa / Drop" with condition, invert operator to keep valid rows
            if re.search(r"\b(loại|xóa|drop|remove|exclude)\b", body, re.I):
                inv = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "==": "!=", "!=": "=="}
                op = inv.get(op, op)
            _add(col, "filter", f"{op} {val}", body)

    # Always ensure deduplication is present as baseline standard if user didn't specify one
    if not any(r["action"] == "drop_duplicates" for r in rules):
        rules.insert(0, {
            "column": "ALL",
            "action": "drop_duplicates",
            "condition": "ALL",
            "description": "Mặc định: Loại bỏ bản ghi trùng lặp hoàn toàn",
        })

    return rules


def cleaning_rules_hash(rules: List[Dict[str, Any]]) -> str:
    payload = json.dumps(rules or [], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _to_pbi_date_format(fmt: str) -> str:
    """Convert human date pattern (e.g. dd/mm/yyyy) to Power BI formatString (dd/MM/yyyy)."""
    f = (fmt or "").strip().lower()
    if f in ("dd/mm/yyyy", "d/m/yyyy"):
        return "dd/MM/yyyy"
    if f in ("dd-mm-yyyy", "d-m-yyyy"):
        return "dd-MM-yyyy"
    if f in ("dd.mm.yyyy", "d.m.yyyy"):
        return "dd.MM.yyyy"
    if f in ("mm/dd/yyyy", "m/d/yyyy"):
        return "MM/dd/yyyy"
    if f in ("yyyy/mm/dd",):
        return "yyyy/MM/dd"
    if f in ("yyyy-mm-dd",):
        return "yyyy-MM-dd"
    return "yyyy-MM-dd"


def _to_strftime_format(fmt: str) -> str:
    f = (fmt or "").strip().lower()
    mapping = {
        "dd/mm/yyyy": "%d/%m/%Y",
        "d/m/yyyy": "%d/%m/%Y",
        "dd-mm-yyyy": "%d-%m-%Y",
        "d-m-yyyy": "%d-%m-%Y",
        "dd.mm.yyyy": "%d.%m.%Y",
        "mm/dd/yyyy": "%m/%d/%Y",
        "yyyy/mm/dd": "%Y/%m/%d",
        "yyyy-mm-dd": "%Y-%m-%d",
    }
    return mapping.get(f, "%Y-%m-%d")


def extract_date_format_map(rules: List[Dict[str, Any]]) -> Dict[str, str]:
    """Return {col_name_or_DEFAULT: pbi_formatString} from format_date rules."""
    out: Dict[str, str] = {}
    for r in rules or []:
        if r.get("action") == "format_date" and r.get("condition"):
            pbi_fmt = _to_pbi_date_format(r["condition"])
            out[r.get("column", "")] = pbi_fmt
            if "_primary" not in out:
                out["_primary"] = pbi_fmt
                out["_primary_strftime"] = _to_strftime_format(r["condition"])
    return out


def _clean_numeric_series(series: pd.Series, vn_decimal: bool = False) -> Tuple[pd.Series, int]:
    raw_s = series.astype(str)
    s = raw_s.str.strip()
    s = s.str.replace(r"[\$€£₫%\s]", "", regex=True)
    if vn_decimal:
        # Vietnamese/European style: 1.250,50 -> 1250.50
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        # Auto-detect per cell: if matches ^-?\d{1,3}(\.\d{3})+,\d+$ treat as VN/EU decimal
        vn_mask = s.str.match(r"^-?\d{1,3}(?:\.\d{3})+,\d+$", na=False)
        if vn_mask.any():
            s = s.where(~vn_mask, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
        s = s.str.replace(",", "", regex=False)
    s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan, "N/A": np.nan, "null": np.nan, "-": np.nan})
    num = pd.to_numeric(s, errors="coerce")
    fixed = int((raw_s != s.fillna("")).sum())
    return num, fixed


def apply_cleaning_rules(df: pd.DataFrame, rules: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Execute normalized cleaning rules on df and return (clean_df, cleaning_report)."""
    n_source = len(df)
    steps_log: List[Dict[str, Any]] = []
    total_dropped = 0
    total_fixed_cells = 0

    for idx, rule in enumerate(rules or [], start=1):
        col = rule.get("column", "")
        action = rule.get("action", "")
        cond = (rule.get("condition") or "").strip()
        desc = rule.get("description") or f"{col}: {action} {cond}".strip()

        before_rows = len(df)
        affected_rows = 0
        fixed_cells = 0
        status = "APPLIED"
        detail = ""

        try:
            if action == "drop_duplicates":
                subset = [c.strip() for c in cond.split(",") if c.strip() in df.columns] if cond and cond.upper() != "ALL" else None
                dup_mask = df.duplicated(subset=subset, keep="first")
                affected_rows = int(dup_mask.sum())
                if affected_rows > 0:
                    df = df.loc[~dup_mask].reset_index(drop=True)
                detail = f"Loại {affected_rows:,} dòng trùng" + (f" theo ({', '.join(subset)})" if subset else " hoàn toàn")

            elif col not in df.columns:
                status = "SKIPPED"
                detail = f"Không tìm thấy cột '{col}' trong CSV"

            elif action == "drop_invalid_date":
                parsed = pd.to_datetime(df[col], errors="coerce")
                bad = parsed.isna()
                affected_rows = int(bad.sum())
                if affected_rows > 0:
                    df = df.loc[~bad].reset_index(drop=True)
                    parsed = parsed.loc[~bad].reset_index(drop=True)
                df[col] = parsed
                detail = f"Loại {affected_rows:,} dòng có ngày lỗi/trống ở '{col}'"

            elif action == "format_date":
                raw_s = df[col]
                fmt_low = cond.lower()
                dayfirst = fmt_low.startswith("d")
                exact_strf = _to_strftime_format(cond) if cond else None
                parsed = None
                if exact_strf and not pd.api.types.is_datetime64_any_dtype(raw_s):
                    # Try exact pattern first; if any NaT on non-empty values, fall back to mixed dayfirst parser
                    s_clean = raw_s.astype(str).str.strip().replace({"": np.nan, "nan": np.nan, "None": np.nan, "N/A": np.nan})
                    parsed = pd.to_datetime(s_clean, format=exact_strf, errors="coerce")
                    missing_exact = parsed.isna() & s_clean.notna()
                    if missing_exact.any():
                        fallback = pd.to_datetime(s_clean.loc[missing_exact], dayfirst=dayfirst, format="mixed", errors="coerce")
                        parsed.loc[missing_exact] = fallback
                else:
                    parsed = pd.to_datetime(raw_s, dayfirst=dayfirst, errors="coerce")

                keep_null = "keep_null" in fmt_low or "giữ null" in fmt_low
                bad = parsed.isna()
                if not keep_null:
                    affected_rows = int(bad.sum())
                    if affected_rows > 0:
                        df = df.loc[~bad].reset_index(drop=True)
                        parsed = parsed.loc[~bad].reset_index(drop=True)
                df[col] = parsed
                fixed_cells = len(df)
                pbi_fmt = _to_pbi_date_format(cond)
                detail = f"Chuẩn hóa ngày '{col}' theo {pbi_fmt} (dayfirst={dayfirst}) -> loại {affected_rows:,} dòng sai định dạng"

            elif action == "clean_numeric":
                num, fixed_cells = _clean_numeric_series(df[col], vn_decimal=("vn" in cond.lower()))
                df[col] = num
                detail = f"Chuẩn hóa kiểu số cột '{col}' ({fixed_cells:,} ô làm sạch)"

            elif action == "cast_type":
                t_low = cond.lower().strip()
                if t_low in ("int", "int64", "integer", "số nguyên"):
                    num, fixed_cells = _clean_numeric_series(df[col])
                    rounded = num.round()
                    df[col] = rounded.astype("Int64") if rounded.isna().any() else rounded.astype(np.int64)
                    detail = f"Ép kiểu số nguyên (int64) cột '{col}' ({fixed_cells:,} ô chuẩn hóa)"
                elif t_low in ("float", "double", "decimal", "numeric", "số thực", "float_vn"):
                    num, fixed_cells = _clean_numeric_series(df[col], vn_decimal=("vn" in t_low))
                    df[col] = num.astype(np.float64)
                    detail = f"Ép kiểu số thực (float64) cột '{col}' ({fixed_cells:,} ô chuẩn hóa)"
                elif t_low in ("string", "text", "str", "chuỗi"):
                    raw_s = df[col]
                    s_out = raw_s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
                    s_out = s_out.where(raw_s.notna(), np.nan)
                    fixed_cells = int((raw_s.astype(str) != s_out.fillna("nan")).sum())
                    df[col] = s_out
                    detail = f"Ép kiểu chuỗi (string) cột '{col}' ({fixed_cells:,} ô chuẩn hóa)"
                elif t_low in ("bool", "boolean"):
                    raw_s = df[col]
                    mapped = raw_s.astype(str).str.strip().str.lower().map({
                        "1": True, "1.0": True, "true": True, "yes": True, "y": True, "có": True,
                        "0": False, "0.0": False, "false": False, "no": False, "n": False, "không": False,
                    }).fillna(False).astype(bool)
                    fixed_cells = len(df)
                    df[col] = mapped
                    detail = f"Ép kiểu boolean cột '{col}'"
                elif t_low in ("date", "datetime"):
                    parsed = pd.to_datetime(df[col], dayfirst=True, format="mixed", errors="coerce")
                    df[col] = parsed
                    fixed_cells = int(parsed.notna().sum())
                    detail = f"Ép kiểu ngày (datetime) cột '{col}'"
                else:
                    status = "SKIPPED"
                    detail = f"Không hỗ trợ kiểu dữ liệu '{cond}' (dùng: int, float, string, bool, date)"

            elif action == "filter":
                s = pd.to_numeric(df[col], errors="coerce") if not pd.api.types.is_numeric_dtype(df[col]) else df[col]
                m_btw = re.fullmatch(r"between\s+([\-+]?\d+(?:\.\d+)?)\s+(?:and|,|-)\s+([\-+]?\d+(?:\.\d+)?)", cond, re.I)
                m_op = re.fullmatch(r"(>=|<=|!=|==|>|<)\s*([\-+]?\d+(?:\.\d+)?)", cond)
                if m_btw:
                    lo, hi = float(m_btw.group(1)), float(m_btw.group(2))
                    keep = s.isna() | ((s >= lo) & (s <= hi))
                elif m_op:
                    op, val = m_op.group(1), float(m_op.group(2))
                    ops = {
                        ">": s > val,
                        ">=": s >= val,
                        "<": s < val,
                        "<=": s <= val,
                        "==": s == val,
                        "!=": s != val,
                    }
                    keep = s.isna() | ops[op]
                elif cond.lower() in ("not_null", "not null", "notnull"):
                    keep = df[col].notna() & (df[col].astype(str).str.strip() != "")
                else:
                    status = "SKIPPED"
                    detail = f"Không hiểu điều kiện lọc '{cond}'"
                    keep = None

                if keep is not None:
                    affected_rows = int((~keep).sum())
                    if affected_rows > 0:
                        df = df.loc[keep].reset_index(drop=True)
                    detail = f"Lọc '{col} {cond}' -> loại {affected_rows:,} dòng vi phạm"

            elif action == "drop_null":
                bad = df[col].isna() | (df[col].astype(str).str.strip() == "")
                affected_rows = int(bad.sum())
                if affected_rows > 0:
                    df = df.loc[~bad].reset_index(drop=True)
                detail = f"Loại {affected_rows:,} dòng bị NULL/trống ở '{col}'"

            elif action == "fillna":
                is_empty_str = (df[col].dtype == object or pd.api.types.is_string_dtype(df[col])) and True
                null_mask = df[col].isna() | (df[col].astype(str).str.strip() == "") if is_empty_str else df[col].isna()
                fixed_cells = int(null_mask.sum())
                if fixed_cells > 0:
                    cl = cond.lower()
                    if cl == "mean":
                        fill_val = float(pd.to_numeric(df[col], errors="coerce").mean())
                    elif cl == "median":
                        fill_val = float(pd.to_numeric(df[col], errors="coerce").median())
                    elif cl == "mode":
                        modes = df[col].loc[~null_mask].mode()
                        fill_val = modes.iloc[0] if len(modes) else "Unknown"
                    else:
                        try:
                            fill_val = float(cond) if "." in cond else int(cond)
                        except ValueError:
                            fill_val = cond or "Unknown"
                    df.loc[null_mask, col] = fill_val
                detail = f"Điền '{cond or 'Unknown'}' cho {fixed_cells:,} ô NULL/trống ở '{col}'"

            elif action in ("trim", "trim_upper", "trim_lower", "trim_title"):
                s = df[col].astype(str)
                new_s = s.str.strip()
                if action == "trim_upper":
                    new_s = new_s.str.upper()
                elif action == "trim_lower":
                    new_s = new_s.str.lower()
                elif action == "trim_title":
                    new_s = new_s.str.title()
                fixed_cells = int((s != new_s).sum())
                df[col] = new_s.where(df[col].notna(), df[col])
                detail = f"Chuẩn hóa chuỗi ({action}) cột '{col}' ({fixed_cells:,} ô thay đổi)"

            elif action in ("drop_outliers", "clip_outliers"):
                s = pd.to_numeric(df[col], errors="coerce")
                valid = s.dropna()
                if len(valid) >= 4:
                    if "p01" in cond.lower() or "percentile" in cond.lower():
                        lo, hi = float(valid.quantile(0.01)), float(valid.quantile(0.99))
                    else:
                        q1, q3 = float(valid.quantile(0.25)), float(valid.quantile(0.75))
                        iqr = q3 - q1
                        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                    out_mask = s.notna() & ((s < lo) | (s > hi))
                    n_out = int(out_mask.sum())
                    if action == "drop_outliers":
                        affected_rows = n_out
                        if n_out > 0:
                            df = df.loc[~out_mask].reset_index(drop=True)
                        detail = f"Loại {n_out:,} ngoại lai ở '{col}' ngoài [{lo:,.2f}, {hi:,.2f}]"
                    else:
                        fixed_cells = n_out
                        if n_out > 0:
                            df[col] = s.clip(lower=lo, upper=hi)
                        detail = f"Giới hạn (clip) {n_out:,} ngoại lai ở '{col}' về [{lo:,.2f}, {hi:,.2f}]"
                else:
                    status = "SKIPPED"
                    detail = f"Cột '{col}' quá ít dữ liệu số để tính ngoại lai"

            elif action == "flag_01":
                raw = df[col]
                mapped = raw.astype(str).str.strip().str.lower().map({
                    "1": 1, "1.0": 1, "true": 1, "yes": 1, "y": 1, "có": 1,
                    "0": 0, "0.0": 0, "false": 0, "no": 0, "n": 0, "không": 0,
                }).fillna(0).astype(np.int8)
                fixed_cells = int((raw.fillna(-1).astype(str) != mapped.astype(str)).sum())
                df[col] = mapped
                detail = f"Chuẩn hóa cột cờ '{col}' về {{0, 1}} ({fixed_cells:,} ô chuẩn hóa)"

            else:
                status = "SKIPPED"
                detail = f"Chưa hỗ trợ hành động '{action}'"

        except Exception as exc:
            status = f"ERROR: {exc}"
            detail = str(exc)

        total_dropped += max(0, before_rows - len(df))
        total_fixed_cells += fixed_cells
        steps_log.append({
            "step": idx,
            "column": col,
            "action": action,
            "condition": cond,
            "rows_dropped": affected_rows,
            "cells_fixed": fixed_cells,
            "status": status,
            "detail": detail,
            "description": desc,
        })

    report = {
        "source_rows": n_source,
        "clean_rows": len(df),
        "total_rows_dropped": n_source - len(df),
        "total_cells_fixed": total_fixed_cells,
        "rules_count": len(rules or []),
        "steps": steps_log,
    }
    return df, report
