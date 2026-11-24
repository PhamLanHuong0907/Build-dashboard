"""
Comprehensive Power BI Visualization Catalog (Built-in + Microsoft Samples + AppSource Custom Visuals).
Sources:
1. Microsoft Learn: Visualization types in Power BI (power-bi-visualization-types-for-reports-and-q-and-a)
2. Microsoft AppSource: Power BI Visuals Marketplace
3. Microsoft Learn: Developer Custom Visual Samples (developer/visuals/samples)

Includes:
- 44 Built-in Power BI Desktop visual types with EXACT `report.json` `visualType` IDs and `projections` role keys
- 22 Popular Microsoft Official & AppSource Custom Visuals with their data roles, AppSource references, and fallback built-in mappings
- Full `.pbiviz` package importer that inspects `package.json` / `pbiviz.json` / `capabilities.json` to dynamically register ANY AppSource `.pbiviz` visual!
"""
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def _role(
    key: str,
    label: str,
    kind: str = "any",
    multi: bool = False,
    required: bool = False,
    active_by_default: bool = False,
    hint: str = "",
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": kind,  # "column", "measure", "any"
        "multi": multi,
        "required": required,
        "active": active_by_default,
        "hint": hint,
    }


def _vis(
    vtype: str,
    name: str,
    name_vi: str,
    category: str,
    source: str,
    icon: str,
    description: str,
    roles: List[Dict[str, Any]],
    keywords: List[str],
    supports_legend: bool = True,
    supports_data_labels: bool = True,
    supports_axes: bool = True,
    supports_constant_line: bool = False,
    supports_top_n: bool = True,
    supports_script: str = "",
    appsource_url: str = "",
    fallback_builtin: str = "",
) -> Dict[str, Any]:
    return {
        "visualType": vtype,
        "name": name,
        "name_vi": name_vi,
        "category": category,
        "source": source,  # "builtin" | "appsource_microsoft" | "appsource_custom" | "imported_pbiviz"
        "icon": icon,
        "description": description,
        "roles": roles,
        "keywords": keywords,
        "capabilities": {
            "legend": supports_legend,
            "data_labels": supports_data_labels,
            "axes": supports_axes,
            "constant_line": supports_constant_line,
            "top_n": supports_top_n,
            "script": supports_script,  # "" | "python" | "r"
        },
        "appsource_url": appsource_url,
        "fallback_builtin": fallback_builtin or vtype,
    }


# Reusable standard Cartesian roles (matching Power BI Desktop's Visualizations Pane 1-to-1)
CARTESIAN_BAR_ROLES = [
    _role("Category", "Y-axis (Trục danh mục)", "column", multi=True, required=True, active_by_default=True, hint="Chọn 1 hoặc nhiều cột để hỗ trợ Drill-down"),
    _role("Y", "X-axis (Giá trị / Measures)", "measure", multi=True, required=True, hint="Chọn 1 hoặc nhiều DAX Measure"),
    _role("Series", "Legend (Phân tách màu theo nhóm)", "column", multi=False, required=False, hint="Chỉ dùng khi có 1 Measure hoặc muốn chia nhóm màu"),
    _role("Rows", "Small multiples (Chia lưới biểu đồ con)", "column", multi=False, required=False, hint="Tách thành nhiều biểu đồ nhỏ theo từng chiều"),
    _role("Tooltips", "Tooltips (Thông tin bổ sung khi di chuột)", "any", multi=True, required=False, hint="Hiển thị thêm chỉ số phụ khi rê chuột"),
]

CARTESIAN_COL_ROLES = [
    _role("Category", "X-axis (Trục danh mục / Thời gian)", "column", multi=True, required=True, active_by_default=True, hint="Chọn 1 hoặc nhiều cột để hỗ trợ Drill-down"),
    _role("Y", "Y-axis (Giá trị / Measures)", "measure", multi=True, required=True, hint="Chọn 1 hoặc nhiều DAX Measure"),
    _role("Series", "Legend (Phân tách màu theo nhóm)", "column", multi=False, required=False, hint="Chia chuỗi dữ liệu theo cột phân loại"),
    _role("Rows", "Small multiples (Chia lưới biểu đồ con)", "column", multi=False, required=False, hint="Tách thành nhiều biểu đồ nhỏ"),
    _role("Tooltips", "Tooltips (Thông tin khi di chuột)", "any", multi=True, required=False),
]

LINE_AREA_ROLES = [
    _role("Category", "X-axis (Trục thời gian / Danh mục)", "column", multi=True, required=True, active_by_default=True, hint="Thường dùng Date, MonthName, DepHour..."),
    _role("Y", "Y-axis (Giá trị trục tung chính)", "measure", multi=True, required=True, hint="Chọn 1 hoặc nhiều DAX Measure"),
    _role("Y2", "Secondary y-axis (Trục tung phụ bên phải)", "measure", multi=True, required=False, hint="Dùng khi so sánh 2 chỉ số khác đơn vị (VD: Count & %)"),
    _role("Series", "Legend (Chuỗi đường theo nhóm)", "column", multi=False, required=False),
    _role("Rows", "Small multiples (Lưới biểu đồ con)", "column", multi=False, required=False),
    _role("Tooltips", "Tooltips (Thông tin bổ sung)", "any", multi=True, required=False),
]

COMBO_ROLES = [
    _role("Category", "X-axis (Trục chung)", "column", multi=True, required=True, active_by_default=True),
    _role("Y", "Column y-axis (Giá trị Cột)", "measure", multi=True, required=True),
    _role("Y2", "Line y-axis (Giá trị Đường)", "measure", multi=True, required=True),
    _role("Series", "Column legend (Phân nhóm Cột)", "column", multi=False, required=False),
    _role("Rows", "Small multiples (Lưới biểu đồ con)", "column", multi=False, required=False),
    _role("Tooltips", "Tooltips", "any", multi=True, required=False),
]

PIE_DONUT_ROLES = [
    _role("Category", "Legend (Nhóm phân loại chính)", "column", multi=True, required=True, active_by_default=True),
    _role("Details", "Details (Chi tiết phân rã nhỏ hơn)", "column", multi=False, required=False),
    _role("Y", "Values (Giá trị / Tỷ trọng)", "measure", multi=False, required=True),
    _role("Tooltips", "Tooltips", "any", multi=True, required=False),
]


