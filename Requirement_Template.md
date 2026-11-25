# ĐẶC TẢ PHÂN TÍCH NGHIỆP VỤ VÀ THIẾT KẾ DASHBOARD POWER BI

## Đề tài: Phân tích hiệu quả kinh doanh bán hàng (FILE MẪU – hãy thay bằng đề tài của bạn)

- Phiên bản: 1.0
- Nền tảng: Power BI Desktop
- Nguồn dữ liệu: file CSV bạn nạp vào ô "File CSV Đầu Vào" (mẫu này khớp với `sample_data/sample_sales.csv`)
- Phương pháp: Star Schema, ETL bằng Python, phân tích bằng DAX
- Trang Data Quality (kiểm toán chất lượng dữ liệu) được phần mềm tự động thêm vào cuối báo cáo

> **Cách dùng mẫu này (3 bước)**
> 1. Sao chép file, giữ nguyên cấu trúc các mục I → III và các khối `# DASHBOARD`.
> 2. Thay tên cột, tên measure, tiêu đề bằng của bạn. **Tên cột phải trùng đúng tên trong file CSV** (không phân biệt hoa/thường).
> 3. Nạp CSV + file này vào web → bấm "Chạy Tự Động A–Z". Mọi thứ sau khi bạn sửa file này sẽ được biên dịch lại, kể cả tab "Kiểm toán dữ liệu & KPI".

---

# QUY ƯỚC VIẾT FILE (đọc xong có thể xóa mục này)

Phần mềm đọc file bằng cấu trúc Markdown, vì vậy hãy giữ đúng các quy ước sau:

| Cần mô tả | Cách viết để phần mềm hiểu |
|---|---|
| Tên đề tài | Dòng `## Đề tài: ...` |
| Loại của từng cột CSV | Bảng ở mục I, cột đầu tiên là `Thuộc tính`, cột thứ hai là `Nhóm`; Nhóm là một trong `Date`, `Dimension`, `Measure`, `Flag` |
| KPI dạng ngắn | Bảng ở mục III có hai cột `KPI` và `Công thức`; công thức ngắn gồm `COUNTROWS(...)`, `SUM(cột)`, `AVG(cột)`, `MIN(cột)`, `MAX(cột)`, `MEDIAN(cột)`, `DISTINCTCOUNT(cột)` |
| KPI dạng DAX đầy đủ | Khối mã bắt đầu bằng ba dấu huyền kèm chữ DAX; dòng đầu có dạng `Tên Measure = Biểu thức`; tham chiếu cột dạng `'Fact_Main'[TênCột]` |
| Một trang dashboard | Dòng `# DASHBOARD <số>: <MÃ> – <Tên trang>` (dấu gạch ngang dài hoặc ngắn đều được) |
| Slicer của trang | Mục `## Slicer` chứa bảng có cột `Slicer`, `Thuộc tính`, `Kiểu` (`Dropdown` hoặc `Between`); tối đa 6 slicer mỗi trang |
| KPI Card của trang | Mục `## KPI Cards` chứa bảng có cột `KPI`; tối đa 6 thẻ mỗi trang |
| Một biểu đồ | Dòng `### <MÃ><số trang>-<số thứ tự> – <Tên biểu đồ>`, ví dụ `### EX01-03 – Tên`; tối đa 8 biểu đồ mỗi trang |
| Loại biểu đồ | Dòng `Loại: ...` trong biểu đồ; xem bảng loại biểu đồ ở cuối file này |
| Gắn dữ liệu vào biểu đồ | Các dòng `- Khóa: giá trị`; khóa hợp lệ gồm `X-axis`, `Axis`, `Category`, `Rows`, `Columns`, `Y-axis`, `Value`, `Values`, `Column Y-axis`, `Line Y-axis`, `Legend`, `Details`, `Size`, `Breakdown`, `Small multiples`, `Play Axis`, `Goal`, `Explain by`, `Tooltips` |
| Nhiều trường trong một ô | Ngăn cách bằng dấu phẩy, ví dụ `- Y-axis: Total Revenue, Total Profit` |
| Lọc Top N | Ghi `(Top N Filter = 10)` ngay cạnh dòng `Loại:` hoặc trong tiêu đề biểu đồ |
| Đường mục tiêu | Trong thân biểu đồ ghi `Constant Line mục tiêu 80%` (hoặc `mục tiêu 0.8`) |

Lưu ý quan trọng:

- Tên measure ở KPI Card và ở biểu đồ phải **trùng tên** measure đã định nghĩa ở mục III (hoặc measure tự sinh `Total <cột số>`, `Avg <cột số>`, `P90 <cột số>`, `<cột cờ> Count`, `<cột cờ> Rate`).
- Các cột dẫn xuất tùy biến (nhóm khoảng giá trị, nhãn trạng thái...) **không** được tự tạo: hãy tạo sẵn trong CSV hoặc dùng DAX ở mục III.
- Không hiển thị `0` thay cho dữ liệu thiếu; phần mềm giữ `NULL` và loại bản ghi trùng hoàn toàn.

