"""
Phase 5 & Phase 7: Independent KPI Calculator, Reconciliation & Live Power BI Validator.
- Calculates all core & supplementary KPIs independently from the Star Schema Parquet files
- Validates business rules:
  * Total Flights = Completed + Cancelled + Diverted + Unknown
  * Non-Cancelled Rate vs Completion-to-Destination Rate
  * Departure OTP & Arrival OTP denominators (excluding Cancelled and Diverted)
  * 5 Delay Causes share
  * Slice tests (by Airline='AA', Origin='MIA', Month='July') per Section 14.2
- Detects running Power BI Desktop AnalysisServicesWorkspace port if open.
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def compute_kpi_slice(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute the full set of KPIs on any slice of Fact_Flight."""
    n_total = int(len(df))
    if n_total == 0:
        return {"Total Flights": 0}

    n_cancelled = int((df["IsCancelled"] == 1).sum())
    n_non_cancelled = n_total - n_cancelled
    n_diverted = int((df["IsDiverted"] == 1).sum())
    n_completed = int((df["IsCompletedToDestination"] == 1).sum())
    n_operated = int((df["IsOperated"] == 1).sum())
    n_unknown = int((df["FlightOutcome"] == "Unknown").sum())

    canc_rate = n_cancelled / n_total
    non_canc_rate = n_non_cancelled / n_total
    div_rate = n_diverted / n_non_cancelled if n_non_cancelled > 0 else 0.0
    comp_rate = n_completed / n_total

    # OTP
    dep_elig_mask = df["IsDepOTPEligible"] == 1
    n_dep_elig = int(dep_elig_mask.sum())
    n_dep_del15 = int((df["IsDepDelay15"] == 1).sum())
    dep_del15_rate = n_dep_del15 / n_dep_elig if n_dep_elig > 0 else 0.0
    dep_otp = 1.0 - dep_del15_rate

    arr_elig_mask = df["IsArrOTPEligible"] == 1
    n_arr_elig = int(arr_elig_mask.sum())
    n_arr_del15 = int((df["IsArrDelay15"] == 1).sum())
    arr_del15_rate = n_arr_del15 / n_arr_elig if n_arr_elig > 0 else 0.0
    arr_otp = 1.0 - arr_del15_rate

    # Delay durations
    total_dep_delay_min = float(df["DepDelayMinutes"].dropna().sum())
    total_arr_delay_min = float(df["ArrDelayMinutes"].dropna().sum())
    avg_dep_delay_min = float(df["DepDelayMinutes"].dropna().mean()) if df["DepDelayMinutes"].notna().any() else 0.0
    avg_arr_delay_min = float(df["ArrDelayMinutes"].dropna().mean()) if df["ArrDelayMinutes"].notna().any() else 0.0
    avg_signed_arr_delay = float(df["ArrDelay"].dropna().mean()) if df["ArrDelay"].notna().any() else 0.0

    arr_min_non_null = df["ArrDelayMinutes"].dropna()
    median_arr_delay = float(np.percentile(arr_min_non_null, 50)) if len(arr_min_non_null) > 0 else 0.0
    p90_arr_delay = float(np.percentile(arr_min_non_null, 90)) if len(arr_min_non_null) > 0 else 0.0
    p95_arr_delay = float(np.percentile(arr_min_non_null, 95)) if len(arr_min_non_null) > 0 else 0.0

    n_severe_delay = int((df["IsSevereDelay"] == 1).sum())
    severe_delay_rate = n_severe_delay / n_arr_elig if n_arr_elig > 0 else 0.0
    n_extreme_delay = int((df["IsExtremeDelay"] == 1).sum())
    extreme_delay_rate = n_extreme_delay / n_arr_elig if n_arr_elig > 0 else 0.0

    # Delay Causes
    c_carrier = float(df["CarrierDelay"].dropna().sum())
    c_weather = float(df["WeatherDelay"].dropna().sum())
    c_nas = float(df["NASDelay"].dropna().sum())
    c_security = float(df["SecurityDelay"].dropna().sum())
    c_late_aircraft = float(df["LateAircraftDelay"].dropna().sum())
    c_total = c_carrier + c_weather + c_nas + c_security + c_late_aircraft

    # Operational efficiency
    avg_taxi_out = float(df["TaxiOut"].dropna().mean()) if df["TaxiOut"].notna().any() else 0.0
    avg_taxi_in = float(df["TaxiIn"].dropna().mean()) if df["TaxiIn"].notna().any() else 0.0
    avg_ground_time = float(df["GroundTime"].dropna().mean()) if df["GroundTime"].notna().any() else 0.0
    avg_air_time = float(df["AirTime"].dropna().mean()) if df["AirTime"].notna().any() else 0.0
    avg_crs_elapsed = float(df["CRSElapsedTime"].dropna().mean()) if df["CRSElapsedTime"].notna().any() else 0.0
    avg_act_elapsed = float(df["ActualElapsedTime"].dropna().mean()) if df["ActualElapsedTime"].notna().any() else 0.0
    avg_block_variance = float(df["BlockTimeVariance"].dropna().mean()) if df["BlockTimeVariance"].notna().any() else 0.0
    total_distance = float(df["Distance"].dropna().sum())
    avg_distance = float(df["Distance"].dropna().mean()) if df["Distance"].notna().any() else 0.0
    total_air_hours = float(df["AirTime"].dropna().sum()) / 60.0
    avg_air_speed = total_distance / total_air_hours if total_air_hours > 0 else 0.0

    return {
        "Total Flights": n_total,
        "Completed Flights": n_completed,
        "Completion-to-Destination Rate (%)": round(comp_rate * 100, 4),
        "Non-Cancelled Flights": n_non_cancelled,
        "Non-Cancelled Rate (%)": round(non_canc_rate * 100, 4),
        "Cancelled Flights": n_cancelled,
        "Cancellation Rate (%)": round(canc_rate * 100, 4),
        "Diverted Flights": n_diverted,
        "Diversion Rate (%)": round(div_rate * 100, 4),
        "Operated Flights": n_operated,
        "Unknown Outcome Flights": n_unknown,
        "Outcome Sum Reconciled": n_completed + n_cancelled + n_diverted + n_unknown == n_total,
        "Departure Eligible Flights": n_dep_elig,
        "Departure Delay 15+ Flights": n_dep_del15,
        "Departure Delay 15+ Rate (%)": round(dep_del15_rate * 100, 4),
        "Departure OTP (%)": round(dep_otp * 100, 4),
        "Arrival Eligible Flights": n_arr_elig,
        "Arrival Delay 15+ Flights": n_arr_del15,
        "Arrival Delay 15+ Rate (%)": round(arr_del15_rate * 100, 4),
        "Arrival OTP (%)": round(arr_otp * 100, 4),
        "Total Departure Delay Minutes": round(total_dep_delay_min, 1),
        "Total Arrival Delay Minutes": round(total_arr_delay_min, 1),
        "Avg Departure Delay (Min)": round(avg_dep_delay_min, 2),
        "Avg Arrival Delay (Min)": round(avg_arr_delay_min, 2),
        "Avg Signed Arrival Delay (Min)": round(avg_signed_arr_delay, 2),
        "Median Arrival Delay (Min)": round(median_arr_delay, 2),
        "P90 Arrival Delay (Min)": round(p90_arr_delay, 2),
        "P95 Arrival Delay (Min)": round(p95_arr_delay, 2),
        "Severe Delay Flights (>60m)": n_severe_delay,
        "Severe Delay Rate (%)": round(severe_delay_rate * 100, 4),
        "Extreme Delay Flights (>120m)": n_extreme_delay,
        "Extreme Delay Rate (%)": round(extreme_delay_rate * 100, 4),
        "Total Delay Cause Minutes": round(c_total, 1),
        "Carrier Delay Minutes": round(c_carrier, 1),
        "Carrier Share (%)": round(c_carrier * 100 / c_total, 2) if c_total > 0 else 0.0,
        "Weather Delay Minutes": round(c_weather, 1),
        "Weather Share (%)": round(c_weather * 100 / c_total, 2) if c_total > 0 else 0.0,
        "NAS Delay Minutes": round(c_nas, 1),
        "NAS Share (%)": round(c_nas * 100 / c_total, 2) if c_total > 0 else 0.0,
        "Security Delay Minutes": round(c_security, 1),
        "Security Share (%)": round(c_security * 100 / c_total, 2) if c_total > 0 else 0.0,
        "Late Aircraft Delay Minutes": round(c_late_aircraft, 1),
        "Late Aircraft Share (%)": round(c_late_aircraft * 100 / c_total, 2) if c_total > 0 else 0.0,
        "Avg Taxi-Out (Min)": round(avg_taxi_out, 2),
        "Avg Taxi-In (Min)": round(avg_taxi_in, 2),
        "Avg Ground Time (Min)": round(avg_ground_time, 2),
        "Avg AirTime (Min)": round(avg_air_time, 2),
        "Avg Scheduled Elapsed (Min)": round(avg_crs_elapsed, 2),
        "Avg Actual Elapsed (Min)": round(avg_act_elapsed, 2),
        "Block Time Variance (Min)": round(avg_block_variance, 2),
        "Total Distance (Miles)": round(total_distance, 0),
        "Avg Distance (Miles)": round(avg_distance, 2),
        "Avg Air Speed (MPH)": round(avg_air_speed, 2),
    }


