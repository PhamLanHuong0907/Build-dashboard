# HƯỚNG DẪN CHI TIẾT CÁCH VIẾT FILE `Requirement.md` ĐỂ PHẦN MỀM TỰ ĐỘNG SINH POWER BI DASHBOARD

Phần mềm **Auto-PBI Dashboard Studio** tích hợp bộ biên dịch phổ quát (`src/parser/universal_compiler.py`), cho phép bạn nạp **bất kỳ file dữ liệu `.csv` nào** cùng **một file mô tả nghiệp vụ `Requirement.md`** để tự động thực hiện từ A–Z:
1. Kiểm toán chất lượng dữ liệu (Data Profiling & Quality Audit)
2. Làm sạch dữ liệu & xây dựng Data Warehouse theo mô hình **Star Schema** (`Fact_Main` + `Dim_Date` + các bảng `Dim_*` kèm phân nhóm Pareto ABC tự động)
3. Sinh bộ công thức **DAX Measures** và **tự động đối soát độc lập từng measure** trên dữ liệu thực tế
4. Xuất dự án **Power BI Desktop (`.pbip` & `.pbit`)** hoàn chỉnh và tự động nạp dữ liệu vào Power BI Desktop.

> **Mẹo nhanh**: Bạn có thể bấm nút **👁️ Xem mẫu** hoặc **📋 Copy mẫu** cho file `Requirement_Template.md` ngay tại khung nạp CSV trên giao diện Web UI để điền theo mẫu chuẩn.

---

## I. 6 Nhóm Thông Tin Cần Có Trong `Requirement.md`

### 1. Thông Tin Tổng Quan Dự Án (Project Header)
- **Mục đích**: Đặt tên cho báo cáo Power BI và mô tả bối cảnh nghiệp vụ.
- **Cách viết**: Dùng tiêu đề Markdown `#` hoặc `##` ở đầu file:
  ```markdown
  # ĐẶC TẢ PHÂN TÍCH NGHIỆP VỤ VÀ THIẾT KẾ DASHBOARD POWER BI
  ## Đề tài: <Tên dự án / Chủ đề Dashboard của bạn>
  ```

### 2. Từ Điển Dữ Liệu Nguồn & Phân Loại Thuộc Tính (Data Dictionary)
- **Mục đích**: Khai báo rõ vai trò của từng cột trong file `.csv` để bộ biên dịch phân loại chính xác thay vì chỉ đoán tự động.
- **Cấu trúc bảng chuẩn** (tên cột `Thuộc tính` phải khớp chính xác header trong file `.csv`):
  ```markdown
  | Thuộc tính | Nhóm | Mô tả nghiệp vụ |
  |---|---|---|
  | OrderDate | Date | Ngày giao dịch (tự tạo bảng Dim_Date) |
  | Region | Dimension | Khu vực (tự tạo Dim_Region + Pareto ABC) |
  | Category | Dimension | Nhóm sản phẩm |
  | Revenue | Measure | Doanh thu |
  | IsReturned | Flag | Cờ nhị phân 0/1 |
  ```
- **4 nhóm giá trị hỗ trợ ở cột `Nhóm`**: `Date` (cột ngày chính), `Dimension` (chiều phân tích), `Measure` (cột số), `Flag` (cột cờ `{0, 1}`).

### 3. Quy Tắc Làm Sạch Dữ Liệu (ETL Cleaning)
- **Mục đích**: Ghi lại quy tắc xử lý giá trị trống (`NULL`), loại bỏ bản ghi trùng lặp và kiểm tra biên giá trị.
- **Lưu ý về tính toán mới**: Các chỉ số kết hợp giữa nhiều cột (như `Lợi nhuận = Revenue - Cost`, `Biên lợi nhuận %`, `Tỷ lệ hoàn trả`) nên định nghĩa bằng **DAX Measure** ở Mục 4 để Power BI tính động theo mọi Slicer/Filter.

### 4. Danh Mục KPI & Công Thức DAX (KPIs & DAX Measures)
Phần mềm hỗ trợ tự động trích xuất DAX theo **2 cách** (có thể dùng cả hai; nếu trùng tên, khối `DAX` sẽ ưu tiên):
- **Cách 1: Bảng KPI tổng hợp** (phần mềm tự biên dịch các cú pháp viết tắt `COUNTROWS(...)`, `SUM(Cột)`, `AVG(Cột)`, `MIN(Cột)`, `MAX(Cột)`, `DISTINCTCOUNT(Cột)`, hoặc biểu thức `DIVIDE(...)`):
  ```markdown
  | KPI | Công thức đề xuất | Đơn vị |
  |---|---|---|
  | Total Orders | COUNTROWS(Fact_Main) | Đơn |
  | Total Revenue | SUM(Revenue) | USD |
  | Avg Order Value | AVG(Revenue) | USD |
  | Return Rate | DIVIDE([IsReturned Count], [Total Orders]) | % |
  ```