---

# I. TỪ ĐIỂN DỮ LIỆU NGUỒN

| Thuộc tính | Nhóm | Ý nghĩa |
|---|---|---|
| `OrderDate` | Date | Ngày phát sinh đơn hàng (dùng tạo bảng `Dim_Date`) |
| `Region` | Dimension | Khu vực kinh doanh (tách bảng `Dim_Region`, phân nhóm Pareto ABC) |
| `Category` | Dimension | Nhóm sản phẩm (tách bảng `Dim_Category`) |
| `CustomerSegment` | Dimension | Phân khúc khách hàng (tách bảng `Dim_CustomerSegment`) |
| `Revenue` | Measure | Doanh thu của đơn hàng |
| `Cost` | Measure | Giá vốn của đơn hàng |
| `Quantity` | Measure | Số lượng bán |
| `IsReturned` | Flag | Cờ hoàn trả: `1` = hoàn trả, `0` = bình thường |

---

# II. QUY TẮC LÀM SẠCH DỮ LIỆU (ETL TỰ ĐỘNG THỰC THI)

> Phần mềm **đọc trực tiếp bảng dưới đây và tự động làm sạch dữ liệu** trước khi tạo Star Schema và Dashboard. Kết quả từng bước (số dòng loại bỏ, số ô chuẩn hóa) được ghi vào Tab **Kiểm Toán Dữ Liệu & KPI**.
>
> Các hành động hỗ trợ: `drop_duplicates`, `format_date` (`dd/mm/yyyy`, `dd-mm-yyyy`, `yyyy-mm-dd`, `mm/dd/yyyy`), `drop_invalid_date`, `cast_type` (`int`, `float`, `float_vn`, `string`, `bool`, `date`), `clean_numeric`, `filter` (`>= 0`, `> 0`, `between 0 and 1000`, `not_null`), `drop_null`, `fillna` (`0`, `mean`, `median`, `mode`, `Unknown`), `trim`, `trim_upper`, `trim_lower`, `trim_title`, `drop_outliers` (`iqr` / `p01_p99`), `clip_outliers` (`iqr` / `p01_p99`), `flag_01`.

| Quy tắc / Cột | Hành động | Điều kiện / Giá trị |
|---|---|---|
| `Duplicates` | `drop_duplicates` | `ALL` |
| `OrderDate` | `format_date` | `dd/mm/yyyy` |
| `Revenue` | `clean_numeric` | Xóa ký tự `$`, `,`, `%` và ép kiểu số |
| `Revenue` | `filter` | `>= 0` |
| `Cost` | `filter` | `>= 0` |
| `Quantity` | `cast_type` | `int` |
| `Quantity` | `filter` | `> 0` |
| `Region` | `trim` | Chuẩn hóa khoảng trắng đầu/cuối |
| `Region` | `fillna` | `Unknown` |
| `IsReturned` | `flag_01` | Chuẩn hóa về `{0, 1}` |

---

# III. KPI VÀ CÔNG THỨC DAX

## Bảng KPI dạng ngắn

| KPI | Công thức | Đơn vị |
|---|---|---|
| Total Orders | COUNTROWS(Fact_Main) | Đơn |
| Total Revenue | SUM(Revenue) | USD |
| Total Cost | SUM(Cost) | USD |
| Total Quantity | SUM(Quantity) | Cái |
| Avg Revenue | AVG(Revenue) | USD |

## Công thức DAX đầy đủ

```DAX
Total Profit =
SUM('Fact_Main'[Revenue]) - SUM('Fact_Main'[Cost])
```

```DAX
Profit Margin % =
DIVIDE(
    SUM('Fact_Main'[Revenue]) - SUM('Fact_Main'[Cost]),
    SUM('Fact_Main'[Revenue])
)
```

```DAX
Return Rate % =
DIVIDE(
    CALCULATE(COUNTROWS('Fact_Main'), 'Fact_Main'[IsReturned] = 1),
    COUNTROWS('Fact_Main')
)
```

```DAX
Target Margin % = 0.25
```

---

# DASHBOARD 01: EX-01 – EXECUTIVE OVERVIEW

## Slicer

| Slicer | Thuộc tính | Kiểu |
|---|---|---|
| Date Range | OrderDate | Between |
| Region | Region | Dropdown |
| Category | Category | Dropdown |
| Customer Segment | CustomerSegment | Dropdown |

## KPI Cards

| KPI | Nội dung |
|---|---|
| Total Orders | Tổng số đơn hàng |
| Total Revenue | Tổng doanh thu |
| Total Profit | Tổng lợi nhuận |
| Profit Margin % | Tỷ suất lợi nhuận |
| Avg Revenue | Doanh thu trung bình mỗi đơn |
| Return Rate % | Tỷ lệ hoàn trả |

## Danh sách biểu đồ

### EX01-01 – Xu hướng doanh thu và lợi nhuận theo thời gian

Loại: Line Chart
- X-axis: OrderDate
- Y-axis: Total Revenue, Total Profit

