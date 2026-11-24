# Auto-PBI Dashboard Studio (Local Portable Edition)

**Auto-PBI Dashboard Studio** là công cụ chạy hoàn toàn cục bộ (local) giúp tự động hóa từ A–Z quy trình chuyển đổi **bất kỳ file `.csv` nào** + **file đặc tả nghiệp vụ `Requirement.md`** thành:
- **Data Warehouse chuẩn Star Schema** (Parquet + Clean CSV trong `data_warehouse/`)
- **Bộ DAX Measures & Báo cáo Kiểm toán Dữ liệu / Đối soát KPI độc lập** (`reports/`)
- **Dự án Power BI Desktop hoàn chỉnh (`.pbip` & `.pbit`)** trong `output_pbi/` với đầy đủ **66+ loại biểu đồ Power BI** (44 built-in + 22+ AppSource/Custom Visuals tải 1-click ngay trên Web UI)
- **Web UI trực quan** để xem trước canvas 16:9, chỉnh sửa Field Wells, Format & Analytics, DAX và mở/nạp dữ liệu trực tiếp vào Power BI Desktop.

> **Bảo mật & Độc lập cho nhiều người dùng**: Mọi dữ liệu bạn nạp (`inputs/`, `data_warehouse/`, `output_pbi/`, `reports/`, `config/project_blueprint.json`) đều chỉ nằm cục bộ trong thư mục máy của riêng bạn.

---

## 1. Yêu Cầu Môi Trường
- **Windows 10 / 11**
- **Python 3.10+** (khi cài nhớ tích chọn *"Add python.exe to PATH"*)
- **Power BI Desktop** (để mở file `.pbip` / `.pbit` đầu ra)

---

## 2. Khởi Chạy Nhanh (3 Bước)
1. Giải nén thư mục phần mềm vào một thư mục bất kỳ trên máy bạn.
2. Nhấp đúp vào **`run_studio.bat`**:
   - Lần chạy đầu tiên sẽ tự động tạo môi trường ảo `.venv` và cài các thư viện trong `requirements.txt` (`Flask`, `pandas`, `numpy`, `pyarrow`, `PyYAML`, `requests`).
   - Trình duyệt sẽ tự động mở Web UI tại `http://127.0.0.1:8505` (tự động chọn cổng trống nếu 8505 đang bận).
3. Trên Web UI:
   - Bấm **👁️ Xem mẫu** / **📋 Copy mẫu** `Requirement_Template.md` ngay tại khung nạp CSV để viết yêu cầu của bạn (hoặc thử ngay bộ dữ liệu mẫu `sample_data/sample_sales.csv` + `Requirement_Template.md`).
   - Bấm **"⚡ Chạy Tự Động A–Z"** → Kiểm tra đối soát KPI tại Tab **📊 Kiểm Toán Dữ Liệu & KPI** → Bấm **"🚀 Mở Trực Tiếp Trên Power BI Desktop"**.

---

## 3. Chạy Qua Dòng Lệnh (CLI)

- **Chạy thử bộ dữ liệu mẫu đi kèm**:
  ```powershell
  .\run_auto_pbi.bat
  ```
- **Chạy với file CSV & Requirement.md bất kỳ**:
  ```powershell
  $env:PYTHONPATH = "."
  python src/main.py --csv "duong_dan/du_lieu.csv" --req "duong_dan/Requirement.md" --project-name "Ten_Du_An" --open-pbi
  ```
- **Mở Web UI từ dòng lệnh**:
  ```powershell
  $env:PYTHONPATH = "."
  python src/main.py --web --port 8505
  ```
- **Chỉ biên dịch lại Power BI & đối soát lại KPI (bỏ qua bước ETL nếu CSV không đổi)**:
  ```powershell
  $env:PYTHONPATH = "."
  python src/main.py --skip-etl
  ```

---

## 4. Cấu Trúc Thư Mục
- `run_studio.bat` / `run_auto_pbi.bat`: File khởi chạy nhanh Web UI và CLI (portable, không phụ thuộc đường dẫn cố định).
- `requirements.txt`: Danh sách thư viện Python cần thiết.
- `Requirement_Template.md` & `HUONG_DAN_REQUIREMENT.md`: Biểu mẫu chuẩn và hướng dẫn viết đặc tả nghiệp vụ.
- `sample_data/sample_sales.csv`: File CSV mẫu khớp với `Requirement_Template.md` để chạy thử ngay.
- `src/`: Mã nguồn bộ biên dịch, ETL Star Schema, trình sinh Power BI (`.pbip`/`.pbit`), bộ đối soát DAX độc lập, kho AppSource 1-click và Web UI.
- `config/appsource_marketplace_index.json`: Chỉ mục 1.300+ Custom Visuals từ AppSource để tìm kiếm & cài đặt 1-click.
- `inputs/`, `custom_visuals/`, `data_warehouse/`, `output_pbi/`, `reports/`: Thư mục làm việc cục bộ của từng người dùng (bắt đầu hoàn toàn trống).
