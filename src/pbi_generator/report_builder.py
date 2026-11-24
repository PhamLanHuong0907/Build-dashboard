"""
Phase 6: Full-Featured Power BI Report Layout & Visual Container Builder (report.json).
Supports ALL 66+ Power BI Visuals (44 Built-in + 22 Microsoft AppSource Samples + Imported .pbiviz):
- Dynamic universal `field_wells` binding (Category, Y, Y2, Series, Rows, Columns, Values, Group,
  Details, X, Size, Play, Breakdown, MinValue, MaxValue, TargetValue, Indicator, TrendAxis, Goal,
  Analyze, ExplainBy, ExpandBy, Data, Tooltips, plus all AppSource custom dataRoles)
- Full backwards compatibility with legacy shorthand blueprint fields (`category`, `values`, etc.)
- Full Power BI Format & Analytics properties:
  * Title, Legend (show/position), Data Labels, Axes, Background, Border, Radius
  * Constant / Target Reference Line (e.g., 80% OTP Goal Line)
  * Native Power BI Sort (OrderBy Ascending/Descending)
  * Native Power BI Top N / Bottom N Visual Filter
  * Embedded Python (`pythonVisual`) & R (`scriptVisual`) scripts
  * Layout elements (`textbox`, `actionButton`, `shape`)
  * `publicCustomVisuals` registration for AppSource & imported `.pbiviz` visuals
"""
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from src.pbi_generator.visual_catalog import get_visual_spec_by_type


def _lit_str(val: str) -> Dict[str, Any]:
    escaped = str(val).replace("'", "''")
    return {"expr": {"Literal": {"Value": f"'{escaped}'"}}}


def _lit_bool(val: bool) -> Dict[str, Any]:
    return {"expr": {"Literal": {"Value": "true" if val else "false"}}}


def _lit_num(val: float) -> Dict[str, Any]:
    return {"expr": {"Literal": {"Value": f"{val}D"}}}


def _lit_color(hex_color: str) -> Dict[str, Any]:
    return {"solid": {"color": _lit_str(hex_color)}}