### EX01-02 – Cơ cấu doanh thu theo nhóm sản phẩm

Loại: Donut Chart
- Category: Category
- Values: Total Revenue

### EX01-03 – Lợi nhuận theo khu vực (Top N Filter = 5)

Loại: Horizontal Bar Chart
- Axis: Region
- Value: Total Profit

### EX01-04 – Doanh thu và giá vốn theo phân khúc khách hàng

Loại: Clustered Column Chart
- X-axis: CustomerSegment
- Y-axis: Total Revenue, Total Cost

### EX01-05 – Ma trận lợi nhuận Khu vực × Nhóm sản phẩm

Loại: Matrix
- Rows: Region
- Columns: Category
- Values: Total Profit

### EX01-06 – Bảng tổng hợp theo nhóm sản phẩm

Loại: Table
- Columns: Category, Total Orders, Total Revenue, Total Profit, Profit Margin %

---

# DASHBOARD 02: AN-02 – PHÂN TÍCH CHUYÊN SÂU

## Slicer

| Slicer | Thuộc tính | Kiểu |
|---|---|---|
| Date Range | OrderDate | Between |
| Region | Region | Dropdown |
| Category | Category | Dropdown |

## KPI Cards

| KPI | Nội dung |
|---|---|
| Total Revenue | Tổng doanh thu |
| Total Profit | Tổng lợi nhuận |
| Profit Margin % | Tỷ suất lợi nhuận |
| Return Rate % | Tỷ lệ hoàn trả |

## Danh sách biểu đồ

### AN02-01 – Doanh thu (cột) và tỷ suất lợi nhuận (đường)

Loại: Line and Clustered Column Chart
- X-axis: OrderDate
- Column Y-axis: Total Revenue
- Line Y-axis: Profit Margin %

### AN02-02 – Tỷ suất lợi nhuận theo thời gian, so với mục tiêu

Loại: Line Chart
- X-axis: OrderDate
- Y-axis: Profit Margin %
- Ghi chú: Constant Line mục tiêu 25%

### AN02-03 – Quy mô, hiệu quả và doanh thu theo khu vực

Loại: Scatter Chart
- Details: Region
- X-axis: Total Orders
- Y-axis: Profit Margin %
- Size: Total Revenue

### AN02-04 – Cơ cấu doanh thu (Treemap)

Loại: Treemap
- Category: Category
- Values: Total Revenue

### AN02-05 – Tỷ suất lợi nhuận so với mục tiêu (Gauge)

Loại: Gauge
- Value: Profit Margin %
- Goal: Target Margin %

### AN02-06 – Đóng góp lợi nhuận theo khu vực (Waterfall)

Loại: Waterfall Chart
- Category: Region
- Breakdown: Category
- Value: Total Profit

---

# PHỤ LỤC – DANH SÁCH LOẠI BIỂU ĐỒ HỖ TRỢ CHO DÒNG `Loại:`

Ghi tên tiếng Anh như trong Power BI (không phân biệt hoa/thường). Phần mềm hỗ trợ 66 loại; các loại thông dụng nhất:

| Nhóm | Giá trị dùng cho `Loại:` |
|---|---|
| Cột / Thanh | Stacked Bar, Stacked Column, Clustered Bar, Clustered Column, 100% Stacked Bar, 100% Stacked Column, Ribbon Chart |
| Đường / Miền / Kết hợp | Line Chart, Area Chart, Stacked Area, 100% Stacked Area, Line and Stacked Column, Line and Clustered Column |
| Đặc biệt | Waterfall Chart, Funnel Chart, Scatter Chart, Treemap, Gauge, KPI Visual |
| Tròn | Pie Chart, Donut Chart |
| Bảng | Table, Matrix, Heatmap |
| Bản đồ | Map, Filled Map, Shape Map, Azure Map |
| AI | Decomposition Tree, Key Influencers, Smart Narrative, Q&A Visual |
| Custom Visual | Sankey, Word Cloud, Chord, Bullet Chart, Tornado, Gantt, Radar, Sunburst... (cài ở tab "Thư Viện Chart" trên web) |

Danh sách đầy đủ và các ô dữ liệu (field wells) của từng loại xem ở tab "Thư Viện Toàn Bộ Chart Power BI" trên web.

# PHỤ LỤC – KIỂM TRA TRƯỚC KHI CHẠY

- [ ] Tên cột trong mục I trùng đúng tên cột trong file CSV
- [ ] Mỗi cột ngày có đúng một dòng nhóm `Date` đầu tiên (đó là cột ngày chính tạo bảng lịch)
- [ ] Mỗi KPI Card và mỗi biểu đồ chỉ dùng measure đã được định nghĩa ở mục III hoặc measure tự sinh
- [ ] Mỗi trang có tối đa 6 slicer, 6 KPI Card, 8 biểu đồ
- [ ] Mã biểu đồ có dạng chữ-số-gạch-số (ví dụ `EX01-01`, `AN02-03`)