def detect_running_pbi_ports() -> List[Dict[str, Any]]:
    """Scan both standard and Microsoft Store Power BI Desktop AnalysisServicesWorkspaces for active SSAS ports."""
    candidates = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    user_profile = os.environ.get("USERPROFILE", "")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Microsoft" / "Power BI Desktop" / "AnalysisServicesWorkspaces")
    if user_profile:
        candidates.append(Path(user_profile) / "Microsoft" / "Power BI Desktop Store App" / "AnalysisServicesWorkspaces")
    instances = []
    for ws_root in candidates:
        if not ws_root.exists():
            continue
        for port_file in ws_root.glob("*/Data/msmdsrv.port.txt"):
            try:
                port_text = port_file.read_text(encoding="utf-16-le").strip()
                if not port_text.isdigit():
                    port_text = port_file.read_text(encoding="utf-8", errors="ignore").strip().replace("\x00", "")
                if port_text.isdigit():
                    instances.append({
                        "workspace": port_file.parents[1].name,
                        "port": int(port_text),
                        "connection_string": f"Data Source=localhost:{port_text};",
                    })
            except Exception:
                continue
    return instances


def _measures_markdown(block: Dict[str, Any], title: str) -> List[str]:
    meta = block["meta"]
    lines = [
        title,
        "",
        f"- Nguồn đặc tả: `{meta.get('requirement_doc') or 'N/A'}` (sửa lần cuối: {meta.get('requirement_modified') or 'N/A'})",
        f"- Thời điểm đối soát: {meta['evaluated_at']}",
        f"- Kết quả: **{meta['ok']}** OK / {meta['blank']} Blank / {meta['unsupported']} chưa hỗ trợ / {meta['error']} lỗi (tổng {meta['total']} measure)",
        "",
        "| Measure | Giá trị | Trạng thái | Công thức DAX |",
        "|---|---:|---|---|",
    ]
    for m in block["measures"]:
        expr = m["expression"].replace("|", "\\|")
        lines.append(f"| **{m['name']}** | {m['display']} | {m['status']} | `{expr}` |")
    return lines