- **Cách 2: Khối mã ```` ```DAX ```` chuẩn** (phần mềm đưa nguyên văn vào `model.bim` và tự động kiểm thử giá trị thực trên Tab **Kiểm Toán Dữ Liệu & KPI**):
  ````markdown
  ```DAX
  Gross Margin % =
  DIVIDE(
      SUM('Fact_Main'[Revenue]) - SUM('Fact_Main'[Cost]),
      SUM('Fact_Main'[Revenue])
  )
  ```
  ````
> *Lưu ý*: Ngay cả khi bạn không viết công thức DAX, phần mềm vẫn tự động sinh sẵn `Total <CộtSố>`, `Avg <CộtSố>`, `P90 <CộtSố>` cho các cột số và `<CộtCờ> Count`, `<CộtCờ> Rate (%)` cho các cột cờ `{0, 1}`.

### 5. Đặc Tả Từng Trang Dashboard, Slicer & KPI Cards
Mỗi trang Dashboard bắt đầu bằng dòng tiêu đề `# DASHBOARD <Số>: <Mã> – <Tên Trang>`:
- **Bảng Slicer của trang** (các Slicer cùng thuộc tính giữa nhiều trang tự động đồng bộ `Sync Slicers`):
  ```markdown
  # DASHBOARD 01: EX-01 – EXECUTIVE OVERVIEW

  ## Slicer
  | Slicer | Thuộc tính | Kiểu |
  |---|---|---|
  | Date Range | OrderDate | Between |
  | Region | Region | Dropdown |
  | Category | Category | Dropdown |
  ```
- **Danh sách KPI Cards của trang** (tối đa 6 thẻ/trang trên khung 16:9):
  ```markdown
  ## KPI Cards
  | KPI | Nội dung |
  |---|---|---|
  | Total Orders | Tổng số đơn hàng |
  | Total Revenue | Tổng doanh thu |
  | Gross Margin % | Biên lợi nhuận gộp |
  ```

### 6. Đặc Tả Chi Tiết Từng Biểu Đồ (Charts / Visuals) Trong Mỗi Trang
Mỗi biểu đồ bắt đầu bằng `### <MãBiểuĐồ> – <Tên Biểu Đồ>` kèm `Loại:` và các trường dữ liệu:
```markdown
## Danh sách biểu đồ

### EX01-01 – Revenue Trend Over Time
Loại: Line Chart
- X-axis: OrderDate
- Y-axis: Total Revenue

### EX01-02 – Revenue Mix by Category
Loại: Donut Chart
- Category: Category
- Values: Total Revenue

### EX01-03 – Top Regions by Revenue (Top N Filter = 5)
Loại: Horizontal Bar Chart
- Axis: Region
- Value: Total Revenue
```

**Danh mục toàn bộ 66+ loại Biểu đồ (`Loại:`) được hỗ trợ đầy đủ như Power BI Desktop**:

| Nhóm Biểu Đồ | Các Loại Biểu Đồ Hỗ Trợ (`visualType`) | Các Ô Dữ Liệu (Field Wells) Chính |
|---|---|---|
| **1. Bar & Column (7)** | `Stacked bar`, `Stacked column`, `Clustered bar`, `Clustered column`, `100% Stacked bar`, `100% Stacked column`, `Ribbon chart` | `Category` (Y/X-axis), `Y` (Values), `Series` (Legend), `Rows` (Small multiples), `Tooltips` |
| **2. Line, Area & Combo (6)** | `Line chart`, `Area chart`, `Stacked area`, `100% Stacked area`, `Line and stacked column`, `Line and clustered column` | `Category`, `Y`, `Y2` (Secondary/Line Y-axis), `Series`, `Rows` (Small multiples), `Tooltips` |
| **3. Waterfall, Funnel & Scatter (3)** | `Waterfall chart`, `Funnel chart`, `Scatter / Bubble / Dot Plot` | `Category`, `Breakdown`, `X`, `Y`, `Series`, `Size`, `Play` (Play Axis), `Tooltips` |
| **4. Pie, Donut & Treemap (3)** | `Pie chart`, `Donut chart`, `Treemap` | `Category`/`Group`, `Details`, `Y`/`Values`, `Tooltips` |
| **5. Maps & Geo (4)** | `Map (Bubble Map)`, `Filled Map`, `Shape Map`, `Azure Map` | `Category` (Location), `Series` (Legend), `Y` (Latitude), `X` (Longitude), `Size`, `Values`, `Tooltips` |
| **6. KPI, Gauge & Cards (5)** | `Gauge`, `Card (Classic)`, `Card (New / cardVisual)`, `Multi-row card`, `KPI Visual` | `Y`/`Values`/`Data`, `MinValue`, `MaxValue`, `TargetValue`, `Indicator`, `TrendAxis`, `Goal` |
| **7. Slicers & Filters (4)** | `Slicer (Classic)`, `Button Slicer (New)`, `List Slicer (New)`, `Text Slicer` | `Values` (Field), `Mode` (`Dropdown`/`Between`/`Basic`), `Sync Group` |
| **8. Tables & Matrices (2)** | `Table`, `Matrix (Pivot / Heatmap)` | `Rows` (nhiều tầng Drill-down), `Columns`, `Values` (nhiều Measures), `Tooltips` |
| **9. AI & Smart Visuals (4)** | `Decomposition Tree`, `Key Influencers`, `Q&A Visual`, `Smart Narrative` | `Analyze`, `ExplainBy` (nhiều chiều), `ExpandBy`, `Values`, `Tooltips` |
| **10. Scripts & UI Elements (6)** | `Python Visual`, `R Script Visual`, `Paginated Report`, `Text Box`, `Action Button`, `Shape` | `Values` (DataFrame fields) + trình soạn thảo mã Python/R trực tiếp |
| **11. AppSource & Samples (22+)** | `Sankey`, `Word Cloud`, `Chord`, `Bullet Chart`, `Tornado`, `Gantt`, `Radar`, `Sunburst`, `Aster Plot`, `Stream Graph`, `Histogram`, `Chiclet Slicer`, `Timeline Slicer`, `Text Filter`, `Marimekko`, `Force-Directed Graph`, `SandDance 3D WebGL`, `Pulse Chart`, `Enhanced Scatter`, `Box and Whisker`, `Calendar Heatmap`, `Table Heatmap` + **tải trực tiếp từ kho AppSource ngay trên Web UI (Tab 2)** hoặc import `.pbiviz` | Đầy đủ các ô chuyên biệt (`Source`, `Destination`, `Weight`, `StartDate`, `EndDate`, `Duration`, `Completion`, `TargetValue`, `Minimum`, `Maximum`, `From`, `To`...) |

**Các thuộc tính Phân tích & Định dạng hỗ trợ tự động**:
- **Lọc Top N / Bottom N**: Ghi `(Top N Filter = 10)` trong tiêu đề hoặc cấu hình tại tab *Format & Analytics*.
- **Đường Mục Tiêu (Constant Line)**: Ghi `(Kèm Constant Line mục tiêu 80%)` hoặc nhập `Constant Line Value`.
- **Small Multiples, Secondary Y-Axis, Breakdown, Play Axis, Sorting (Asc/Desc), Legend Position, Data Labels, Colors, Border Radius**.

---

## II. Cách Chạy Tự Động Với File `CSV` Và `Requirement.md` Bất Kỳ

### Cách 1: Chạy trực tiếp trên Giao diện Web UI (Khuyên dùng)
1. Nhấp đúp vào `run_studio.bat` (lần đầu chạy sẽ tự tạo `.venv` và cài thư viện từ `requirements.txt`, sau đó tự mở trình duyệt).
2. Tại khung **"⚡ Nạp File CSV & Requirement.md Bất Kỳ (Auto-Pipeline A–Z)"** ở đầu trang:
   - Chọn/tải lên file `.csv` và file `Requirement.md` (hoặc dùng thử ngay `sample_data/sample_sales.csv` và `Requirement_Template.md`).
   - Bấm **"⚡ Chạy Tự Động Toàn Trình (Clean → ETL → Star Schema → DAX → Sinh Power BI)"**.
3. Kiểm tra kết quả đối soát DAX tại Tab **📊 Kiểm Toán Dữ Liệu & KPI**, tinh chỉnh bố cục/biểu đồ nếu cần, rồi bấm **"🚀 Mở Trực Tiếp Trên Power BI Desktop"**.

### Cách 2: Chạy qua dòng lệnh (CLI)
```powershell
$env:PYTHONPATH = "."
python src/main.py --csv "sample_data/sample_sales.csv" --req "Requirement_Template.md" --project-name "Sales_Demo" --open-pbi
```