POWERBI_VISUAL_CATALOG: List[Dict[str, Any]] = [
    # =========================================================================
    # 1. BAR & COLUMN CHARTS (7 Built-in)
    # =========================================================================
    _vis(
        "barChart", "Stacked bar chart", "Biểu đồ thanh ngang chồng",
        "01. Bar & Column Charts", "builtin", "📊",
        "So sánh tổng giá trị và thành phần đóng góp theo chiều ngang giữa các nhóm.",
        CARTESIAN_BAR_ROLES, ["stacked bar", "horizontal stacked bar", "thanh ngang chồng"],
        supports_constant_line=True,
    ),
    _vis(
        "columnChart", "Stacked column chart", "Biểu đồ cột đứng chồng",
        "01. Bar & Column Charts", "builtin", "📊",
        "So sánh tổng và cơ cấu thành phần theo chiều dọc qua thời gian hoặc danh mục.",
        CARTESIAN_COL_ROLES, ["stacked column", "cột chồng"],
        supports_constant_line=True,
    ),
    _vis(
        "clusteredBarChart", "Clustered bar chart", "Biểu đồ thanh ngang nhóm",
        "01. Bar & Column Charts", "builtin", "📊",
        "Xếp hạng đối tượng (Top N) hoặc so sánh nhiều chỉ số theo thanh ngang.",
        CARTESIAN_BAR_ROLES, ["clustered bar", "horizontal bar", "diverging bar", "bar chart", "thanh ngang"],
        supports_constant_line=True,
    ),
    _vis(
        "clusteredColumnChart", "Clustered column chart", "Biểu đồ cột đứng nhóm",
        "01. Bar & Column Charts", "builtin", "📊",
        "So sánh trực tiếp các giá trị hoặc nhiều chỉ số cạnh nhau theo chiều dọc.",
        CARTESIAN_COL_ROLES, ["clustered column", "column chart", "cột đứng", "cột nhóm"],
        supports_constant_line=True,
    ),
    _vis(
        "hundredPercentStackedBarChart", "100% Stacked bar chart", "Biểu đồ thanh ngang chồng 100%",
        "01. Bar & Column Charts", "builtin", "▤",
        "So sánh tỷ trọng phần trăm (tổng 100%) giữa các nhóm theo thanh ngang.",
        CARTESIAN_BAR_ROLES, ["100% stacked bar", "chồng 100% ngang"],
    ),
    _vis(
        "hundredPercentStackedColumnChart", "100% Stacked column chart", "Biểu đồ cột đứng chồng 100%",
        "01. Bar & Column Charts", "builtin", "▥",
        "So sánh tỷ trọng phần trăm (tổng 100%) giữa các giai đoạn hoặc nhóm theo cột đứng.",
        CARTESIAN_COL_ROLES, ["100% stacked column", "chồng 100% dọc"],
    ),
    _vis(
        "ribbonChart", "Ribbon chart", "Biểu đồ dải ruy-băng (Xếp hạng biến động)",
        "01. Bar & Column Charts", "builtin", "🎀",
        "Theo dõi sự thay đổi thứ hạng (Rank) của các danh mục qua từng giai đoạn thời gian.",
        [
            _role("Category", "X-axis (Thời gian / Giai đoạn)", "column", multi=True, required=True, active_by_default=True),
            _role("Series", "Legend (Đối tượng xếp hạng)", "column", multi=False, required=True),
            _role("Y", "Y-axis (Chỉ số xếp hạng)", "measure", multi=False, required=True),
            _role("Rows", "Small multiples", "column", multi=False, required=False),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["ribbon", "ribbon chart", "ruy băng", "xếp hạng theo thời gian"],
    ),

    # =========================================================================
    # 2. LINE, AREA & COMBO CHARTS (6 Built-in)
    # =========================================================================
    _vis(
        "lineChart", "Line chart", "Biểu đồ đường (Xu hướng)",
        "02. Line, Area & Combo Charts", "builtin", "📈",
        "Theo dõi xu hướng biến động liên tục theo thời gian, hỗ trợ trục Y phụ và đường mục tiêu.",
        LINE_AREA_ROLES, ["line", "line chart", "biểu đồ đường", "xu hướng"],
        supports_constant_line=True,
    ),
    _vis(
        "areaChart", "Area chart", "Biểu đồ miền (Area)",
        "02. Line, Area & Combo Charts", "builtin", "🏔️",
        "Nhấn mạnh độ lớn thay đổi theo thời gian bằng vùng tô màu dưới đường xu hướng.",
        LINE_AREA_ROLES, ["area", "area chart", "biểu đồ miền"],
        supports_constant_line=True,
    ),
    _vis(
        "stackedAreaChart", "Stacked area chart", "Biểu đồ miền chồng",
        "02. Line, Area & Combo Charts", "builtin", "⛰️",
        "Hiển thị tổng cộng dồn và sự đóng góp của từng nhóm thành phần theo thời gian.",
        CARTESIAN_COL_ROLES, ["stacked area", "miền chồng"],
        supports_constant_line=True,
    ),
    _vis(
        "hundredPercentStackedAreaChart", "100% Stacked area chart", "Biểu đồ miền chồng 100%",
        "02. Line, Area & Combo Charts", "builtin", "📐",
        "Theo dõi sự dịch chuyển tỷ trọng phần trăm (tổng 100%) của các thành phần qua thời gian.",
        CARTESIAN_COL_ROLES, ["100% stacked area", "miền chồng 100%"],
    ),
    _vis(
        "lineStackedColumnComboChart", "Line and stacked column chart", "Biểu đồ kết hợp Đường & Cột chồng",
        "02. Line, Area & Combo Charts", "builtin", "📉",
        "Kết hợp cột chồng (số lượng/cơ cấu) và đường xu hướng (tỷ lệ %) trên hai trục tung.",
        COMBO_ROLES, ["line and stacked column", "line and column", "combo", "cột chồng và đường"],
        supports_constant_line=True,
    ),
    _vis(
        "lineClusteredColumnComboChart", "Line and clustered column chart", "Biểu đồ kết hợp Đường & Cột nhóm",
        "02. Line, Area & Combo Charts", "builtin", "📉",
        "Kết hợp cột đứng nhóm và đường xu hướng để đối chiếu quy mô với tỷ lệ (VD: Flights vs OTP %).",
        COMBO_ROLES, ["line and clustered column", "cột nhóm và đường"],
        supports_constant_line=True,
    ),

    # =========================================================================
    # 3. WATERFALL, FUNNEL & SCATTER CHARTS (3 Built-in)
    # =========================================================================
    _vis(
        "waterfallChart", "Waterfall chart", "Biểu đồ thác nước (Biến động tăng/giảm)",
        "03. Waterfall, Funnel & Scatter", "builtin", "🌊",
        "Hiển thị tổng cộng dồn khi các yếu tố tăng (xanh) hoặc giảm (đỏ) tác động lên kết quả cuối cùng.",
        [
            _role("Category", "Category (Trục chính)", "column", multi=True, required=True, active_by_default=True),
            _role("Breakdown", "Breakdown (Phân rã nguyên nhân tăng/giảm)", "column", multi=False, required=False),
            _role("Y", "Y-axis (Giá trị biến động)", "measure", multi=False, required=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["waterfall", "waterfall chart", "thác nước", "bridge chart"],
    ),
    _vis(
        "funnel", "Funnel chart", "Biểu đồ phễu (Chuyển đổi giai đoạn)",
        "03. Waterfall, Funnel & Scatter", "builtin", "🔻",
        "Mô tả quy trình nhiều bước tuần tự và tỷ lệ chuyển đổi/rơi rụng giữa các bước.",
        [
            _role("Category", "Category (Các bước / Giai đoạn)", "column", multi=False, required=True, active_by_default=True),
            _role("Y", "Values (Số lượng từng bước)", "measure", multi=False, required=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["funnel", "funnel chart", "phễu"],
        supports_legend=False,
    ),
    _vis(
        "scatterChart", "Scatter / Bubble / Dot Plot chart", "Biểu đồ phân tán & Bong bóng (Scatter)",
        "03. Waterfall, Funnel & Scatter", "builtin", "🫧",
        "Phân tích tương quan giữa 2-3 biến số (X, Y, Kích thước bong bóng) và hoạt ảnh theo trục Play Axis.",
        [
            _role("Category", "Values / Details (Điểm dữ liệu)", "column", multi=False, required=True, active_by_default=True, hint="Mỗi giá trị sẽ là 1 điểm/bong bóng (VD: Airline, Route)"),
            _role("X", "X-axis (Chỉ số trục hoành)", "measure", multi=False, required=True),
            _role("Y", "Y-axis (Chỉ số trục tung)", "measure", multi=False, required=True),
            _role("Series", "Legend (Phân màu điểm)", "column", multi=False, required=False),
            _role("Size", "Size (Kích thước bong bóng)", "measure", multi=False, required=False),
            _role("Play", "Play Axis (Hoạt ảnh theo thời gian)", "column", multi=False, required=False, hint="VD: MonthName hoặc Date để chạy animation"),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["scatter", "scatter chart", "bubble", "dot plot", "phân tán", "bong bóng"],
        supports_constant_line=True,
    ),

    # =========================================================================
    # 4. PIE, DONUT & TREEMAP (3 Built-in)
    # =========================================================================
    _vis(
        "pieChart", "Pie chart", "Biểu đồ tròn (Pie)",
        "04. Pie, Donut & Treemap", "builtin", "🥧",
        "Hiển thị tỷ lệ phần trăm đóng góp của từng nhóm vào tổng thể (nên dùng <= 6 nhóm).",
        PIE_DONUT_ROLES, ["pie", "pie chart", "biểu đồ tròn"],
        supports_axes=False,
    ),
    _vis(
        "donutChart", "Donut chart", "Biểu đồ vành khuyên (Donut)",
        "04. Pie, Donut & Treemap", "builtin", "🍩",
        "Tương tự biểu đồ tròn nhưng có khoảng trống ở giữa, phù hợp phân tích cơ cấu trạng thái.",
        PIE_DONUT_ROLES, ["donut", "doughnut", "donut chart", "vành khuyên"],
        supports_axes=False,
    ),
    _vis(
        "treemap", "Treemap", "Biểu đồ bản đồ cây (Treemap)",
        "04. Pie, Donut & Treemap", "builtin", "🟩",
        "Hiển thị dữ liệu phân cấp theo diện tích hình chữ nhật lồng nhau, tối ưu khi có nhiều nhóm.",
        [
            _role("Group", "Category (Nhóm phân cấp chính)", "column", multi=True, required=True, active_by_default=True),
            _role("Details", "Details (Nhóm con bên trong)", "column", multi=False, required=False),
            _role("Values", "Values (Diện tích ô)", "measure", multi=False, required=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["treemap", "tree map", "bản đồ cây"],
        supports_axes=False,
    ),

    # =========================================================================
    # 5. MAPS & GEOSPATIAL (4 Built-in)
    # =========================================================================
    _vis(
        "map", "Map (Bubble Map)", "Bản đồ bong bóng (Bing Map)",
        "05. Maps & Geospatial", "builtin", "🗺️",
        "Định vị dữ liệu địa lý theo Bang/Thành phố hoặc Kinh độ/Vĩ độ với kích thước bong bóng.",
        [
            _role("Category", "Location (Bang / Thành phố / Quốc gia)", "column", multi=True, required=True, active_by_default=True),
            _role("Series", "Legend (Phân màu điểm)", "column", multi=False, required=False),
            _role("Y", "Latitude (Vĩ độ)", "column", multi=False, required=False),
            _role("X", "Longitude (Kinh độ)", "column", multi=False, required=False),
            _role("Size", "Bubble size (Kích thước bong bóng)", "measure", multi=False, required=False),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["map", "bubble map", "basic map", "bản đồ bong bóng"],
        supports_axes=False,
    ),
    _vis(
        "filledMap", "Filled Map (Choropleth)", "Bản đồ tô màu vùng (Filled Map)",
        "05. Maps & Geospatial", "builtin", "🌎",
        "Tô đậm nhạt theo ranh giới địa lý (Bang, Tỉnh, Quốc gia) để thấy mật độ/hiệu suất vùng miền.",
        [
            _role("Category", "Location (Bang / Quốc gia)", "column", multi=True, required=True, active_by_default=True),
            _role("Series", "Legend (Phân nhóm vùng)", "column", multi=False, required=False),
            _role("Y", "Latitude", "column", multi=False, required=False),
            _role("X", "Longitude", "column", multi=False, required=False),
            _role("Tooltips", "Tooltips (Chỉ số hiển thị & tô màu)", "any", multi=True, required=False),
        ],
        ["filled map", "choropleth", "bản đồ tô màu"],
        supports_axes=False,
    ),
    _vis(
        "shapeMap", "Shape Map", "Bản đồ hình khối tùy biến (Shape Map)",
        "05. Maps & Geospatial", "builtin", "🗾",
        "So sánh khu vực bằng bản đồ TopoJSON tùy chỉnh (Mỹ theo Bang, Việt Nam theo Tỉnh, sơ đồ nhà xưởng).",
        [
            _role("Category", "Location (Mã vùng / Bang)", "column", multi=False, required=True, active_by_default=True),
            _role("Series", "Legend", "column", multi=False, required=False),
            _role("Values", "Color saturation (Chỉ số tô màu)", "measure", multi=False, required=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["shape map", "topojson"],
        supports_axes=False,
    ),
    _vis(
        "azureMap", "Azure Map", "Bản đồ nâng cao Azure Maps",
        "05. Maps & Geospatial", "builtin", "🌐",
        "Bản đồ thế hệ mới của Microsoft hỗ trợ Bubble Layer, Heat Map Layer, 3D Bar Chart và Reference Layer.",
        [
            _role("Category", "Location (Địa điểm)", "column", multi=True, required=True, active_by_default=True),
            _role("Y", "Latitude (Vĩ độ)", "column", multi=False, required=False),
            _role("X", "Longitude (Kinh độ)", "column", multi=False, required=False),
            _role("Size", "Size (Kích thước)", "measure", multi=False, required=False),
            _role("Series", "Legend (Phân nhóm)", "column", multi=False, required=False),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["azure map", "azure maps", "bản đồ azure"],
        supports_axes=False,
    ),

    # =========================================================================
    # 6. KPI, GAUGE & CARDS (5 Built-in)
    # =========================================================================
    _vis(
        "gauge", "Gauge (Radial)", "Đồng hồ đo tiến độ (Gauge)",
        "06. KPI, Gauge & Cards", "builtin", "⏱️",
        "Đo mức độ hoàn thành của một chỉ số so với ngưỡng Min, Max và vạch Mục tiêu (Target).",
        [
            _role("Y", "Value (Giá trị hiện tại)", "measure", multi=False, required=True),
            _role("MinValue", "Minimum value (Ngưỡng tối thiểu)", "measure", multi=False, required=False),
            _role("MaxValue", "Maximum value (Ngưỡng tối đa)", "measure", multi=False, required=False),
            _role("TargetValue", "Target value (Vạch mục tiêu)", "measure", multi=False, required=False),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["gauge", "radial gauge", "đồng hồ đo"],
        supports_legend=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "card", "Card (Classic)", "Thẻ chỉ số đơn (Card cổ điển)",
        "06. KPI, Gauge & Cards", "builtin", "🪪",
        "Hiển thị nổi bật một con số KPI duy nhất với định dạng đơn vị tự động.",
        [
            _role("Values", "Fields (Chỉ số KPI hiển thị)", "any", multi=False, required=True),
        ],
        ["card", "single number card", "kpi card", "thẻ số"],
        supports_legend=False, supports_data_labels=True, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "cardVisual", "Card (New)", "Thẻ chỉ số hiện đại (New Card Visual)",
        "06. KPI, Gauge & Cards", "builtin", "🎴",
        "Thẻ KPI thế hệ mới hỗ trợ hiển thị nhiều chỉ số cùng lúc theo lưới, thêm Reference Labels, icon & thanh màu.",
        [
            _role("Data", "Data (Danh sách chỉ số hiển thị trên Card)", "any", multi=True, required=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["new card", "card visual", "modern card", "thẻ mới"],
        supports_legend=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "multiRowCard", "Multi-row card", "Thẻ hiển thị nhiều dòng (Multi-row Card)",
        "06. KPI, Gauge & Cards", "builtin", "🗂️",
        "Trình bày gọn gàng danh sách nhiều chỉ số hoặc thuộc tính liên quan trên cùng một khung thẻ.",
        [
            _role("Values", "Fields (Nhiều chỉ số / cột)", "any", multi=True, required=True),
        ],
        ["multi-row card", "multirow card", "thẻ nhiều dòng"],
        supports_legend=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "kpi", "KPI Visual", "Biểu đồ KPI có xu hướng & Mục tiêu",
        "06. KPI, Gauge & Cards", "builtin", "🎯",
        "Hiển thị con số KPI chính kèm đường xu hướng mờ phía sau và % chênh lệch so với Mục tiêu (Goal).",
        [
            _role("Indicator", "Value / Indicator (Chỉ số chính)", "measure", multi=False, required=True),
            _role("TrendAxis", "Trend axis (Trục thời gian xu hướng)", "column", multi=False, required=True),
            _role("Goal", "Target / Goal (Chỉ số mục tiêu)", "measure", multi=False, required=False),
        ],
        ["kpi", "kpi visual", "chỉ tiêu kpi"],
        supports_legend=False, supports_axes=False, supports_top_n=False,
    ),

    # =========================================================================
    # 7. SLICERS & FILTER CONTROLS (4 Built-in)
    # =========================================================================
    _vis(
        "slicer", "Slicer (Classic)", "Bộ lọc Slicer chuẩn (Dropdown / List / Between)",
        "07. Slicers & Filters", "builtin", "🔻",
        "Bộ lọc tương tác trên trang hỗ trợ kiểu Dropdown, Danh sách, Khoảng thời gian (Between) và Sync Slicers.",
        [
            _role("Values", "Field (Cột dùng để lọc)", "column", multi=True, required=True, active_by_default=True),
        ],
        ["slicer", "bộ lọc", "dropdown slicer", "between slicer"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "advancedSlicerVisual", "Button Slicer (New)", "Bộ lọc dạng Nút bấm hiện đại (Button Slicer)",
        "07. Slicers & Filters", "builtin", "🔘",
        "Bộ lọc dạng lưới nút bấm (Tiles) đẹp mắt, hỗ trợ hiển thị hình ảnh, nhãn phụ và trạng thái Hover/Selected.",
        [
            _role("Values", "Field (Cột tạo nút bấm)", "column", multi=True, required=True, active_by_default=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["button slicer", "tile slicer", "new slicer", "advanced slicer"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "listSlicer", "List Slicer (New)", "Bộ lọc Danh sách phân cấp (List Slicer)",
        "07. Slicers & Filters", "builtin", "☑️",
        "Bộ lọc danh sách hiện đại hỗ trợ phân cấp cha-con (Expand/Collapse) và nhãn phụ.",
        [
            _role("Values", "Field (Cột danh sách phân cấp)", "column", multi=True, required=True, active_by_default=True),
        ],
        ["list slicer", "hierarchy slicer"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "textSlicer", "Text Slicer (Input Filter)", "Bộ lọc Nhập chữ tìm kiếm (Text Slicer)",
        "07. Slicers & Filters", "builtin", "🔎",
        "Cho phép người dùng gõ trực tiếp từ khóa hoặc mã chuyến bay/sản phẩm để lọc dữ liệu.",
        [
            _role("Values", "Field (Cột văn bản cần tìm)", "column", multi=False, required=True, active_by_default=True),
        ],
        ["text slicer", "input slicer", "search slicer"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),

    # =========================================================================
    # 8. TABLES & MATRICES (2 Built-in)
    # =========================================================================
    _vis(
        "tableEx", "Table", "Bảng dữ liệu chi tiết (Table)",
        "08. Tables & Matrices", "builtin", "📋",
        "Hiển thị danh sách bản ghi chi tiết hoặc bảng tổng hợp với số lượng cột & measure không giới hạn.",
        [
            _role("Values", "Columns (Danh sách Cột & DAX Measures)", "any", multi=True, required=True, hint="Thêm không giới hạn cột phân loại và DAX Measures"),
        ],
        ["table", "detail table", "bảng chi tiết", "watchlist"],
        supports_legend=False, supports_data_labels=False, supports_axes=False,
    ),
    _vis(
        "matrix", "Matrix (Pivot / Heatmap)", "Ma trận đa chiều & Heatmap (Matrix)",
        "08. Tables & Matrices", "builtin", "🧮",
        "Bảng xoay chiều hỗ trợ phân cấp nhiều tầng (Drill-down) ở cả Hàng và Cột, thích hợp làm Heatmap.",
        [
            _role("Rows", "Rows (Các tầng Hàng - hỗ trợ Drill-down)", "column", multi=True, required=True, active_by_default=True),
            _role("Columns", "Columns (Các tầng Cột)", "column", multi=True, required=False, active_by_default=True),
            _role("Values", "Values (Các chỉ số / DAX Measures)", "measure", multi=True, required=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["matrix", "heatmap", "pivot", "ma trận"],
        supports_legend=False, supports_data_labels=False, supports_axes=False,
    ),

    # =========================================================================
    # 9. AI & SMART VISUALS (4 Built-in)
    # =========================================================================
    _vis(
        "decompositionTreeVisual", "Decomposition Tree (AI)", "Cây phân rã nguyên nhân AI (Decomposition Tree)",
        "09. AI & Smart Visuals", "builtin", "🌳",
        "Visual AI cho phép phân rã một chỉ số qua nhiều chiều dữ liệu và tự động tìm nhánh cao nhất/thấp nhất.",
        [
            _role("Analyze", "Analyze (Chỉ số cần phân tích)", "measure", multi=False, required=True),
            _role("ExplainBy", "Explain by (Các chiều giải thích nguyên nhân)", "column", multi=True, required=True, active_by_default=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["decomposition tree", "cây phân rã", "root cause tree"],
        supports_legend=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "keyDriversVisual", "Key Influencers (AI)", "Phân tích yếu tố ảnh hưởng chính AI (Key Influencers)",
        "09. AI & Smart Visuals", "builtin", "🧠",
        "Visual AI tự động chạy hồi quy/phân cụm để tìm ra các yếu tố tác động mạnh nhất làm tăng/giảm KPI.",
        [
            _role("Analyze", "Analyze (Cột/Chỉ số mục tiêu cần phân tích)", "any", multi=False, required=True),
            _role("ExplainBy", "Explain by (Các thuộc tính nghi ngờ ảnh hưởng)", "column", multi=True, required=True),
            _role("ExpandBy", "Expand by (Chiều mở rộng khi phân tích Measure)", "column", multi=True, required=False),
        ],
        ["key influencers", "key drivers", "yếu tố ảnh hưởng"],
        supports_legend=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "qnaVisual", "Q&A Visual", "Hỏi đáp ngôn ngữ tự nhiên (Q&A)",
        "09. AI & Smart Visuals", "builtin", "💬",
        "Cho phép người xem báo cáo gõ câu hỏi bằng tiếng Anh để Power BI tự sinh biểu đồ tức thì.",
        [
            _role("Values", "Suggested Fields (Các trường gợi ý)", "any", multi=True, required=False),
        ],
        ["q&a", "qna", "hỏi đáp"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "aiNarratives", "Smart Narrative (AI)", "Tóm tắt nhận định tự động AI (Smart Narrative)",
        "09. AI & Smart Visuals", "builtin", "📝",
        "Tự động viết đoạn văn tóm tắt biến động chính và insight của trang báo cáo theo bộ lọc hiện tại.",
        [
            _role("Values", "Context Values (Các chỉ số tóm tắt)", "any", multi=True, required=False),
        ],
        ["smart narrative", "ai narrative", "tóm tắt tự động"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),

    # =========================================================================
    # 10. DEVELOPER, SCRIPTS & UI ELEMENTS (6 Built-in)
    # =========================================================================
    _vis(
        "pythonVisual", "Python Visual", "Biểu đồ mã Python (Matplotlib / Seaborn / Plotly)",
        "10. Scripts & UI Elements", "builtin", "🐍",
        "Nhúng trực tiếp mã Python (Matplotlib, Seaborn, SciPy) vẽ biểu đồ thống kê nâng cao trên dữ liệu Power BI.",
        [
            _role("Values", "Values (Các cột truyền vào DataFrame `dataset`)", "any", multi=True, required=True),
        ],
        ["python visual", "python script", "biểu đồ python"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_script="python",
    ),
    _vis(
        "scriptVisual", "R Script Visual", "Biểu đồ mã R (ggplot2 / Stats)",
        "10. Scripts & UI Elements", "builtin", "📐",
        "Nhúng trực tiếp mã R (ggplot2, corrplot, forecast) để trực quan hóa phân tích thống kê chuyên sâu.",
        [
            _role("Values", "Values (Các cột truyền vào DataFrame `dataset`)", "any", multi=True, required=True),
        ],
        ["r visual", "r script", "biểu đồ r"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_script="r",
    ),
    _vis(
        "paginatedReport", "Paginated Report", "Báo cáo phân trang in ấn (Paginated Report)",
        "10. Scripts & UI Elements", "builtin", "📄",
        "Nhúng báo cáo RDL chuẩn in ấn nhiều trang vào bên trong Dashboard Power BI.",
        [
            _role("Values", "Parameters (Tham số truyền vào báo cáo)", "any", multi=True, required=False),
        ],
        ["paginated report", "báo cáo in"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "textbox", "Text Box / Header", "Khung văn bản / Tiêu đề (Text Box)",
        "10. Scripts & UI Elements", "builtin", "🔤",
        "Khung văn bản tự do để làm tiêu đề trang, ghi chú nghiệp vụ hoặc mô tả nguồn dữ liệu.",
        [],
        ["textbox", "text box", "header", "văn bản"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "actionButton", "Action Button", "Nút thao tác (Reset Filters / Back / Navigation)",
        "10. Scripts & UI Elements", "builtin", "⏩",
        "Nút bấm tương tác dùng để Reset Filters (Bookmark), chuyển trang hoặc quay lại trang trước (Back).",
        [],
        ["button", "action button", "reset filters", "nút bấm"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),
    _vis(
        "shape", "Shape / Panel", "Hình khối / Khung nền nhóm Visual (Shape)",
        "10. Scripts & UI Elements", "builtin", "⬜",
        "Khung hình chữ nhật, đường kẻ hoặc mũi tên để phân chia bố cục trực quan cho trang báo cáo.",
        [],
        ["shape", "rectangle", "khung nền"],
        supports_legend=False, supports_data_labels=False, supports_axes=False, supports_top_n=False,
    ),

    # =========================================================================
    # 11. MICROSOFT OFFICIAL SAMPLES & APPSOURCE MARKETPLACE VISUALS (22 Visuals)
    # =========================================================================
    _vis(
        "sankey02300D1BE6F5427989F3DE31CCA9E0F32020", "Sankey Chart (Microsoft AppSource)", "Biểu đồ dòng chảy Sankey (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🔀",
        "Hiển thị luồng dịch chuyển giữa Nguồn (Source) và Đích (Destination) với độ dày tỷ lệ theo trọng số.",
        [
            _role("Source", "Source (Điểm đi / Nguồn)", "column", multi=False, required=True, active_by_default=True),
            _role("Destination", "Destination (Điểm đến / Đích)", "column", multi=False, required=True),
            _role("Weight", "Weight (Giá trị dòng chảy)", "measure", multi=False, required=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["sankey", "sankey chart", "dòng chảy"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380772",
        fallback_builtin="clusteredBarChart",
    ),
    _vis(
        "WordCloud1447959067750", "Word Cloud (Microsoft AppSource)", "Đám mây từ khóa Word Cloud (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "☁️",
        "Trực quan hóa tần suất từ khóa, mã sân bay hoặc lý do chậm/hủy theo kích thước chữ.",
        [
            _role("Category", "Category (Cột từ khóa / Nhãn)", "column", multi=False, required=True, active_by_default=True),
            _role("Values", "Values (Trọng số kích thước chữ)", "measure", multi=False, required=False),
            _role("Excludes", "Excludes (Từ loại trừ)", "column", multi=False, required=False),
        ],
        ["word cloud", "wordcloud", "đám mây từ"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380752",
        fallback_builtin="treemap",
    ),
    _vis(
        "ChordChart1444757060245", "Chord Chart (Microsoft AppSource)", "Biểu đồ dây cung quan hệ Chord (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "⭕",
        "Hiển thị mối liên kết hai chiều giữa các thực thể trên vòng tròn (VD: luồng bay giữa các Bang/Sân bay).",
        [
            _role("From", "From (Thực thể nguồn)", "column", multi=False, required=True, active_by_default=True),
            _role("To", "To (Thực thể đích)", "column", multi=False, required=True),
            _role("Values", "Values (Cường độ liên kết)", "measure", multi=False, required=True),
        ],
        ["chord", "chord chart", "dây cung"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380764",
        fallback_builtin="matrix",
    ),
    _vis(
        "BulletChart1443347686880", "Bullet Chart (Microsoft AppSource)", "Biểu đồ thanh mục tiêu Bullet Chart (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🎯",
        "So sánh giá trị thực tế với Mục tiêu (Target) và các vùng đánh giá (Kém, Đạt, Tốt, Xuất sắc).",
        [
            _role("Category", "Category (Đối tượng so sánh)", "column", multi=False, required=True, active_by_default=True),
            _role("Value", "Value (Giá trị thực tế)", "measure", multi=False, required=True),
            _role("TargetValue", "Target Value (Mục tiêu)", "measure", multi=False, required=False),
            _role("Minimum", "Minimum (Ngưỡng tối thiểu)", "measure", multi=False, required=False),
            _role("NeedsImprovement", "Needs Improvement (Ngưỡng cần cải thiện)", "measure", multi=False, required=False),
            _role("Satisfactory", "Satisfactory (Ngưỡng đạt)", "measure", multi=False, required=False),
            _role("Good", "Good (Ngưỡng tốt)", "measure", multi=False, required=False),
            _role("VeryGood", "Very Good (Ngưỡng rất tốt)", "measure", multi=False, required=False),
            _role("Maximum", "Maximum (Ngưỡng tối đa)", "measure", multi=False, required=False),
        ],
        ["bullet", "bullet chart"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380755",
        fallback_builtin="clusteredBarChart",
    ),
    _vis(
        "TornadoChart1452517688218", "Tornado Chart (Microsoft AppSource)", "Biểu đồ lốc xoáy đối xứng Tornado (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🌪️",
        "So sánh đối xứng 2 nhóm dữ liệu hai bên trục giữa (VD: Dep OTP vs Arr OTP, Nam vs Nữ).",
        [
            _role("Category", "Group (Trục danh mục giữa)", "column", multi=False, required=True, active_by_default=True),
            _role("Series", "Legend (2 nhóm so sánh đối xứng)", "column", multi=False, required=False),
            _role("Values", "Values (Giá trị 2 bên)", "measure", multi=True, required=True),
        ],
        ["tornado", "tornado chart", "pyramid chart", "lốc xoáy"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380765",
        fallback_builtin="clusteredBarChart",
    ),
    _vis(
        "Gantt1448688115699", "Gantt Chart (Microsoft AppSource)", "Biểu đồ tiến độ Gantt (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "📅",
        "Quản lý lịch trình, tiến độ dự án, thời gian bắt đầu/kết thúc, % hoàn thành và tài nguyên.",
        [
            _role("Legend", "Legend (Phân nhóm màu)", "column", multi=False, required=False),
            _role("Task", "Task (Tên công việc / Chuyến)", "column", multi=False, required=True, active_by_default=True),
            _role("Parent", "Parent (Nhóm công việc cha)", "column", multi=False, required=False),
            _role("StartDate", "Start Date (Ngày bắt đầu)", "column", multi=False, required=True),
            _role("EndDate", "End Date (Ngày kết thúc)", "column", multi=False, required=False),
            _role("Duration", "Duration (Thời lượng)", "measure", multi=False, required=False),
            _role("Completion", "% Completion (% Hoàn thành)", "measure", multi=False, required=False),
            _role("Resource", "Resource (Người/Đơn vị phụ trách)", "column", multi=False, required=False),
            _role("Milestones", "Milestones (Mốc quan trọng)", "column", multi=False, required=False),
            _role("ExtraInformation", "Tooltips", "any", multi=True, required=False),
        ],
        ["gantt", "gantt chart", "tiến độ"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380766",
        fallback_builtin="clusteredBarChart",
    ),
    _vis(
        "RadarChart1446119667547", "Radar Chart (Microsoft AppSource)", "Biểu đồ mạng nhện Radar (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🕸️",
        "So sánh đa tiêu chí trên các trục tỏa tròn từ tâm (Spider/Web Chart).",
        [
            _role("Category", "Category (Các trục tiêu chí)", "column", multi=False, required=True, active_by_default=True),
            _role("Y", "Y-axis (Các chuỗi chỉ số so sánh)", "measure", multi=True, required=True),
        ],
        ["radar", "radar chart", "spider chart", "mạng nhện"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380771",
        fallback_builtin="lineChart",
    ),
    _vis(
        "Sunburst1445472000808", "Sunburst Chart (Microsoft AppSource)", "Biểu đồ đồng tâm phân cấp Sunburst (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "☀️",
        "Hiển thị dữ liệu phân cấp nhiều tầng theo các vòng tròn đồng tâm mở rộng dần ra ngoài.",
        [
            _role("Group", "Groups (Nhiều cấp độ phân cấp)", "column", multi=True, required=True, active_by_default=True),
            _role("Values", "Values (Độ lớn cung)", "measure", multi=False, required=True),
        ],
        ["sunburst", "sunburst chart", "đồng tâm"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380768",
        fallback_builtin="donutChart",
    ),
    _vis(
        "AsterPlot1443303142064", "Aster Plot (Microsoft AppSource)", "Biểu đồ hoa hướng dương Aster Plot (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🌼",
        "Biến thể biểu đồ Donut cho phép dùng chỉ số thứ 2 để quyết định độ dài bán kính từng cánh.",
        [
            _role("Category", "Category (Nhóm cánh)", "column", multi=False, required=True, active_by_default=True),
            _role("Y", "Y-axis (1 hoặc 2 chỉ số: độ dài & độ rộng góc)", "measure", multi=True, required=True),
        ],
        ["aster", "aster plot"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380754",
        fallback_builtin="donutChart",
    ),
    _vis(
        "StreamGraph1446659696222", "Stream Graph (Microsoft AppSource)", "Biểu đồ dòng sóng Stream Graph (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "〰️",
        "Biểu đồ miền chồng mượt mà quanh trục trung tâm, lý tưởng theo dõi biến động theo thời gian.",
        [
            _role("Category", "Category (Trục thời gian)", "column", multi=False, required=True, active_by_default=True),
            _role("Group", "Legend (Nhóm phân tách)", "column", multi=False, required=False),
            _role("Values", "Values (Độ rộng dòng)", "measure", multi=False, required=True),
        ],
        ["stream graph", "streamgraph"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380770",
        fallback_builtin="stackedAreaChart",
    ),
    _vis(
        "Histogram1445664487616", "Histogram Chart (Microsoft AppSource)", "Biểu đồ phân phối tần suất Histogram (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "📶",
        "Tự động chia khoảng (Bins) và vẽ phân phối tần suất của một biến liên tục (VD: phân phối số phút trễ).",
        [
            _role("Values", "Values (Biến số liên tục)", "column", multi=False, required=True, active_by_default=True),
            _role("Frequency", "Frequency (Tần suất / Trọng số)", "measure", multi=False, required=False),
        ],
        ["histogram", "phân phối tần suất"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380776",
        fallback_builtin="clusteredColumnChart",
    ),
    _vis(
        "ChicletSlicer1448559807354", "Chiclet Slicer (Microsoft AppSource)", "Bộ lọc ô ảnh/nút Chiclet Slicer (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🎛️",
        "Bộ lọc nút bấm nổi tiếng của Microsoft hỗ trợ hiển thị logo hãng bay/hình ảnh sản phẩm theo lưới.",
        [
            _role("Category", "Category (Trường lọc)", "column", multi=False, required=True, active_by_default=True),
            _role("Values", "Values (Chỉ số sắp xếp)", "measure", multi=False, required=False),
            _role("Images", "Image (URL hình ảnh/logo)", "column", multi=False, required=False),
        ],
        ["chiclet", "chiclet slicer"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380756",
        fallback_builtin="advancedSlicerVisual",
    ),
    _vis(
        "Timeline1447991079100", "Timeline Slicer (Microsoft AppSource)", "Thanh trượt thời gian Timeline Slicer (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🗓️",
        "Bộ lọc thanh trượt thời gian trực quan theo Năm / Quý / Tháng / Tuần / Ngày.",
        [
            _role("Time", "Time (Cột Date)", "column", multi=False, required=True, active_by_default=True),
        ],
        ["timeline", "timeline slicer"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380786",
        fallback_builtin="slicer",
    ),
    _vis(
        "textFilter25A4896A83E0487089E2B90C9AE57C8A", "Text Filter (Microsoft AppSource)", "Ô tìm kiếm văn bản Text Filter (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🔍",
        "Hộp tìm kiếm từ khóa nhanh trên các cột mã chuyến bay, tên sân bay, khách hàng.",
        [
            _role("field", "Field (Cột văn bản)", "column", multi=False, required=True, active_by_default=True),
        ],
        ["text filter"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104381309",
        fallback_builtin="textSlicer",
    ),
    _vis(
        "MekkoChart1449744733038", "Marimekko Chart (Microsoft AppSource)", "Biểu đồ Marimekko 2 chiều tỷ trọng (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🧱",
        "Biểu đồ cột chồng 100% có độ rộng cột thay đổi tỷ lệ theo quy mô từng danh mục.",
        [
            _role("Category", "Category (Trục ngang)", "column", multi=False, required=True, active_by_default=True),
            _role("Series", "Series (Phân lớp màu trong cột)", "column", multi=False, required=True),
            _role("Y", "Y (Chiều cao / Giá trị)", "measure", multi=False, required=True),
            _role("Width", "Width (Độ rộng cột)", "measure", multi=False, required=False),
        ],
        ["mekko", "marimekko", "mekko chart"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380767",
        fallback_builtin="hundredPercentStackedColumnChart",
    ),
    _vis(
        "ForceGraph1449359463895", "Force-Directed Graph (Microsoft AppSource)", "Đồ thị mạng lưới Force-Directed (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🕸️",
        "Mô phỏng mạng lưới kết nối nút-cạnh vật lý (VD: Mạng lưới đường bay Hub-and-Spoke giữa các sân bay).",
        [
            _role("Source", "Source (Nút nguồn)", "column", multi=False, required=True, active_by_default=True),
            _role("Target", "Target (Nút đích)", "column", multi=False, required=True),
            _role("Weight", "Weight (Độ dày liên kết)", "measure", multi=False, required=False),
            _role("LinkType", "Link Type (Loại liên kết)", "column", multi=False, required=False),
        ],
        ["force directed", "network graph", "đồ thị mạng"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380763",
        fallback_builtin="scatterChart",
    ),
    _vis(
        "SandDance201929976D117A654D0BAB8E96507442D80B", "SandDance 3D WebGL (Microsoft Research)", "Phân tích đa chiều 3D WebGL SandDance (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "🧊",
        "Visual WebGL 2D/3D của Microsoft Research hiển thị hàng trăm nghìn điểm dữ liệu tương tác mượt mà.",
        [
            _role("Values", "Values (Các cột đưa vào không gian 3D: X, Y, Z, Color, Size)", "any", multi=True, required=True),
        ],
        ["sanddance", "webgl", "3d chart"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA200000438",
        fallback_builtin="scatterChart",
    ),
    _vis(
        "PulseChart1459202849658", "Pulse Chart (Microsoft AppSource)", "Biểu đồ xung sự kiện Pulse Chart (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "💓",
        "Vẽ đường thời gian kèm các điểm nhấn chú thích sự kiện quan trọng theo thời gian thực.",
        [
            _role("Timestamp", "Timestamp (Trục thời gian)", "column", multi=False, required=True, active_by_default=True),
            _role("Value", "Value (Giá trị đường xung)", "measure", multi=False, required=True),
            _role("EventTitle", "Event Title (Tiêu đề sự kiện)", "column", multi=False, required=False),
            _role("EventDescription", "Event Description (Mô tả sự kiện)", "column", multi=False, required=False),
        ],
        ["pulse", "pulse chart"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380784",
        fallback_builtin="lineChart",
    ),
    _vis(
        "EnhancedScatterChart1443994985041", "Enhanced Scatter (Microsoft AppSource)", "Biểu đồ phân tán nâng cao hình ảnh (AppSource)",
        "11. AppSource & Developer Samples", "appsource_microsoft", "✨",
        "Scatter Chart hỗ trợ hình nền tùy chỉnh, thay điểm bằng hình ảnh/logo và màu động.",
        [
            _role("Category", "Details", "column", multi=False, required=True, active_by_default=True),
            _role("Series", "Legend", "column", multi=False, required=False),
            _role("X", "X-axis", "measure", multi=False, required=True),
            _role("Y", "Y-axis", "measure", multi=False, required=True),
            _role("Size", "Size", "measure", multi=False, required=False),
            _role("Image", "Image URL", "column", multi=False, required=False),
        ],
        ["enhanced scatter"],
        appsource_url="https://appsource.microsoft.com/en-us/product/power-bi-visuals/WA104380778",
        fallback_builtin="scatterChart",
    ),
    _vis(
        "BoxAndWhiskerChartAppSource", "Box and Whisker Plot (AppSource)", "Biểu đồ hộp phân vị Box Plot (AppSource)",
        "11. AppSource & Developer Samples", "appsource_custom", "📦",
        "Hiển thị phân vị Min, Q1, Median, Q3, Max và các điểm ngoại lai (Outliers) theo từng danh mục.",
        [
            _role("Category", "Category (Nhóm so sánh)", "column", multi=False, required=True, active_by_default=True),
            _role("Sampling", "Sampling (Chi tiết mẫu)", "column", multi=False, required=False),
            _role("Values", "Value (Giá trị đo phân vị)", "measure", multi=False, required=True),
        ],
        ["box plot", "box and whisker", "biểu đồ hộp"],
        appsource_url="https://appsource.microsoft.com/en-us/marketplace/apps?product=power-bi-visuals&search=Box%20and%20Whisker",
        fallback_builtin="clusteredColumnChart",
    ),
    _vis(
        "CalendarHeatmapAppSource", "Calendar Heatmap (AppSource)", "Lịch nhiệt theo ngày Calendar Heatmap (AppSource)",
        "11. AppSource & Developer Samples", "appsource_custom", "📆",
        "Trực quan hóa cường độ chỉ số theo từng ô ngày trên lịch tháng/năm (tương tự GitHub contributions).",
        [
            _role("Date", "Date (Cột ngày tháng)", "column", multi=False, required=True, active_by_default=True),
            _role("Values", "Measure Data (Giá trị tô màu ngày)", "measure", multi=False, required=True),
            _role("Tooltips", "Tooltips", "any", multi=True, required=False),
        ],
        ["calendar", "calendar heatmap", "lịch nhiệt"],
        appsource_url="https://appsource.microsoft.com/en-us/marketplace/apps?product=power-bi-visuals&search=Calendar",
        fallback_builtin="matrix",
    ),
    _vis(
        "TableHeatMap1443716069308", "Table Heatmap (AppSource)", "Bảng nhiệt cường độ màu (AppSource)",
        "11. AppSource & Developer Samples", "appsource_custom", "🔥",
        "Hiển thị ma trận 2 chiều với thang màu liên tục để phát hiện ngay điểm nóng (Hotspots).",
        [
            _role("Category", "Category (Hàng)", "column", multi=False, required=True, active_by_default=True),
            _role("Y", "Y (Cột)", "column", multi=False, required=True),
            _role("Values", "Value (Giá trị nhiệt)", "measure", multi=False, required=True),
        ],
        ["table heatmap", "bảng nhiệt"],
        appsource_url="https://appsource.microsoft.com/en-us/marketplace/apps?product=power-bi-visuals&search=Heatmap",
        fallback_builtin="matrix",
    ),
]


def load_imported_pbiviz_catalog(workspace_dir: str) -> List[Dict[str, Any]]:
    """Scan workspace/custom_visuals/*.pbiviz and register every imported custom visual with its real GUID and dataRoles."""
    cv_dir = Path(workspace_dir) / "custom_visuals"
    if not cv_dir.exists():
        return []
    imported = []
    for pbiviz_path in sorted(cv_dir.glob("*.pbiviz")):
        try:
            meta = inspect_pbiviz_package(pbiviz_path)
            if meta:
                imported.append(meta)
        except Exception:
            continue
    return imported


def inspect_pbiviz_package(pbiviz_path: Path) -> Optional[Dict[str, Any]]:
    """Extract GUID, displayName, description, and exact dataRoles from any Microsoft AppSource .pbiviz file."""
    with zipfile.ZipFile(pbiviz_path, "r") as zf:
        names = zf.namelist()
        pkg_file = next((n for n in names if n.endswith("package.json")), None)
        if not pkg_file:
            return None
        pkg = json.loads(zf.read(pkg_file).decode("utf-8-sig"))
        vis_meta = pkg.get("visual", {})
        guid = vis_meta.get("guid") or pbiviz_path.stem
        display_name = vis_meta.get("displayName") or guid
        desc = vis_meta.get("description") or f"Custom visual imported from {pbiviz_path.name}"

        # Extract capabilities.json -> dataRoles (exact Power BI field wells!)
        roles = []
        res_json_files = [n for n in names if n.endswith(".json") and "resources/" in n]
        for rf in res_json_files:
            try:
                res_obj = json.loads(zf.read(rf).decode("utf-8-sig"))
                cap = res_obj.get("capabilities") or {}
                for dr in cap.get("dataRoles", []):
                    r_kind = "column" if dr.get("kind") == 0 else ("measure" if dr.get("kind") == 1 else "any")
                    roles.append(_role(
                        dr["name"],
                        dr.get("displayName") or dr["name"],
                        kind=r_kind,
                        multi=True,
                        required=False,
                        active_by_default=(r_kind == "column"),
                    ))
                if roles:
                    break
            except Exception:
                continue

        if not roles:
            roles = [
                _role("Category", "Category", "column", multi=True, required=False, active_by_default=True),
                _role("Values", "Values", "measure", multi=True, required=False),
            ]

        return _vis(
            guid,
            f"{display_name} (.pbiviz)",
            f"{display_name} (Đã cài .pbiviz)",
            "12. Imported Custom Visuals (.pbiviz)",
            "imported_pbiviz",
            "🧩",
            desc,
            roles,
            [display_name.lower(), guid.lower()],
            fallback_builtin=guid,
        )


def get_full_visual_catalog(workspace_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all built-in + AppSource reference visuals + any locally imported .pbiviz packages."""
    catalog = list(POWERBI_VISUAL_CATALOG)
    if workspace_dir:
        existing_guids = {v["visualType"] for v in catalog}
        for imp in load_imported_pbiviz_catalog(workspace_dir):
            if imp["visualType"] in existing_guids:
                # Upgrade the reference entry to imported_pbiviz with exact capabilities!
                catalog = [imp if v["visualType"] == imp["visualType"] else v for v in catalog]
            else:
                catalog.append(imp)
    return catalog


def get_visual_spec_by_type(vtype: str, workspace_dir: Optional[str] = None) -> Dict[str, Any]:
    catalog = get_full_visual_catalog(workspace_dir)
    for v in catalog:
        if v["visualType"] == vtype:
            return v
    # Default fallback to clusteredBarChart
    return next(v for v in POWERBI_VISUAL_CATALOG if v["visualType"] == "clusteredBarChart")


def match_visual_type_from_text(raw_text: str, workspace_dir: Optional[str] = None) -> str:
    """Match natural Vietnamese/English chart descriptions in Requirement.md to any visualType in the catalog."""
    low = raw_text.lower().strip()
    catalog = get_full_visual_catalog(workspace_dir)
    # 1. Exact visualType match
    for v in catalog:
        if low == v["visualType"].lower() or low == v["name"].lower():
            return v["visualType"]
    # 2. Longest keyword match first so '100% stacked bar' wins over 'bar'
    matches = []
    for v in catalog:
        for kw in v.get("keywords", []):
            if kw.lower() in low:
                matches.append((len(kw), v["visualType"]))
    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1]
    return "clusteredBarChart"
