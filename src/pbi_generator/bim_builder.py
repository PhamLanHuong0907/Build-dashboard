"""
Phase 4 & 5: Power BI Semantic Model Builder (model.bim).
Supports both:
- Aviation Star Schema mode (9 specialized tables, 12 relationships, 49 DAX measures)
- Universal Star Schema mode (dynamically builds Tabular schema from ANY generated Parquet tables in data_warehouse/)
"""
import json
from pathlib import Path
from typing import Any, Dict, List
import pyarrow.parquet as pq


def _col(
    name: str,
    data_type: str = "string",
    source_col: str = "",
    summarize_by: str = "none",
    format_string: str = "",
    sort_by_column: str = "",
    is_hidden: bool = False,
    data_category: str = "",
) -> Dict[str, Any]:
    c: Dict[str, Any] = {
        "name": name,
        "dataType": data_type,
        "sourceColumn": source_col or name,
        "summarizeBy": summarize_by,
    }
    if format_string:
        c["formatString"] = format_string
    if sort_by_column:
        c["sortByColumn"] = sort_by_column
    if is_hidden:
        c["isHidden"] = True
    if data_category:
        c["dataCategory"] = data_category
    return c


def _parquet_m_expression(parquet_path: Path) -> List[str]:
    escaped_path = str(parquet_path.resolve()).replace("\\", "\\\\")
    return [
        "let",
        f'    Source = Parquet.Document(File.Contents("{escaped_path}"), [Compression=null, LegacyColumnNameEncoding=false, MaxDepth=null])',
        "in",
        "    Source",
    ]


def _arrow_type_to_bim(pa_type: Any) -> str:
    tstr = str(pa_type).lower()
    if "int" in tstr:
        return "int64"
    if "float" in tstr or "double" in tstr or "decimal" in tstr:
        return "double"
    if "timestamp" in tstr or "date" in tstr:
        return "dateTime"
    if "bool" in tstr:
        return "boolean"
    return "string"