def _apply_requirement_measures(result: Dict[str, Any], workspace_dir: str, blueprint: Dict[str, Any]) -> Dict[str, Any]:
    """Make the KPI audit follow the blueprint (= the user's Requirement.md): every DAX measure is evaluated independently."""
    from src.pbi_connector.dax_eval import evaluate_blueprint_measures

    block = evaluate_blueprint_measures(workspace_dir, blueprint)
    if result.get("overall") and result.get("dataset_mode") != "universal_star_schema":
        result["aviation_core_kpis"] = result["overall"]
    result["measures"] = block["measures"]
    result["measures_meta"] = block["meta"]
    result["overall"] = {m["name"]: m["value"] for m in block["measures"]}
    return block


def run_kpi_validation(workspace_dir: str, blueprint: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    t0 = time.time()
    root = Path(workspace_dir)
    warehouse_dir = root / "data_warehouse"
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if blueprint is None:
        bp_path = root / "config" / "project_blueprint.json"
        blueprint = json.loads(bp_path.read_text(encoding="utf-8")) if bp_path.exists() else {}

    if blueprint.get("project", {}).get("dataset_mode") == "universal_star_schema" or not (warehouse_dir / "Fact_Flight.parquet").exists():
        fact_name = blueprint.get("project", {}).get("fact_table_name", "Fact_Main")
        result = {
            "dataset_mode": "universal_star_schema",
            "overall": {},
            "slice_tests": {},
            "active_pbi_instances": detect_running_pbi_ports(),
        }
        block = _apply_requirement_measures(result, workspace_dir, blueprint)
        result["elapsed_seconds"] = round(time.time() - t0, 2)
        with open(reports_dir / "kpi_validation_results.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        md_u = _measures_markdown(block, "# BÁO CÁO ĐỐI SOÁT KPI THEO REQUIREMENT")
        (reports_dir / "KPI_Validation_Report.md").write_text("\n".join(md_u), encoding="utf-8")
        return result

    print("[Phase 5] Loading Star Schema Parquet tables for independent KPI calculation & validation...")
    fact_df = pq.read_table(str(warehouse_dir / "Fact_Flight.parquet")).to_pandas()
    dim_airline = pq.read_table(str(warehouse_dir / "Dim_Airline.parquet")).to_pandas()
    dim_origin = pq.read_table(str(warehouse_dir / "Dim_OriginAirport.parquet")).to_pandas()
    dim_date = pq.read_table(str(warehouse_dir / "Dim_Date.parquet")).to_pandas()

    # 1. Full Dataset KPIs
    overall_kpis = compute_kpi_slice(fact_df)

    # 2. Slice Tests per Section 14.2:
    # - Slice by Airline = AA
    aa_key = int(dim_airline.loc[dim_airline["Reporting_Airline"] == "AA", "AirlineKey"].iloc[0])
    aa_kpis = compute_kpi_slice(fact_df.loc[fact_df["AirlineKey"] == aa_key])

    # - Slice by Origin Airport = ATL (or MIA)
    atl_key = int(dim_origin.loc[dim_origin["AirportCode"] == "ATL", "AirportKey"].iloc[0])
    atl_kpis = compute_kpi_slice(fact_df.loc[fact_df["OriginAirportKey"] == atl_key])

    # - Slice by Month = July 2025 (MonthNo = 7)
    july_keys = set(dim_date.loc[dim_date["MonthNo"] == 7, "DateKey"].tolist())
    july_kpis = compute_kpi_slice(fact_df.loc[fact_df["DateKey"].isin(july_keys)])

    # 3. Monthly Breakdown for R10 (Period-over-period MoM variance)
    fact_with_month = fact_df.merge(dim_date[["DateKey", "MonthNo", "MonthName"]], on="DateKey", how="left")
    monthly_rows = []
    for m_no, m_df in fact_with_month.groupby("MonthNo"):
        m_name = m_df["MonthName"].iloc[0]
        mk = compute_kpi_slice(m_df)
        monthly_rows.append({
            "MonthNo": int(m_no),
            "MonthName": m_name,
            "Total Flights": mk["Total Flights"],
            "Completion-to-Dest Rate (%)": mk["Completion-to-Destination Rate (%)"],
            "Departure OTP (%)": mk["Departure OTP (%)"],
            "Arrival OTP (%)": mk["Arrival OTP (%)"],
            "Cancellation Rate (%)": mk["Cancellation Rate (%)"],
            "Diversion Rate (%)": mk["Diversion Rate (%)"],
            "Avg Arrival Delay (Min)": mk["Avg Arrival Delay (Min)"],
            "P90 Arrival Delay (Min)": mk["P90 Arrival Delay (Min)"],
        })

    # 4. Airline Benchmark Table (R3, R4, R9)
    fact_with_airline = fact_df.merge(dim_airline[["AirlineKey", "Reporting_Airline", "AirlineName"]], on="AirlineKey", how="left")
    airline_rows = []
    for code, a_df in fact_with_airline.groupby("Reporting_Airline"):
        ak = compute_kpi_slice(a_df)
        airline_rows.append({
            "Airline": code,
            "AirlineName": a_df["AirlineName"].iloc[0],
            "Total Flights": ak["Total Flights"],
            "Completion Rate (%)": ak["Completion-to-Destination Rate (%)"],
            "Departure OTP (%)": ak["Departure OTP (%)"],
            "Arrival OTP (%)": ak["Arrival OTP (%)"],
            "Cancellation Rate (%)": ak["Cancellation Rate (%)"],
            "Diversion Rate (%)": ak["Diversion Rate (%)"],
            "Avg Arr Delay (Min)": ak["Avg Arrival Delay (Min)"],
            "P90 Arr Delay (Min)": ak["P90 Arrival Delay (Min)"],
            "Severe Delay Rate (%)": ak["Severe Delay Rate (%)"],
        })
    airline_rows = sorted(airline_rows, key=lambda x: x["Total Flights"], reverse=True)

    result = {
        "overall": overall_kpis,
        "slice_tests": {
            "Airline_AA": aa_kpis,
            "Origin_ATL": atl_kpis,
            "Month_July_2025": july_kpis,
        },
        "monthly_trend": monthly_rows,
        "airline_benchmark": airline_rows,
        "active_pbi_instances": detect_running_pbi_ports(),
    }
    measures_block = _apply_requirement_measures(result, workspace_dir, blueprint)
    result["elapsed_seconds"] = round(time.time() - t0, 2)

    with open(reports_dir / "kpi_validation_results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Write Markdown Report
    md = [
        "# BÁO CÁO ĐỐI SOÁT & KIỂM THỬ ĐỘC LẬP HỆ THỐNG KPI (PHASE 5 & PHASE 7)",
        "",
        "## 1. Kết Quả Tính Toán Độc Lập Bộ KPI Cốt Lõi (Toàn Mạng Bay & Kiểm Thử Lát Cắt Slicer)",
        "",
        "| Chỉ số KPI | Toàn Mạng Bay (All) | Lát cắt Hãng `AA` | Lát cắt Sân bay `ATL` | Lát cắt Tháng `07/2025` |",
        "|---|---:|---:|---:|---:|",
    ]
    for k in overall_kpis.keys():
        v_all = overall_kpis[k]
        v_aa = aa_kpis.get(k, "-")
        v_atl = atl_kpis.get(k, "-")
        v_jul = july_kpis.get(k, "-")
        if isinstance(v_all, int) and not isinstance(v_all, bool):
            md.append(f"| **{k}** | {v_all:,} | {v_aa:,} | {v_atl:,} | {v_jul:,} |")
        elif isinstance(v_all, float):
            md.append(f"| **{k}** | {v_all:,.2f} | {v_aa:,.2f} | {v_atl:,.2f} | {v_jul:,.2f} |")
        else:
            md.append(f"| **{k}** | {v_all} | {v_aa} | {v_atl} | {v_jul} |")

    md.extend([
        "",
        "## 2. Xu Hướng Hiệu Suất Theo Tháng (Biến Động Kỳ Phân Tích R2 & R10)",
        "",
        "| Tháng | Tổng chuyến | Completion-to-Dest (%) | Dep OTP (%) | Arr OTP (%) | Tỷ lệ Hủy (%) | Tỷ lệ Divert (%) | Avg Arr Delay (Phút) | P90 Arr Delay (Phút) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for m in monthly_rows:
        md.append(
            f"| **{m['MonthName']} ({m['MonthNo']}/2025)** | {m['Total Flights']:,} | {m['Completion-to-Dest Rate (%)']:.2f}% | "
            f"{m['Departure OTP (%)']:.2f}% | {m['Arrival OTP (%)']:.2f}% | {m['Cancellation Rate (%)']:.2f}% | "
            f"{m['Diversion Rate (%)']:.2f}% | {m['Avg Arrival Delay (Min)']:.2f} | {m['P90 Arrival Delay (Min)']:.1f} |"
        )

    md.extend([
        "",
        "## 3. Bảng Xếp Hạng Hiệu Suất 14 Hãng Hàng Không (Benchmark R3, R4, R9)",
        "",
        "| Mã Hãng | Tên Hãng | Tổng Chuyến | Completion (%) | Dep OTP (%) | Arr OTP (%) | Tỷ lệ Hủy (%) | Tỷ lệ Divert (%) | Avg Arr Delay | P90 Arr Delay | Trễ Nặng >60p (%) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for a in airline_rows:
        md.append(
            f"| **{a['Airline']}** | {a['AirlineName']} | {a['Total Flights']:,} | {a['Completion Rate (%)']:.2f}% | "
            f"{a['Departure OTP (%)']:.2f}% | {a['Arrival OTP (%)']:.2f}% | {a['Cancellation Rate (%)']:.2f}% | "
            f"{a['Diversion Rate (%)']:.2f}% | {a['Avg Arr Delay (Min)']:.2f} | {a['P90 Arr Delay (Min)']:.1f} | {a['Severe Delay Rate (%)']:.2f}% |"
        )

    md.append("")
    md.extend(_measures_markdown(measures_block, "## 4. Đối Soát Từng DAX Measure Theo Requirement.md"))
    (reports_dir / "KPI_Validation_Report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[Phase 5] Independent KPI validation completed in {result['elapsed_seconds']}s. Saved reports/KPI_Validation_Report.md")
    return result


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    run_kpi_validation(str(root))