class ReportBuilder:
    def __init__(self, blueprint: Dict[str, Any], workspace_dir: Optional[str] = None):
        self.blueprint = blueprint
        self.workspace_dir = workspace_dir
        self.fact_table = blueprint.get("project", {}).get("fact_table_name", "Fact_Flight")
        self.measure_owner: Dict[str, str] = {}
        self.public_custom_visuals: Set[str] = set()
        for m in blueprint.get("dax_measures", []):
            expr = m.get("expression", "")
            if "Fact_DelayCause" in expr and "Fact_Flight" not in expr:
                self.measure_owner[m["name"]] = "Fact_DelayCause"
            else:
                self.measure_owner[m["name"]] = self.fact_table

    def _alias_for(self, table_name: str, alias_map: Dict[str, str], from_list: List[Dict[str, Any]]) -> str:
        if table_name not in alias_map:
            alias = f"t{len(alias_map) + 1}"
            alias_map[table_name] = alias
            from_list.append({"Name": alias, "Entity": table_name, "Type": 0})
        return alias_map[table_name]

    def _add_field_to_query(
        self,
        table_name: str,
        field_name: str,
        is_measure: bool,
        alias_map: Dict[str, str],
        from_list: List[Dict[str, Any]],
        select_list: List[Dict[str, Any]],
        seen_refs: Set[str],
    ) -> Tuple[str, Dict[str, Any]]:
        actual_table = self.measure_owner.get(field_name, table_name) if is_measure else table_name
        q_ref = f"{actual_table}.{field_name}"
        alias = self._alias_for(actual_table, alias_map, from_list)
        expr_node: Dict[str, Any]
        if is_measure:
            expr_node = {
                "Measure": {
                    "Expression": {"SourceRef": {"Source": alias}},
                    "Property": field_name,
                }
            }
        else:
            expr_node = {
                "Column": {
                    "Expression": {"SourceRef": {"Source": alias}},
                    "Property": field_name,
                }
            }
        if q_ref not in seen_refs:
            seen_refs.add(q_ref)
            sel_item = dict(expr_node)
            sel_item["Name"] = q_ref
            sel_item["NativeReferenceName"] = field_name
            select_list.append(sel_item)
        return q_ref, expr_node

    def _extract_normalized_field_wells(self, vis_spec: Dict[str, Any], effective_vtype: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return normalized field_wells dict `{role_key: [{table, column|measure}, ...]}`.
        Prioritizes explicit `vis_spec["field_wells"]`, falling back cleanly to legacy keys.
        """
        if vis_spec.get("field_wells"):
            return {
                role_k: [item for item in items if item and (item.get("column") or item.get("measure"))]
                for role_k, items in vis_spec["field_wells"].items()
                if items
            }

        wells: Dict[str, List[Dict[str, Any]]] = {}

        if effective_vtype == "lineStackedColumnComboChart" or effective_vtype == "lineClusteredColumnComboChart":
            if vis_spec.get("category"):
                wells["Category"] = [vis_spec["category"]]
            if vis_spec.get("column_values"):
                wells["Y"] = list(vis_spec["column_values"])
            elif vis_spec.get("values"):
                wells["Y"] = list(vis_spec["values"])
            if vis_spec.get("line_values"):
                wells["Y2"] = list(vis_spec["line_values"])
            if vis_spec.get("series"):
                wells["Series"] = [vis_spec["series"]]

        elif effective_vtype == "scatterChart":
            if vis_spec.get("details"):
                wells["Category"] = [vis_spec["details"]]
            elif vis_spec.get("category"):
                wells["Category"] = [vis_spec["category"]]
            if vis_spec.get("x_axis"):
                wells["X"] = [vis_spec["x_axis"]]
            if vis_spec.get("y_axis"):
                wells["Y"] = [vis_spec["y_axis"]]
            if vis_spec.get("size"):
                wells["Size"] = [vis_spec["size"]]
            if vis_spec.get("series"):
                wells["Series"] = [vis_spec["series"]]
            if vis_spec.get("play_axis"):
                wells["Play"] = [vis_spec["play_axis"]]

        elif effective_vtype == "tableEx":
            if vis_spec.get("columns"):
                wells["Values"] = list(vis_spec["columns"])
            elif vis_spec.get("values"):
                wells["Values"] = list(vis_spec["values"])

        elif effective_vtype == "matrix":
            if vis_spec.get("rows"):
                wells["Rows"] = list(vis_spec["rows"])
            if vis_spec.get("columns"):
                wells["Columns"] = list(vis_spec["columns"])
            if vis_spec.get("values"):
                wells["Values"] = list(vis_spec["values"])

        elif effective_vtype == "treemap":
            if vis_spec.get("category"):
                wells["Group"] = [vis_spec["category"]]
            if vis_spec.get("series"):
                wells["Details"] = [vis_spec["series"]]
            if vis_spec.get("values"):
                wells["Values"] = list(vis_spec["values"])

        elif effective_vtype == "gauge":
            if vis_spec.get("values"):
                wells["Y"] = list(vis_spec["values"][:1])
            for rk, sk in [("MinValue", "min_value"), ("MaxValue", "max_value"), ("TargetValue", "target_value")]:
                if vis_spec.get(sk):
                    wells[rk] = [vis_spec[sk]]

        elif effective_vtype == "kpi":
            if vis_spec.get("values"):
                wells["Indicator"] = list(vis_spec["values"][:1])
            if vis_spec.get("category"):
                wells["TrendAxis"] = [vis_spec["category"]]
            if vis_spec.get("target_value"):
                wells["Goal"] = [vis_spec["target_value"]]

        elif effective_vtype == "cardVisual":
            if vis_spec.get("values"):
                wells["Data"] = list(vis_spec["values"])

        elif effective_vtype in ("card", "multiRowCard", "slicer", "advancedSlicerVisual", "listSlicer", "textSlicer", "pythonVisual", "scriptVisual", "qnaVisual", "aiNarratives", "paginatedReport"):
            items = []
            if vis_spec.get("category"):
                items.append(vis_spec["category"])
            if vis_spec.get("values"):
                items.extend(vis_spec["values"])
            if items:
                wells["Values"] = items

        elif effective_vtype in ("decompositionTreeVisual", "keyDriversVisual"):
            if vis_spec.get("values"):
                wells["Analyze"] = list(vis_spec["values"][:1])
            if vis_spec.get("explain_by"):
                wells["ExplainBy"] = list(vis_spec["explain_by"])
            elif vis_spec.get("category"):
                wells["ExplainBy"] = [vis_spec["category"]]

        else:
            if vis_spec.get("category"):
                wells["Category"] = [vis_spec["category"]]
            if vis_spec.get("series"):
                wells["Series"] = [vis_spec["series"]]
            if vis_spec.get("breakdown"):
                wells["Breakdown"] = [vis_spec["breakdown"]]
            if vis_spec.get("small_multiples"):
                wells["Rows"] = [vis_spec["small_multiples"]]
            if vis_spec.get("values"):
                wells["Y"] = list(vis_spec["values"])
            if vis_spec.get("secondary_values"):
                wells["Y2"] = list(vis_spec["secondary_values"])

        # Tooltips
        if vis_spec.get("tooltips"):
            tt_items = []
            for tt in vis_spec["tooltips"]:
                if isinstance(tt, str):
                    tt_items.append({"table": self.fact_table, "measure": tt})
                elif isinstance(tt, dict):
                    tt_items.append(tt)
            if tt_items:
                wells["Tooltips"] = tt_items

        return wells

    def _build_header_visual(self, page_id: str, title: str, subtitle: str, z: int) -> Dict[str, Any]:
        vc_name = f"Header_{page_id.replace('-', '_')}"
        config = {
            "name": vc_name,
            "layouts": [
                {"id": 0, "position": {"x": 16, "y": 8, "z": z, "width": 1248, "height": 46, "tabOrder": z}}
            ],
            "singleVisual": {
                "visualType": "textbox",
                "drillFilterOtherVisuals": True,
                "objects": {
                    "general": [
                        {
                            "properties": {
                                "paragraphs": [
                                    {"textRuns": [{"value": title, "textStyle": {"fontWeight": "bold", "fontFamily": "Segoe UI", "fontSize": "14pt", "color": "#FFFFFF"}}]},
                                    {"textRuns": [{"value": subtitle, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "9pt", "color": "#CBD5E1"}}]},
                                ]
                            }
                        }
                    ]
                },
                "vcObjects": {
                    "background": [{"properties": {"show": _lit_bool(True), "color": _lit_color("#0F172A"), "transparency": _lit_num(0)}}],
                    "border": [{"properties": {"show": _lit_bool(True), "color": _lit_color("#1E293B"), "radius": _lit_num(6)}}],
                },
            },
        }
        return {"x": 16, "y": 8, "z": z, "width": 1248, "height": 46, "config": json.dumps(config, ensure_ascii=False), "filters": "[]", "tabOrder": z}

    def _build_slicer_visual(self, slicer_spec: Dict[str, Any], x: int, y: int, w: int, h: int, z: int) -> Dict[str, Any]:
        alias_map: Dict[str, str] = {}
        from_list: List[Dict[str, Any]] = []
        select_list: List[Dict[str, Any]] = []
        seen_refs: Set[str] = set()

        q_ref, _ = self._add_field_to_query(
            slicer_spec["table"], slicer_spec["column"], False, alias_map, from_list, select_list, seen_refs
        )
        mode = slicer_spec.get("mode", "Dropdown")
        slicer_vtype = slicer_spec.get("visual_type", "slicer")
        if slicer_vtype not in ("slicer", "advancedSlicerVisual", "listSlicer", "textSlicer"):
            slicer_vtype = "slicer"

        objects: Dict[str, Any] = {
            "header": [{"properties": {"show": _lit_bool(True), "text": _lit_str(slicer_spec["title"])}}]
        }
        if slicer_vtype == "slicer":
            objects["data"] = [{"properties": {"mode": _lit_str(mode)}}]

        config: Dict[str, Any] = {
            "name": slicer_spec["id"],
            "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
            "singleVisual": {
                "visualType": slicer_vtype,
                "projections": {"Values": [{"queryRef": q_ref, "active": True}]},
                "prototypeQuery": {"Version": 2, "From": from_list, "Select": select_list},
                "drillFilterOtherVisuals": True,
                "objects": objects,
                "vcObjects": {
                    "background": [{"properties": {"show": _lit_bool(True), "color": _lit_color("#F8FAFC")}}],
                    "border": [{"properties": {"show": _lit_bool(True), "color": _lit_color("#CBD5E1"), "radius": _lit_num(4)}}],
                },
            },
        }
        sync_group = slicer_spec.get("sync_group", "")
        if sync_group:
            config["syncGroup"] = {"groupName": sync_group, "fieldChanges": True, "filterChanges": True}
        return {"x": x, "y": y, "z": z, "width": w, "height": h, "config": json.dumps(config, ensure_ascii=False), "filters": "[]", "tabOrder": z}

    def _build_kpi_card_visual(self, kpi_spec: Dict[str, Any], x: int, y: int, w: int, h: int, z: int) -> Dict[str, Any]:
        alias_map: Dict[str, str] = {}
        from_list: List[Dict[str, Any]] = []
        select_list: List[Dict[str, Any]] = []
        seen_refs: Set[str] = set()

        measure_name = kpi_spec["measure"]
        q_ref, _ = self._add_field_to_query(self.fact_table, measure_name, True, alias_map, from_list, select_list, seen_refs)
        card_vtype = kpi_spec.get("visual_type", "card")
        proj_key = "Data" if card_vtype == "cardVisual" else "Values"

        config = {
            "name": kpi_spec["id"],
            "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
            "singleVisual": {
                "visualType": card_vtype,
                "projections": {proj_key: [{"queryRef": q_ref}]},
                "prototypeQuery": {"Version": 2, "From": from_list, "Select": select_list},
                "drillFilterOtherVisuals": True,
                "objects": {
                    "categoryLabels": [{"properties": {"show": _lit_bool(False)}}],
                    "labels": [{"properties": {"fontSize": _lit_num(18), "color": _lit_color("#0F172A")}}],
                },
                "vcObjects": {
                    "title": [{"properties": {"show": _lit_bool(True), "text": _lit_str(kpi_spec["title"]), "fontSize": _lit_num(10), "fontColor": _lit_color("#334155"), "alignment": _lit_str("center")}}],
                    "background": [{"properties": {"show": _lit_bool(True), "color": _lit_color("#FFFFFF")}}],
                    "border": [{"properties": {"show": _lit_bool(True), "color": _lit_color("#94A3B8"), "radius": _lit_num(6)}}],
                },
            },
        }
        return {"x": x, "y": y, "z": z, "width": w, "height": h, "config": json.dumps(config, ensure_ascii=False), "filters": "[]", "tabOrder": z}

    def _build_top_n_filter(self, cat_item: Dict[str, Any], val_item: Dict[str, Any], top_n: int, direction: str = "Top") -> List[Dict[str, Any]]:
        """Build a native Power BI TopN visual-level filter JSON structure."""
        c_tbl = cat_item["table"]
        c_col = cat_item.get("column")
        v_is_m = "measure" in val_item
        v_fname = val_item.get("measure") or val_item.get("column")
        v_tbl = self.measure_owner.get(v_fname, val_item["table"]) if v_is_m else val_item["table"]
        if not c_col or not v_fname:
            return []

        sub_from: List[Dict[str, Any]] = [{"Name": "c", "Entity": c_tbl, "Type": 0}]
        if v_tbl == c_tbl:
            v_alias = "c"
        else:
            v_alias = "v"
            sub_from.append({"Name": "v", "Entity": v_tbl, "Type": 0})

        order_expr = (
            {"Measure": {"Expression": {"SourceRef": {"Source": v_alias}}, "Property": v_fname}}
            if v_is_m
            else {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Source": v_alias}}, "Property": v_fname}}, "Function": 0}}
        )
        pbi_dir = 2 if direction.lower() == "top" else 1
        return [
            {
                "name": f"TopNFilter_{c_col}",
                "expression": {"Column": {"Expression": {"SourceRef": {"Entity": c_tbl}}, "Property": c_col}},
                "filter": {
                    "Version": 2,
                    "From": [
                        {"Name": "sub", "Expression": {"Subquery": {"Query": {
                            "Version": 2,
                            "From": sub_from,
                            "Select": [{"Column": {"Expression": {"SourceRef": {"Source": "c"}}, "Property": c_col}, "Name": "field"}],
                            "OrderBy": [{"Direction": pbi_dir, "Expression": order_expr}],
                            "Top": int(top_n),
                        }}}, "Type": 2},
                        {"Name": "c", "Entity": c_tbl, "Type": 0},
                    ],
                    "Where": [
                        {
                            "Condition": {
                                "In": {
                                    "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "c"}}, "Property": c_col}}],
                                    "Table": {"SourceRef": {"Source": "sub"}},
                                }
                            }
                        }
                    ],
                },
                "type": "TopN",
                "howCreated": 0,
            }
        ]

    def _build_chart_visual(self, vis_spec: Dict[str, Any], z: int) -> Dict[str, Any]:
        requested_vtype = vis_spec.get("type", "clusteredBarChart")
        cat_meta = get_visual_spec_by_type(requested_vtype, self.workspace_dir)
        fmt = vis_spec.get("format") or {}

        # Determine effective Power BI visualType (Built-in vs Native AppSource vs Fallback)
        is_custom_source = cat_meta["source"] in ("appsource_microsoft", "appsource_custom", "imported_pbiviz")
        use_appsource_native = bool(vis_spec.get("use_appsource_native", cat_meta["source"] == "imported_pbiviz"))
        if is_custom_source and not use_appsource_native:
            effective_vtype = cat_meta.get("fallback_builtin") or "clusteredBarChart"
        else:
            effective_vtype = cat_meta["visualType"]
            if is_custom_source:
                self.public_custom_visuals.add(effective_vtype)

        x, y, w, h = int(vis_spec["x"]), int(vis_spec["y"]), int(vis_spec["w"]), int(vis_spec["h"])
        vc_name = vis_spec["id"].replace("-", "_")

        # Special UI layout elements: textbox, actionButton, shape
        if effective_vtype == "textbox":
            txt_val = fmt.get("text_content") or vis_spec.get("title", "Text Box")
            txt_sub = fmt.get("subtitle_content") or ""
            paragraphs = [{"textRuns": [{"value": txt_val, "textStyle": {"fontWeight": "bold", "fontFamily": "Segoe UI", "fontSize": f"{fmt.get('title_font_size', 13)}pt", "color": fmt.get("title_color", "#0F172A")}}]}]
            if txt_sub:
                paragraphs.append({"textRuns": [{"value": txt_sub, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": "#475569"}}]})
            config = {
                "name": vc_name,
                "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
                "singleVisual": {
                    "visualType": "textbox",
                    "drillFilterOtherVisuals": True,
                    "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
                    "vcObjects": {
                        "background": [{"properties": {"show": _lit_bool(True), "color": _lit_color(fmt.get("bg_color", "#FFFFFF"))}}],
                        "border": [{"properties": {"show": _lit_bool(fmt.get("border_show", True)), "color": _lit_color(fmt.get("border_color", "#CBD5E1")), "radius": _lit_num(fmt.get("border_radius", 6))}}],
                    },
                },
            }
            return {"x": x, "y": y, "z": z, "width": w, "height": h, "config": json.dumps(config, ensure_ascii=False), "filters": "[]", "tabOrder": z}

        if effective_vtype == "actionButton":
            btn_text = fmt.get("button_text") or vis_spec.get("title", "Reset Filters")
            config = {
                "name": vc_name,
                "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
                "singleVisual": {
                    "visualType": "actionButton",
                    "drillFilterOtherVisuals": True,
                    "objects": {
                        "text": [{"properties": {"show": _lit_bool(True), "text": _lit_str(btn_text), "fontColor": _lit_color(fmt.get("title_color", "#FFFFFF"))}}],
                        "fill": [{"properties": {"show": _lit_bool(True), "fillColor": _lit_color(fmt.get("bg_color", "#1D4ED8"))}}],
                        "outline": [{"properties": {"show": _lit_bool(True), "lineColor": _lit_color("#1E40AF")}}],
                    },
                },
            }
            return {"x": x, "y": y, "z": z, "width": w, "height": h, "config": json.dumps(config, ensure_ascii=False), "filters": "[]", "tabOrder": z}

        if effective_vtype == "shape":
            config = {
                "name": vc_name,
                "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
                "singleVisual": {
                    "visualType": "shape",
                    "drillFilterOtherVisuals": True,
                    "objects": {
                        "shape": [{"properties": {"tileShape": _lit_str(fmt.get("shape_type", "rectangle")), "roundEdge": _lit_num(fmt.get("border_radius", 8))}}],
                        "fill": [{"properties": {"show": _lit_bool(True), "fillColor": _lit_color(fmt.get("bg_color", "#F8FAFC"))}}],
                        "outline": [{"properties": {"show": _lit_bool(True), "lineColor": _lit_color(fmt.get("border_color", "#CBD5E1"))}}],
                    },
                },
            }
            return {"x": x, "y": y, "z": z, "width": w, "height": h, "config": json.dumps(config, ensure_ascii=False), "filters": "[]", "tabOrder": z}

        # Standard & Custom Data Visuals: build projections & prototypeQuery dynamically from field_wells!
        wells = self._extract_normalized_field_wells(vis_spec, effective_vtype)
        # If falling back from an AppSource visual whose custom roles differ from built-in roles, remap gracefully
        if is_custom_source and not use_appsource_native:
            wells = self._remap_custom_wells_to_builtin(wells, effective_vtype)

        alias_map: Dict[str, str] = {}
        from_list: List[Dict[str, Any]] = []
        select_list: List[Dict[str, Any]] = []
        seen_refs: Set[str] = set()
        projections: Dict[str, List[Dict[str, Any]]] = {}
        expr_by_qref: Dict[str, Dict[str, Any]] = {}

        # Role active metadata lookup
        eff_meta = get_visual_spec_by_type(effective_vtype, self.workspace_dir)
        active_roles = {r["key"] for r in eff_meta.get("roles", []) if r.get("active")}

        first_cat_item = None
        first_val_item = None

        for role_key, field_items in wells.items():
            proj_items = []
            for item in field_items:
                is_m = "measure" in item and bool(item.get("measure"))
                fname = item.get("measure") if is_m else item.get("column")
                if not fname:
                    continue
                tbl = item.get("table") or self.fact_table
                q_ref, expr_node = self._add_field_to_query(tbl, fname, is_m, alias_map, from_list, select_list, seen_refs)
                expr_by_qref[q_ref] = expr_node
                p_entry: Dict[str, Any] = {"queryRef": q_ref}
                if role_key in active_roles and not is_m:
                    p_entry["active"] = True
                proj_items.append(p_entry)

                if not is_m and first_cat_item is None and role_key in ("Category", "Group", "Rows", "Location"):
                    first_cat_item = item
                if is_m and first_val_item is None and role_key in ("Y", "Values", "Data", "Analyze", "Indicator"):
                    first_val_item = item

            if proj_items:
                projections[role_key] = proj_items

        prototype_query: Dict[str, Any] = {
            "Version": 2,
            "From": from_list,
            "Select": select_list,
        }

        # Sorting (OrderBy)
        sort_field = fmt.get("sort_field")
        sort_dir = fmt.get("sort_direction", "Descending")
        if sort_field:
            matched_ref = next((qr for qr in expr_by_qref if qr.endswith(f".{sort_field}") or qr == sort_field), None)
            if matched_ref:
                prototype_query["OrderBy"] = [
                    {"Direction": 2 if str(sort_dir).lower().startswith("desc") else 1, "Expression": expr_by_qref[matched_ref]}
                ]

        # Build Visual `objects` (Legend, Data Labels, Axes, Constant Line, Python/R Script)
        objects: Dict[str, Any] = {}
        if "legend_show" in fmt or "legend_position" in fmt:
            leg_props: Dict[str, Any] = {}
            if "legend_show" in fmt:
                leg_props["show"] = _lit_bool(bool(fmt["legend_show"]))
            if fmt.get("legend_position"):
                leg_props["position"] = _lit_str(fmt["legend_position"])
            objects["legend"] = [{"properties": leg_props}]

        if "data_labels_show" in fmt:
            objects["labels"] = [{"properties": {"show": _lit_bool(bool(fmt["data_labels_show"]))}}]

        if "x_axis_show" in fmt:
            objects["categoryAxis"] = [{"properties": {"show": _lit_bool(bool(fmt["x_axis_show"]))}}]

        if "y_axis_show" in fmt:
            objects["valueAxis"] = [{"properties": {"show": _lit_bool(bool(fmt["y_axis_show"]))}}]

        if fmt.get("constant_line_value") not in (None, ""):
            try:
                cval = float(fmt["constant_line_value"])
                objects["y1AxisReferenceLine"] = [
                    {
                        "properties": {
                            "show": _lit_bool(True),
                            "displayName": _lit_str(fmt.get("constant_line_label") or f"Target ({cval})"),
                            "value": _lit_num(cval),
                            "lineColor": _lit_color(fmt.get("constant_line_color") or "#EF4444"),
                            "style": _lit_str("dashed"),
                        },
                        "selector": {"id": "target_line_1"},
                    }
                ]
            except (TypeError, ValueError):
                pass

        # Python / R Script Visual Source Code
        if effective_vtype == "pythonVisual":
            py_code = vis_spec.get("script_code") or (
                "# Auto-generated Power BI Python Visual (Matplotlib)\n"
                "import matplotlib.pyplot as plt\n"
                "dataset.plot(kind='bar')\n"
                "plt.tight_layout()\n"
                "plt.show()\n"
            )
            objects["script"] = [{"properties": {"source": _lit_str(py_code), "provider": _lit_str("Python")}}]
        elif effective_vtype == "scriptVisual":
            r_code = vis_spec.get("script_code") or (
                "# Auto-generated Power BI R Script Visual\n"
                "barplot(dataset[[2]], names.arg=dataset[[1]], col='#1D4ED8')\n"
            )
            objects["script"] = [{"properties": {"source": _lit_str(r_code), "provider": _lit_str("R")}}]

        # Build Visual Container `vcObjects` (Title, Background, Border)
        title_show = fmt.get("title_show", True)
        title_text = vis_spec.get("title", vc_name)
        vc_objects = {
            "title": [
                {
                    "properties": {
                        "show": _lit_bool(bool(title_show)),
                        "text": _lit_str(title_text),
                        "fontSize": _lit_num(float(fmt.get("title_font_size", 10))),
                        "fontColor": _lit_color(fmt.get("title_color", "#0F172A")),
                        "background": _lit_color(fmt.get("title_bg", "#F1F5F9")),
                        "alignment": _lit_str(fmt.get("title_align", "left")),
                    }
                }
            ],
            "background": [
                {"properties": {"show": _lit_bool(True), "color": _lit_color(fmt.get("bg_color", "#FFFFFF"))}}
            ],
            "border": [
                {
                    "properties": {
                        "show": _lit_bool(bool(fmt.get("border_show", True))),
                        "color": _lit_color(fmt.get("border_color", "#CBD5E1")),
                        "radius": _lit_num(float(fmt.get("border_radius", 6))),
                    }
                }
            ],
        }

        single_visual: Dict[str, Any] = {
            "visualType": effective_vtype,
            "projections": projections,
            "prototypeQuery": prototype_query,
            "drillFilterOtherVisuals": True,
            "vcObjects": vc_objects,
        }
        if objects:
            single_visual["objects"] = objects

        config = {
            "name": vc_name,
            "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
            "singleVisual": single_visual,
        }

        # Top N visual-level filter if configured
        visual_filters: List[Dict[str, Any]] = []
        top_n_val = fmt.get("top_n")
        if top_n_val and int(top_n_val) > 0 and first_cat_item and first_val_item:
            visual_filters = self._build_top_n_filter(
                first_cat_item, first_val_item, int(top_n_val), fmt.get("top_n_direction", "Top")
            )

        return {
            "x": x,
            "y": y,
            "z": z,
            "width": w,
            "height": h,
            "config": json.dumps(config, ensure_ascii=False),
            "filters": json.dumps(visual_filters, ensure_ascii=False),
            "tabOrder": z,
        }

    def _remap_custom_wells_to_builtin(
        self, wells: Dict[str, List[Dict[str, Any]]], fallback_vtype: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Gracefully remap AppSource custom role keys (e.g., Source/Destination/Weight) to built-in fallback roles."""
        cols = []
        measures = []
        tooltips = wells.get("Tooltips", [])
        for rk, items in wells.items():
            if rk == "Tooltips":
                continue
            for it in items:
                if it.get("measure"):
                    measures.append(it)
                elif it.get("column"):
                    cols.append(it)

        mapped: Dict[str, List[Dict[str, Any]]] = {}
        if fallback_vtype == "matrix":
            if cols:
                mapped["Rows"] = [cols[0]]
            if len(cols) > 1:
                mapped["Columns"] = [cols[1]]
            if measures:
                mapped["Values"] = measures
        elif fallback_vtype == "treemap":
            if cols:
                mapped["Group"] = [cols[0]]
            if len(cols) > 1:
                mapped["Details"] = [cols[1]]
            if measures:
                mapped["Values"] = measures[:1]
        elif fallback_vtype == "scatterChart":
            if cols:
                mapped["Category"] = [cols[0]]
            if measures:
                mapped["X"] = [measures[0]]
            if len(measures) > 1:
                mapped["Y"] = [measures[1]]
            elif measures:
                mapped["Y"] = [measures[0]]
        elif fallback_vtype in ("slicer", "advancedSlicerVisual", "textSlicer"):
            if cols:
                mapped["Values"] = [cols[0]]
        else:
            if cols:
                mapped["Category"] = [cols[0]]
            if len(cols) > 1:
                mapped["Series"] = [cols[1]]
            if measures:
                mapped["Y"] = measures
        if tooltips:
            mapped["Tooltips"] = tooltips
        return mapped

    def build_report_json(self) -> Dict[str, Any]:
        sections: List[Dict[str, Any]] = []
        canvas_w = int(self.blueprint["project"]["canvas"].get("width", 1280))
        canvas_h = int(self.blueprint["project"]["canvas"].get("height", 720))

        for page_idx, dash in enumerate(self.blueprint.get("dashboards", [])):
            vcs: List[Dict[str, Any]] = []
            z_counter = 100

            # 1. Header Banner (y=8..54)
            vcs.append(self._build_header_visual(dash["id"], dash["title"], dash.get("subtitle", ""), z_counter))
            z_counter += 100

            # 2. Slicers Bar (y=58, h=64)
            slicers = dash.get("slicers", [])
            if slicers:
                n_slicers = len(slicers)
                gap = 8
                total_w = 1248
                s_w = (total_w - gap * (n_slicers - 1)) // n_slicers
                for s_idx, s_spec in enumerate(slicers):
                    s_x = 16 + s_idx * (s_w + gap)
                    vcs.append(self._build_slicer_visual(s_spec, s_x, 58, s_w, 64, z_counter))
                    z_counter += 100

            # 3. KPI Cards Row (y=128, h=76)
            kpis = dash.get("kpis", [])
            if kpis:
                n_kpis = len(kpis)
                gap = 8
                total_w = 1248
                k_w = (total_w - gap * (n_kpis - 1)) // n_kpis
                for k_idx, k_spec in enumerate(kpis):
                    k_x = 16 + k_idx * (k_w + gap)
                    vcs.append(self._build_kpi_card_visual(k_spec, k_x, 128, k_w, 76, z_counter))
                    z_counter += 100

            # 4. Main & Diagnostic Visuals
            for v_spec in dash.get("visuals", []):
                vcs.append(self._build_chart_visual(v_spec, z_counter))
                z_counter += 100

            sections.append({
                "name": f"ReportSection{page_idx + 1}",
                "displayName": dash["name"],
                "filters": "[]",
                "ordinal": page_idx,
                "visualContainers": vcs,
                "config": json.dumps({"relationships": []}, ensure_ascii=False),
                "displayOption": 1,
                "width": canvas_w,
                "height": canvas_h,
            })

        report_config = {
            "version": "5.53",
            "themeCollection": {"baseTheme": {"name": "CY24SU06", "version": "5.53", "type": 2}},
            "activeSectionIndex": 0,
            "defaultDrillFilterOtherVisuals": True,
            "linguisticSchemaSyncVersion": 2,
            "settings": {
                "useNewFilterPaneExperience": True,
                "allowChangeFilterTypes": True,
                "useStylableVisualContainerHeader": True,
                "queryLimitOption": 6,
                "exportDataMode": 1,
                "useDefaultAggregateDisplayName": True,
            },
        }

        report_obj: Dict[str, Any] = {
            "config": json.dumps(report_config, ensure_ascii=False),
            "layoutOptimization": 0,
            "resourcePackages": [
                {
                    "resourcePackage": {
                        "disabled": False,
                        "items": [{"name": "CY24SU06", "path": "BaseThemes/CY24SU06.json", "type": 202}],
                        "name": "SharedResources",
                        "type": 2,
                    }
                }
            ],
            "sections": sections,
        }
        if self.public_custom_visuals:
            report_obj["publicCustomVisuals"] = sorted(self.public_custom_visuals)
        return report_obj