def _build_universal_model_bim(wh_dir: Path, blueprint: Dict[str, Any]) -> Dict[str, Any]:
    """Dynamically construct model.bim for ANY Star Schema dataset from its Parquet schemas."""
    fact_name = blueprint["project"].get("fact_table_name", "Fact_Main")
    dims_cfg = blueprint.get("universal_schema", {}).get("dimensions", [])
    date_col = blueprint["project"].get("primary_date_col")

    table_names = [fact_name, "Data_Quality_Stats"]
    if date_col and (wh_dir / "Dim_Date.parquet").exists():
        table_names.append("Dim_Date")
    for dcfg in dims_cfg:
        if (wh_dir / f"{dcfg['table_name']}.parquet").exists():
            table_names.append(dcfg["table_name"])

    tables: List[Dict[str, Any]] = []
    for tname in table_names:
        p_path = wh_dir / f"{tname}.parquet"
        if not p_path.exists():
            continue
        schema = pq.read_schema(str(p_path))
        col_names_set = set(schema.names)
        cols = []
        for field in schema:
            cname = field.name
            btype = _arrow_type_to_bim(field.type)
            sort_col = ""
            if f"{cname}Sort" in col_names_set:
                sort_col = f"{cname}Sort"
            elif tname == "Dim_Date" and cname in ("MonthName", "MonthShort", "YearMonth") and "MonthNo" in col_names_set:
                sort_col = "MonthNo"
            elif tname == "Dim_Date" and cname in ("DayName", "DayShort") and "DayOfWeekNo" in col_names_set:
                sort_col = "DayOfWeekNo"
            elif tname == "Data_Quality_Stats" and cname == "CheckID" and "CheckSort" in col_names_set:
                sort_col = "CheckSort"

            is_hidden = cname.endswith("Sort") or (cname.endswith("Key") and cname != "RecordKey")
            summ = "sum" if (btype in ("int64", "double") and not is_hidden and not cname.endswith(("No", "Year", "Quarter"))) else "none"
            fmt = "yyyy-mm-dd" if btype == "dateTime" else ("#,##0" if btype == "int64" else ("0.00" if btype == "double" else ""))
            cols.append(_col(cname, btype, summarize_by=summ, format_string=fmt, sort_by_column=sort_col, is_hidden=is_hidden))

        t_obj: Dict[str, Any] = {
            "name": tname,
            "columns": cols,
            "partitions": [
                {
                    "name": f"{tname}-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(p_path)},
                }
            ],
        }
        if tname == fact_name:
            t_obj["measures"] = [
                {
                    "name": m["name"],
                    "expression": m["expression"],
                    "formatString": m.get("formatString", "#,##0"),
                    "displayFolder": m.get("folder", "KPIs"),
                    "description": m.get("description", ""),
                }
                for m in blueprint.get("dax_measures", [])
            ]
        tables.append(t_obj)

    relationships = []
    if "Dim_Date" in table_names:
        relationships.append({
            "name": f"Rel_DimDate_{fact_name}",
            "fromTable": fact_name,
            "fromColumn": "DateKey",
            "toTable": "Dim_Date",
            "toColumn": "DateKey",
            "crossFilteringBehavior": "oneDirection",
        })
    for dcfg in dims_cfg:
        if dcfg["table_name"] in table_names:
            relationships.append({
                "name": f"Rel_{dcfg['table_name']}_{fact_name}",
                "fromTable": fact_name,
                "fromColumn": dcfg["key_column"],
                "toTable": dcfg["table_name"],
                "toColumn": dcfg["key_column"],
                "crossFilteringBehavior": "oneDirection",
            })

    return {
        "name": blueprint["project"]["name"],
        "compatibilityLevel": 1567,
        "model": {
            "culture": "en-US",
            "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "en-US",
            "tables": tables,
            "relationships": relationships,
            "annotations": [
                {"name": "PBI_QueryOrder", "value": json.dumps([t["name"] for t in tables])},
                {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
                {"name": "PBIDesktopVersion", "value": "2.138.0.0"},
            ],
        },
    }


def build_model_bim(workspace_dir: str, blueprint: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(workspace_dir)
    wh_dir = root / blueprint["project"].get("warehouse_dir", "data_warehouse")

    if blueprint["project"].get("dataset_mode") == "universal_star_schema":
        return _build_universal_model_bim(wh_dir, blueprint)

    # --- AVIATION STAR SCHEMA MODEL.BIM ---
    tables: List[Dict[str, Any]] = [
        {
            "name": "Dim_Date",
            "dataCategory": "Time",
            "columns": [
                _col("DateKey", "int64", is_hidden=True),
                _col("Date", "dateTime", format_string="yyyy-mm-dd"),
                _col("DateStr", "string"),
                _col("Year", "int64", format_string="0"),
                _col("Quarter", "int64", format_string="0"),
                _col("QuarterLabel", "string", sort_by_column="Quarter"),
                _col("MonthNo", "int64", format_string="0", is_hidden=True),
                _col("MonthName", "string", sort_by_column="MonthNo"),
                _col("MonthShort", "string", sort_by_column="MonthNo"),
                _col("YearMonth", "string", sort_by_column="MonthNo"),
                _col("DayOfMonth", "int64", format_string="0"),
                _col("DayOfWeekNo", "int64", format_string="0", is_hidden=True),
                _col("DayName", "string", sort_by_column="DayOfWeekNo"),
                _col("DayShort", "string", sort_by_column="DayOfWeekNo"),
                _col("WeekOfYear", "int64", format_string="0"),
                _col("WeekendFlag", "string"),
            ],
            "hierarchies": [
                {
                    "name": "Calendar Hierarchy",
                    "levels": [
                        {"name": "Year", "ordinal": 0, "column": "Year"},
                        {"name": "Quarter", "ordinal": 1, "column": "QuarterLabel"},
                        {"name": "Month", "ordinal": 2, "column": "MonthName"},
                        {"name": "Date", "ordinal": 3, "column": "Date"},
                    ],
                }
            ],
            "partitions": [
                {
                    "name": "Dim_Date-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Dim_Date.parquet")},
                }
            ],
        },
        {
            "name": "Dim_Airline",
            "columns": [
                _col("AirlineKey", "int64", is_hidden=True),
                _col("Reporting_Airline", "string"),
                _col("AirlineName", "string"),
                _col("AirlineLabel", "string"),
                _col("ScheduledFlights", "int64", summarize_by="sum", format_string="#,##0"),
            ],
            "partitions": [
                {
                    "name": "Dim_Airline-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Dim_Airline.parquet")},
                }
            ],
        },
        {
            "name": "Dim_OriginAirport",
            "columns": [
                _col("AirportKey", "int64", is_hidden=True),
                _col("AirportCode", "string"),
                _col("CityName", "string", data_category="City"),
                _col("State", "string", data_category="StateOrProvince"),
                _col("AirportLabel", "string"),
                _col("RoleFlights", "int64", summarize_by="sum", format_string="#,##0"),
                _col("VolumeSharePct", "double", summarize_by="none", format_string="0.00"),
                _col("CumulativeSharePct", "double", summarize_by="none", format_string="0.00"),
                _col("AirportGroup", "string"),
                _col("AirportGroupCode", "string"),
            ],
            "hierarchies": [
                {
                    "name": "Origin Geography",
                    "levels": [
                        {"name": "Origin State", "ordinal": 0, "column": "State"},
                        {"name": "Origin City", "ordinal": 1, "column": "CityName"},
                        {"name": "Origin Airport", "ordinal": 2, "column": "AirportCode"},
                    ],
                }
            ],
            "partitions": [
                {
                    "name": "Dim_OriginAirport-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Dim_OriginAirport.parquet")},
                }
            ],
        },
        {
            "name": "Dim_DestinationAirport",
            "columns": [
                _col("AirportKey", "int64", is_hidden=True),
                _col("AirportCode", "string"),
                _col("CityName", "string", data_category="City"),
                _col("State", "string", data_category="StateOrProvince"),
                _col("AirportLabel", "string"),
                _col("RoleFlights", "int64", summarize_by="sum", format_string="#,##0"),
                _col("VolumeSharePct", "double", summarize_by="none", format_string="0.00"),
                _col("CumulativeSharePct", "double", summarize_by="none", format_string="0.00"),
                _col("AirportGroup", "string"),
                _col("AirportGroupCode", "string"),
            ],
            "hierarchies": [
                {
                    "name": "Destination Geography",
                    "levels": [
                        {"name": "Dest State", "ordinal": 0, "column": "State"},
                        {"name": "Dest City", "ordinal": 1, "column": "CityName"},
                        {"name": "Dest Airport", "ordinal": 2, "column": "AirportCode"},
                    ],
                }
            ],
            "partitions": [
                {
                    "name": "Dim_DestinationAirport-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Dim_DestinationAirport.parquet")},
                }
            ],
        },
        {
            "name": "Dim_Route",
            "columns": [
                _col("RouteKey", "string", is_hidden=True),
                _col("RouteLabel", "string"),
                _col("Origin", "string"),
                _col("Dest", "string"),
                _col("OriginState", "string"),
                _col("DestState", "string"),
                _col("AvgDistance", "double", summarize_by="average", format_string="#,##0.0"),
                _col("DistanceBand", "string", sort_by_column="DistanceBandSort"),
                _col("DistanceBandSort", "int64", is_hidden=True),
                _col("RouteFlights", "int64", summarize_by="sum", format_string="#,##0"),
                _col("VolumeSharePct", "double", summarize_by="none", format_string="0.00"),
                _col("CumulativeSharePct", "double", summarize_by="none", format_string="0.00"),
                _col("RouteGroup", "string"),
                _col("RouteGroupCode", "string"),
            ],
            "partitions": [
                {
                    "name": "Dim_Route-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Dim_Route.parquet")},
                }
            ],
        },
        {
            "name": "Dim_TimeBlock",
            "columns": [
                _col("DepHour", "int64", format_string="0"),
                _col("HourLabel", "string", sort_by_column="DepHour"),
                _col("DepTimeBlock", "string", sort_by_column="DepTimeBlockSort"),
                _col("DepTimeBlockSort", "int64", is_hidden=True),
            ],
            "partitions": [
                {
                    "name": "Dim_TimeBlock-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Dim_TimeBlock.parquet")},
                }
            ],
        },
        {
            "name": "Fact_Flight",
            "columns": [
                _col("FlightKey", "int64", format_string="0"),
                _col("DateKey", "int64", is_hidden=True),
                _col("AirlineKey", "int64", is_hidden=True),
                _col("OriginAirportKey", "int64", is_hidden=True),
                _col("DestinationAirportKey", "int64", is_hidden=True),
                _col("RouteKey", "string", is_hidden=True),
                _col("DepHour", "int64", format_string="0"),
                _col("ArrHour", "int64", format_string="0"),
                _col("Flight_Number_Reporting_Airline", "int64", format_string="0"),
                _col("CRSDepTime", "int64", format_string="0"),
                _col("CRSDepTimeFormatted", "string"),
                _col("DepTime", "double", format_string="0"),
                _col("DepDelay", "double", summarize_by="average", format_string="0.0"),
                _col("DepDelayMinutes", "double", summarize_by="sum", format_string="#,##0.0"),
                _col("DepDel15", "double", format_string="0"),
                _col("TaxiOut", "double", summarize_by="average", format_string="0.0"),
                _col("WheelsOff", "double", format_string="0"),
                _col("WheelsOn", "double", format_string="0"),
                _col("TaxiIn", "double", summarize_by="average", format_string="0.0"),
                _col("CRSArrTime", "int64", format_string="0"),
                _col("CRSArrTimeFormatted", "string"),
                _col("ArrTime", "double", format_string="0"),
                _col("ArrDelay", "double", summarize_by="average", format_string="0.0"),
                _col("ArrDelayMinutes", "double", summarize_by="sum", format_string="#,##0.0"),
                _col("ArrDel15", "double", format_string="0"),
                _col("Cancelled", "double", format_string="0"),
                _col("CancellationCode", "string"),
                _col("CancellationReasonLabel", "string"),
                _col("Diverted", "double", format_string="0"),
                _col("CRSElapsedTime", "double", summarize_by="average", format_string="0.0"),
                _col("ActualElapsedTime", "double", summarize_by="average", format_string="0.0"),
                _col("AirTime", "double", summarize_by="average", format_string="0.0"),
                _col("Distance", "double", summarize_by="sum", format_string="#,##0"),
                _col("CarrierDelay", "double", summarize_by="sum", format_string="#,##0"),
                _col("WeatherDelay", "double", summarize_by="sum", format_string="#,##0"),
                _col("NASDelay", "double", summarize_by="sum", format_string="#,##0"),
                _col("SecurityDelay", "double", summarize_by="sum", format_string="#,##0"),
                _col("LateAircraftDelay", "double", summarize_by="sum", format_string="#,##0"),
                _col("DelayCauseTotal", "double", summarize_by="sum", format_string="#,##0"),
                _col("GroundTime", "double", summarize_by="average", format_string="0.0"),
                _col("BlockTimeVariance", "double", summarize_by="average", format_string="+0.0;-0.0;0.0"),
                _col("AirSpeedMph", "double", summarize_by="average", format_string="0.0"),
                _col("DepTimeBlock", "string", sort_by_column="DepTimeBlockSort"),
                _col("DepTimeBlockSort", "int64", is_hidden=True),
                _col("DistanceBand", "string", sort_by_column="DistanceBandSort"),
                _col("DistanceBandSort", "int64", is_hidden=True),
                _col("DepDelayBand", "string", sort_by_column="DepDelayBandSort"),
                _col("DepDelayBandSort", "int64", is_hidden=True),
                _col("ArrDelayBand", "string", sort_by_column="ArrDelayBandSort"),
                _col("ArrDelayBandSort", "int64", is_hidden=True),
                _col("FlightOutcome", "string", sort_by_column="FlightOutcomeSort"),
                _col("FlightOutcomeSort", "int64", is_hidden=True),
                _col("IsCancelled", "int64", format_string="0"),
                _col("IsDiverted", "int64", format_string="0"),
                _col("IsOperated", "int64", format_string="0"),
                _col("IsCompletedToDestination", "int64", format_string="0"),
                _col("IsDepOTPEligible", "int64", format_string="0"),
                _col("IsArrOTPEligible", "int64", format_string="0"),
                _col("IsEligibleForOTP", "int64", format_string="0"),
                _col("IsDepDelay15", "int64", format_string="0"),
                _col("IsArrDelay15", "int64", format_string="0"),
                _col("IsSevereDelay", "int64", format_string="0"),
                _col("IsExtremeDelay", "int64", format_string="0"),
            ],
            "measures": [],
            "partitions": [
                {
                    "name": "Fact_Flight-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Fact_Flight.parquet")},
                }
            ],
        },
        {
            "name": "Fact_DelayCause",
            "columns": [
                _col("FlightKey", "int64", is_hidden=True),
                _col("DateKey", "int64", is_hidden=True),
                _col("AirlineKey", "int64", is_hidden=True),
                _col("OriginAirportKey", "int64", is_hidden=True),
                _col("DestinationAirportKey", "int64", is_hidden=True),
                _col("RouteKey", "string", is_hidden=True),
                _col("DepHour", "int64", is_hidden=True),
                _col("ArrDelayBand", "string"),
                _col("CauseName", "string", sort_by_column="CauseSort"),
                _col("CauseSort", "int64", is_hidden=True),
                _col("CauseMinutes", "double", summarize_by="sum", format_string="#,##0"),
            ],
            "measures": [],
            "partitions": [
                {
                    "name": "Fact_DelayCause-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Fact_DelayCause.parquet")},
                }
            ],
        },
        {
            "name": "Data_Quality_Stats",
            "columns": [
                _col("CheckID", "string", sort_by_column="CheckSort"),
                _col("Category", "string"),
                _col("CheckName", "string"),
                _col("RecordCount", "int64", summarize_by="sum", format_string="#,##0"),
                _col("Percentage", "double", summarize_by="none", format_string="0.0000"),
                _col("Status", "string"),
                _col("CheckSort", "int64", is_hidden=True),
            ],
            "partitions": [
                {
                    "name": "Data_Quality_Stats-Partition",
                    "mode": "import",
                    "source": {"type": "m", "expression": _parquet_m_expression(wh_dir / "Data_Quality_Stats.parquet")},
                }
            ],
        },
    ]

    fact_flight_table = next(t for t in tables if t["name"] == "Fact_Flight")
    fact_cause_table = next(t for t in tables if t["name"] == "Fact_DelayCause")

    for m in blueprint.get("dax_measures", []):
        m_obj = {
            "name": m["name"],
            "expression": m["expression"],
            "formatString": m.get("formatString", "#,##0"),
            "displayFolder": m.get("folder", "KPIs"),
            "description": m.get("description", ""),
        }
        if "Fact_DelayCause" in m["expression"] and "Fact_Flight" not in m["expression"]:
            fact_cause_table["measures"].append(m_obj)
        else:
            fact_flight_table["measures"].append(m_obj)

    relationships = [
        {"name": "Rel_DimDate_FactFlight", "fromTable": "Fact_Flight", "fromColumn": "DateKey", "toTable": "Dim_Date", "toColumn": "DateKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimAirline_FactFlight", "fromTable": "Fact_Flight", "fromColumn": "AirlineKey", "toTable": "Dim_Airline", "toColumn": "AirlineKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimOrigin_FactFlight", "fromTable": "Fact_Flight", "fromColumn": "OriginAirportKey", "toTable": "Dim_OriginAirport", "toColumn": "AirportKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimDest_FactFlight", "fromTable": "Fact_Flight", "fromColumn": "DestinationAirportKey", "toTable": "Dim_DestinationAirport", "toColumn": "AirportKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimRoute_FactFlight", "fromTable": "Fact_Flight", "fromColumn": "RouteKey", "toTable": "Dim_Route", "toColumn": "RouteKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimTimeBlock_FactFlight", "fromTable": "Fact_Flight", "fromColumn": "DepHour", "toTable": "Dim_TimeBlock", "toColumn": "DepHour", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimDate_FactDelayCause", "fromTable": "Fact_DelayCause", "fromColumn": "DateKey", "toTable": "Dim_Date", "toColumn": "DateKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimAirline_FactDelayCause", "fromTable": "Fact_DelayCause", "fromColumn": "AirlineKey", "toTable": "Dim_Airline", "toColumn": "AirlineKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimOrigin_FactDelayCause", "fromTable": "Fact_DelayCause", "fromColumn": "OriginAirportKey", "toTable": "Dim_OriginAirport", "toColumn": "AirportKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimDest_FactDelayCause", "fromTable": "Fact_DelayCause", "fromColumn": "DestinationAirportKey", "toTable": "Dim_DestinationAirport", "toColumn": "AirportKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimRoute_FactDelayCause", "fromTable": "Fact_DelayCause", "fromColumn": "RouteKey", "toTable": "Dim_Route", "toColumn": "RouteKey", "crossFilteringBehavior": "oneDirection"},
        {"name": "Rel_DimTimeBlock_FactDelayCause", "fromTable": "Fact_DelayCause", "fromColumn": "DepHour", "toTable": "Dim_TimeBlock", "toColumn": "DepHour", "crossFilteringBehavior": "oneDirection"},
    ]

    return {
        "name": blueprint["project"]["name"],
        "compatibilityLevel": 1567,
        "model": {
            "culture": "en-US",
            "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "en-US",
            "tables": tables,
            "relationships": relationships,
            "annotations": [
                {"name": "PBI_QueryOrder", "value": json.dumps([t["name"] for t in tables])},
                {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
                {"name": "PBIDesktopVersion", "value": "2.138.0.0"},
            ],
        },
    }
