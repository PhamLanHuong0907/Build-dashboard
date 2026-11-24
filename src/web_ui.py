"""
Interactive Web UI for Auto-PBI Dashboard Studio (Power BI Desktop-Grade Visual Builder).
Features:
- Full Catalog of 66+ Power BI Visuals (44 Built-in + 22 Microsoft AppSource Samples + Custom .pbiviz Importer)
- Dynamic Power BI Visualizations Inspector:
  * "Build Visual" pane with EVERY exact Field Well (X-axis, Y-axis, Secondary Y-axis, Legend,
    Small Multiples, Tooltips, Play Axis, Size, Breakdown, Min/Max/Target, Indicator/TrendAxis/Goal,
    Analyze/ExplainBy/ExpandBy, Location/Latitude/Longitude, Rows/Columns/Values, Python/R scripts,
    and all AppSource custom roles)
  * "Format & Analytics" pane (Title, Legend, Data Labels, Axes, Sorting, Top N / Bottom N Filter,
    Constant Target Line, Colors, Border, Layout Presets)
- Universal CSV + Requirement.md One-Click A-Z Pipeline Launcher
- Live 16:9 Click-to-Edit Canvas Preview
- Direct Power BI Desktop Launcher & Live Tabular Data Refresh
"""
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, List
from flask import Flask, jsonify, render_template_string, request

from src.parser.spec_parser import SpecParser
from src.pbi_generator.pbip_packager import generate_pbi_artifacts
from src.pbi_generator.visual_catalog import get_full_visual_catalog, inspect_pbiviz_package
from src.pbi_generator import marketplace
from src.pbi_connector.dax_validator import run_kpi_validation
from src.pbi_connector.live_refresh import refresh_running_powerbi
from src.main import launch_powerbi_desktop, run_full_pipeline


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Auto-PBI Studio – Thiết Kế Toàn Bộ Biểu Đồ Power BI</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #1e293b;
      --card: #334155;
      --border: #475569;
      --text: #f8fafc;
      --muted: #94a3b8;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --accent: #8b5cf6;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }
    header {
      background: #020617;
      border-bottom: 1px solid var(--border);
      padding: 12px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
      gap: 12px;
      flex-wrap: wrap;
    }
    .brand h1 { font-size: 17px; font-weight: 700; color: #60a5fa; }
    .brand p { font-size: 11px; color: var(--muted); }
    .actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    button {
      cursor: pointer;
      border: none;
      border-radius: 6px;
      padding: 8px 13px;
      font-size: 12px;
      font-weight: 600;
      color: white;
      background: var(--primary);
      transition: all 0.15s;
    }
    button:hover { background: var(--primary-hover); }
    button.btn-success { background: var(--success); }
    button.btn-success:hover { background: #059669; }
    button.btn-warning { background: var(--warning); color: #0f172a; }
    button.btn-accent { background: var(--accent); }
    button.btn-danger { background: var(--danger); padding: 4px 9px; font-size: 11px; }
    button.btn-secondary { background: #475569; }
    button.btn-sm { padding: 5px 10px; font-size: 11px; }

    .tabs {
      display: flex;
      gap: 6px;
      background: #090d16;
      padding: 10px 20px 0;
      border-bottom: 1px solid var(--border);
      overflow-x: auto;
    }
    .tab {
      padding: 9px 16px;
      cursor: pointer;
      border-radius: 8px 8px 0 0;
      background: var(--panel);
      color: var(--muted);
      font-weight: 600;
      font-size: 13px;
      border: 1px solid transparent;
      white-space: nowrap;
    }
    .tab.active {
      background: var(--bg);
      color: #60a5fa;
      border-color: var(--border);
      border-bottom-color: var(--bg);
    }
    .container { padding: 18px 20px; max-width: 1720px; margin: 0 auto; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 16px;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
      gap: 10px;
      flex-wrap: wrap;
    }
    .panel-header h2 { font-size: 14px; color: #93c5fd; }

    label { display: block; font-size: 11px; color: var(--muted); margin-bottom: 3px; font-weight: 600; }
    input, select, textarea {
      width: 100%;
      padding: 6px 9px;
      border-radius: 5px;
      border: 1px solid var(--border);
      background: #0f172a;
      color: var(--text);
      font-size: 12px;
      margin-bottom: 8px;
    }
    input[type="checkbox"] { width: auto; margin-right: 6px; }
    input[type="color"] { height: 32px; padding: 2px; cursor: pointer; }
    textarea { font-family: Consolas, monospace; }

    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { padding: 7px 9px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }
    th { background: #0f172a; color: #93c5fd; font-weight: 600; }
    td input, td select { margin-bottom: 0; }

    .dash-selector { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
    .dash-pill {
      padding: 7px 13px;
      border-radius: 6px;
      background: var(--card);
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid var(--border);
    }
    .dash-pill.active { background: var(--primary); border-color: #93c5fd; }

    /* 16:9 Canvas Preview */
    .canvas-preview-wrap { background: #020617; padding: 10px; border-radius: 8px; border: 1px solid var(--border); }
    .canvas-16-9 {
      position: relative;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #f1f5f9;
      border-radius: 6px;
      overflow: hidden;
      color: #0f172a;
    }
    .cv-box {
      position: absolute;
      border-radius: 4px;
      font-size: 10px;
      padding: 4px 6px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: center;
      box-shadow: 0 1px 2px rgba(0,0,0,0.15);
    }
    .cv-header { background: #0f172a; color: #fff; font-weight: 700; }
    .cv-slicer { background: #e2e8f0; border: 1px solid #94a3b8; color: #1e293b; }
    .cv-kpi { background: #ffffff; border: 1px solid #3b82f6; color: #0f172a; text-align: center; font-weight: 700; }
    .cv-visual {
      background: #ffffff;
      border: 1.5px solid #cbd5e1;
      color: #0f172a;
      justify-content: flex-start;
      cursor: pointer;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .cv-visual:hover, .cv-visual.selected {
      border-color: #2563eb;
      box-shadow: 0 0 0 2px rgba(37,99,235,0.35);
    }
    .cv-visual-title { font-weight: 700; font-size: 9px; background: #e2e8f0; padding: 2px 4px; margin: -4px -6px 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .cv-badge { display: inline-block; background: #2563eb; color: #fff; border-radius: 3px; padding: 1px 4px; font-size: 9px; width: fit-content; margin-bottom: 2px; }
    .cv-wells-mini { font-size: 8.5px; color: #334155; line-height: 1.25; }

    /* Power BI Inspector Modal / Drawer */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(2, 6, 23, 0.78);
      display: none;
      justify-content: center;
      align-items: flex-start;
      padding: 24px;
      z-index: 500;
      overflow-y: auto;
    }
    .modal-backdrop.open { display: flex; }
    .inspector-modal {
      background: #1e293b;
      border: 1px solid #60a5fa;
      border-radius: 10px;
      width: 100%;
      max-width: 1120px;
      overflow: hidden;
      box-shadow: 0 20px 50px rgba(0,0,0,0.65);
    }
    .inspector-head {
      background: #020617;
      padding: 14px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
    }
    .inspector-body { padding: 16px 18px; max-height: 78vh; overflow-y: auto; }
    .subtabs { display: flex; gap: 8px; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
    .subtab {
      padding: 6px 14px;
      border-radius: 6px;
      background: #0f172a;
      color: var(--muted);
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid var(--border);
    }
    .subtab.active { background: var(--primary); color: #fff; border-color: #93c5fd; }

    .well-card {
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 7px;
      padding: 10px 12px;
      margin-bottom: 10px;
    }
    .well-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }
    .well-title { font-size: 12px; font-weight: 700; color: #93c5fd; }
    .well-tag { font-size: 10px; padding: 1px 6px; border-radius: 99px; background: #334155; color: #cbd5e1; }
    .well-tag.req { background: #b45309; color: #fef3c7; }
    .well-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; min-height: 24px; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 8px;
      border-radius: 5px;
      font-size: 11px;
      font-weight: 600;
      background: #1d4ed8;
      color: #fff;
    }
    .chip.measure { background: #0f766e; }
    .chip button {
      background: transparent;
      padding: 0 3px;
      font-size: 11px;
      color: #e2e8f0;
    }
    .chip button:hover { color: #fca5a5; background: transparent; }
    .well-add-row { display: grid; grid-template-columns: 1fr 1fr 110px; gap: 6px; }
    .well-add-row select { margin-bottom: 0; }

    /* Visual Catalog Grid */
    .catalog-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(295px, 1fr));
      gap: 12px;
    }
    .vcat-card {
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 8px;
    }
    .vcat-card:hover { border-color: #60a5fa; }
    .vcat-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
    .vcat-name { font-size: 13px; font-weight: 700; color: #f8fafc; }
    .vcat-vi { font-size: 11px; color: #93c5fd; }
    .vcat-src {
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 700;
      white-space: nowrap;
    }
    .src-builtin { background: #065f46; color: #a7f3d0; }
    .src-appsource { background: #5b21b6; color: #ddd6fe; }
    .src-pbiviz { background: #9a3412; color: #fed7aa; }
    .vcat-roles { display: flex; flex-wrap: wrap; gap: 4px; }
    .role-pill { font-size: 10px; background: #1e293b; border: 1px solid #475569; border-radius: 4px; padding: 1px 5px; color: #cbd5e1; }

    .status-toast {
      position: fixed;
      bottom: 20px;
      right: 24px;
      padding: 14px 20px;
      border-radius: 8px;
      background: #059669;
      color: white;
      font-weight: 600;
      font-size: 13px;
      box-shadow: 0 8px 20px rgba(0,0,0,0.4);
      display: none;
      z-index: 999;
      max-width: 540px;
    }
    .stat-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 16px; }
    .stat-box { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 10px; text-align: center; }
    .stat-box .val { font-size: 18px; font-weight: 700; color: #60a5fa; }
    .stat-box .lbl { font-size: 11px; color: var(--muted); }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>⚡ Auto-PBI Dashboard Studio – Full Power BI Visuals (<span id="hdr-vcount">66</span>+ Charts)</h1>
      <p>Thiết kế đầy đủ Field Wells, Format, Top N, Constant Line, Python/R, AppSource & .pbiviz như Power BI Desktop</p>
    </div>
    <div class="actions">
      <button class="btn-success" onclick="saveAndGeneratePBI()">💾 1. Lưu & Sinh File Power BI</button>
      <button onclick="refreshLivePowerBI()">🔄 2. Nạp Dữ Liệu Vào Power BI Đang Mở</button>
      <button class="btn-warning" onclick="openInPowerBIDesktop()">🚀 3. Lưu Thay Đổi & Mở Lại Power BI Desktop</button>
    </div>
  </header>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('tab-dash')">1. Thiết Kế Dashboard & Slicer</div>
    <div class="tab" onclick="switchTab('tab-catalog')">2. Thư Viện Toàn Bộ Chart Power BI (<span id="cat-count">0</span>)</div>
    <div class="tab" onclick="switchTab('tab-dax')">3. Quản Lý DAX Measures (<span id="dax-count">0</span>)</div>
    <div class="tab" onclick="switchTab('tab-req')">4. Tài Liệu Requirement.md</div>
    <div class="tab" onclick="switchTab('tab-audit')">5. Kiểm Toán Dữ Liệu & KPI</div>
  </div>

  <div class="container">
    <!-- UNIVERSAL CSV + REQUIREMENT.MD AUTO-PIPELINE LAUNCHER -->
    <div class="panel" style="border-color:#3b82f6;background:#0f172a;">
      <div class="panel-header">
        <h2>⚡ Nạp File CSV & Requirement.md Bất Kỳ – Chạy Tự Động Toàn Trình (Clean → ETL → Star Schema → DAX → Power BI)</h2>
        <span style="font-size:11px;color:#93c5fd;">Hỗ trợ mọi file CSV & đặc tả Requirement.md theo chuẩn HUONG_DAN_REQUIREMENT.md</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 200px 250px;gap:10px;align-items:end;">
        <div>
          <label>Đường dẫn File CSV Đầu Vào (hoặc tải file lên)</label>
          <input type="text" id="pipe-csv-path" value="" placeholder="VD: inputs/sales.csv (hoặc tải file lên ở dưới)" style="margin-bottom:4px;" />
          <input type="file" id="pipe-csv-file" accept=".csv" onchange="uploadInputFile(this, 'csv')" style="margin-bottom:0;font-size:11px;padding:3px;" />
        </div>
        <div>
          <label>Đường dẫn File Đặc Tả Requirement.md (hoặc tải file lên)</label>
          <input type="text" id="pipe-req-path" value="" placeholder="VD: inputs/Requirement.md (hoặc tải file lên ở dưới)" style="margin-bottom:4px;" />
          <input type="file" id="pipe-req-file" accept=".md,.txt" onchange="uploadInputFile(this, 'req')" style="margin-bottom:0;font-size:11px;padding:3px;" />
        </div>
        <div>
          <label>Tên Dự Án Power BI</label>
          <input type="text" id="pipe-proj-name" value="My_Dashboard" style="margin-bottom:0;" />
        </div>
        <div>
          <button class="btn-success" style="width:100%;padding:11px;" onclick="runAutomatedPipeline()">⚡ Chạy Tự Động A–Z (ETL & Sinh PBI)</button>
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px;padding-top:10px;border-top:1px dashed #334155;">
        <span style="font-size:12px;color:#93c5fd;font-weight:600;">📄 Mẫu Requirement.md:</span>
        <button class="btn-secondary btn-sm" onclick="openDocModal('Requirement_Template.md','Requirement_Template.md – Mẫu đặc tả chuẩn')">👁️ Xem Requirement_Template.md</button>
        <button class="btn-accent btn-sm" onclick="copyDocByName('Requirement_Template.md')">📋 Copy nội dung mẫu</button>
        <button class="btn-secondary btn-sm" onclick="downloadDocByName('Requirement_Template.md')">⬇️ Tải mẫu về máy</button>
        <button class="btn-secondary btn-sm" onclick="openDocModal('HUONG_DAN_REQUIREMENT.md','Hướng dẫn viết Requirement.md')">📖 Hướng dẫn viết Requirement</button>
      </div>
      <div id="pipe-status-bar" style="margin-top:8px;font-size:12px;color:#10b981;display:none;"></div>
    </div>

    <!-- TAB 1: DASHBOARD & SLICER EDITOR -->
    <div id="tab-dash" class="tab-content active">
      <div class="dash-selector" id="dash-pills"></div>

      <div class="grid-2">
        <div class="panel">
          <div class="panel-header">
            <h2>Thông Tin Trang Dashboard</h2>
            <div style="display:flex;gap:6px;">
              <button class="btn-sm" onclick="addNewDashboard()">+ Thêm Trang Mới</button>
              <button class="btn-danger" onclick="deleteCurrentDashboard()">Xóa Trang Này</button>
            </div>
          </div>
          <div class="grid-2" style="gap:10px;">
            <div>
              <label>Mã Trang (ID)</label>
              <input type="text" id="d-id" onchange="updateCurrentDashMeta()" />
            </div>
            <div>
              <label>Tên Tab Trên Power BI</label>
              <input type="text" id="d-name" onchange="updateCurrentDashMeta()" />
            </div>
          </div>
          <label>Tiêu Đề Header Chính (Banner Title)</label>
          <input type="text" id="d-title" onchange="updateCurrentDashMeta()" />
          <label>Mô Tả Phụ (Subtitle)</label>
          <input type="text" id="d-subtitle" onchange="updateCurrentDashMeta()" />
        </div>

        <div class="panel">
          <div class="panel-header">
            <h2>Xem Trước Bố Cục 16:9 (Nhấp Vào Biểu Đồ Để Mở Power BI Field Wells)</h2>
            <span style="font-size:11px;color:#93c5fd;">1280 × 720 px</span>
          </div>
          <div class="canvas-preview-wrap">
            <div class="canvas-16-9" id="canvas-preview"></div>
          </div>
        </div>
      </div>

      <!-- SLICERS EDITOR -->
      <div class="panel">
        <div class="panel-header">
          <h2>Bộ Lọc Slicer Trên Trang (Hỗ trợ Classic Slicer, Button Slicer, List Slicer, Text Slicer & Sync Groups)</h2>
          <button class="btn-sm" onclick="addSlicer()">+ Thêm Slicer</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Mã</th>
              <th>Tiêu đề</th>
              <th>Loại Slicer Power BI</th>
              <th>Bảng</th>
              <th>Thuộc tính (Column)</th>
              <th>Chế độ</th>
              <th>Nhóm Đồng Bộ (Sync)</th>
              <th>Xóa</th>
            </tr>
          </thead>
          <tbody id="slicers-tbody"></tbody>
        </table>
      </div>

      <!-- KPI CARDS EDITOR -->
      <div class="panel">
        <div class="panel-header">
          <h2>Thẻ Chỉ Số KPI Cards (Hỗ trợ Card Classic & New Card Visual)</h2>
          <button class="btn-sm" onclick="addKpiCard()">+ Thêm KPI Card</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Mã Card</th>
              <th>Tiêu đề Card</th>
              <th>Loại Card</th>
              <th>DAX Measure Ánh Xạ</th>
              <th>Xóa</th>
            </tr>
          </thead>
          <tbody id="kpis-tbody"></tbody>
        </table>
      </div>

      <!-- VISUALS LIST -->
      <div class="panel">
        <div class="panel-header">
          <h2>Danh Sách Biểu Đồ & Visuals Trên Trang (Hỗ Trợ Toàn Bộ 66+ Loại Chart & Field Wells Đầy Đủ)</h2>
          <div style="display:flex;gap:8px;">
            <button class="btn-accent btn-sm" onclick="switchTab('tab-catalog')">📚 Chọn Từ Thư Viện 66+ Charts</button>
            <button class="btn-sm" onclick="addVisual('clusteredBarChart')">+ Thêm Biểu Đồ Nhanh</button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width:90px;">Mã</th>
              <th>Tiêu đề Biểu đồ</th>
              <th style="width:240px;">Loại Biểu Đồ Power BI</th>
              <th>Tóm Tắt Field Wells (Các Ô Dữ Liệu Đã Gắn)</th>
              <th style="width:170px;">Vị trí (X, Y, W, H)</th>
              <th style="width:175px;">Thao Tác</th>
            </tr>
          </thead>
          <tbody id="visuals-tbody"></tbody>
        </table>
      </div>
    </div>

    <!-- TAB 2: FULL VISUAL CATALOG & PBIVIZ IMPORTER -->
    <div id="tab-catalog" class="tab-content">
      <div class="panel" style="border-color:#06b6d4;">
        <div class="panel-header">
          <h2>🛒 Kho Custom Visual AppSource – Cài 1 Click Ngay Tại Đây (Không Cần Mở Link / Import Thủ Công)</h2>
          <span id="mp-count" style="font-size:11px;color:#67e8f9;"></span>
        </div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px;">
          <input type="text" id="mp-search" placeholder="🔍 Tìm visual (VD: sankey, gantt, bullet, word cloud, calendar, box plot...)" onkeydown="if(event.key==='Enter') searchMarketplace()" style="max-width:520px;margin-bottom:0;" />
          <button onclick="searchMarketplace()">Tìm trong kho</button>
          <span style="font-size:11px;color:#94a3b8;">Cần Internet. Tải trực tiếp gói .pbiviz về thư mục custom_visuals/ của bạn và đăng ký field wells tự động.</span>
        </div>
        <div class="catalog-grid" id="mp-results"></div>
      </div>

      <div class="panel" style="border-color:#8b5cf6;">
        <div class="panel-header">
          <h2>🧩 Nhập Custom Visual (.pbiviz) Trực Tiếp Từ Microsoft AppSource / GitHub Samples</h2>
          <span style="font-size:11px;color:#ddd6fe;">Tự động giải nén package.json & capabilities.json để lấy GUID + toàn bộ ô nhập dữ liệu (dataRoles)</span>
        </div>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
          <input type="file" id="pbiviz-upload" accept=".pbiviz" style="max-width:380px;margin-bottom:0;" />
          <button class="btn-accent" onclick="uploadPbiviz()">⬆️ Import .pbiviz Vào Thư Viện Phần Mềm</button>
          <a href="https://appsource.microsoft.com/en-us/marketplace/apps?product=power-bi-visuals" target="_blank" style="color:#93c5fd;font-size:12px;">🔗 Mở Microsoft AppSource Power BI Visuals</a>
          <a href="https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-types-for-reports-and-q-and-a" target="_blank" style="color:#93c5fd;font-size:12px;">🔗 Microsoft Learn Docs</a>
          <a href="https://learn.microsoft.com/en-us/power-bi/developer/visuals/samples" target="_blank" style="color:#93c5fd;font-size:12px;">🔗 Developer Visual Samples</a>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>📚 Thư Viện Toàn Bộ Biểu Đồ Power BI (Built-in + AppSource + Developer Samples)</h2>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <input type="text" id="cat-search" placeholder="🔍 Tìm chart (VD: Waterfall, Sankey, Gauge, Map, KPI, Tree, Bullet, Gantt...)" oninput="renderCatalogGrid()" style="width:320px;margin-bottom:0;" />
            <select id="cat-group-filter" onchange="renderCatalogGrid()" style="width:240px;margin-bottom:0;"></select>
            <select id="cat-src-filter" onchange="renderCatalogGrid()" style="width:180px;margin-bottom:0;">
              <option value="all">Tất cả nguồn</option>
              <option value="builtin">Built-in Power BI (44)</option>
              <option value="appsource">AppSource & Samples (22+)</option>
              <option value="imported_pbiviz">Đã Import .pbiviz</option>
            </select>
          </div>
        </div>
        <div class="catalog-grid" id="catalog-grid"></div>
      </div>
    </div>

    <!-- TAB 3: DAX MEASURES -->
    <div id="tab-dax" class="tab-content">
      <div class="panel">
        <div class="panel-header">
          <h2>Danh Mục DAX Measures Chuẩn Hóa</h2>
          <button class="btn-sm" onclick="addDaxMeasure()">+ Thêm DAX Measure</button>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width:190px;">Tên Measure</th>
              <th style="width:170px;">Thư mục</th>
              <th>Công thức DAX</th>
              <th style="width:100px;">Định dạng</th>
              <th style="width:220px;">Mô tả</th>
              <th style="width:55px;">Xóa</th>
            </tr>
          </thead>
          <tbody id="dax-tbody"></tbody>
        </table>
      </div>
    </div>

    <!-- TAB 4: REQUIREMENT.MD -->
    <div id="tab-req" class="tab-content">
      <div class="panel">
        <div class="panel-header">
          <h2>Tài Liệu Đặc Tả Nghiệp Vụ (Requirement.md)</h2>
          <button class="btn-success btn-sm" onclick="saveRequirementMd()">Lưu Tài Liệu Requirement.md</button>
        </div>
        <textarea id="req-md-editor" rows="28"></textarea>
      </div>
    </div>

    <!-- TAB 5: DATA QUALITY & KPI AUDIT -->
    <div id="tab-audit" class="tab-content">
      <div class="stat-grid" id="audit-top-stats"></div>
      <div class="grid-2">
        <div class="panel">
          <div class="panel-header"><h2>Đối Soát Từng DAX Measure Theo Requirement.md (Tính Độc Lập Bằng Python)</h2><button class="btn-sm" onclick="revalidateKpi()">🔄 Đối soát lại KPI theo Requirement hiện tại</button></div>
          <div id="audit-kpi-table" style="max-height:520px;overflow:auto;"></div>
        </div>
        <div class="panel">
          <div class="panel-header"><h2>Kiểm Toán Chất Lượng Dữ Liệu (Data Quality Audit)</h2></div>
          <div id="audit-dq-table" style="max-height:520px;overflow:auto;"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- POWER BI VISUAL INSPECTOR MODAL (BUILD VISUAL + FORMAT VISUAL) -->
  <div class="modal-backdrop" id="inspector-backdrop" onclick="if(event.target===this) closeInspector()">
    <div class="inspector-modal">
      <div class="inspector-head">
        <div>
          <h2 id="insp-heading" style="font-size:15px;color:#60a5fa;">⚙️ Power BI Visual Inspector</h2>
          <p id="insp-sub" style="font-size:11px;color:#94a3b8;"></p>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn-success" onclick="applyAndCloseInspector()">✅ Áp Dụng Thay Đổi</button>
          <button class="btn-secondary" onclick="closeInspector()">Đóng</button>
        </div>
      </div>
      <div class="inspector-body">
        <div class="grid-2" style="gap:12px;margin-bottom:10px;">
          <div>
            <label>Loại Biểu Đồ Power BI (Toàn bộ 66+ loại Built-in & AppSource)</label>
            <select id="insp-vtype" onchange="onInspectorVisualTypeChange(this.value)"></select>
          </div>
          <div>
            <label>Tiêu Đề Biểu Đồ (Title)</label>
            <input type="text" id="insp-title" oninput="syncInspectorBasicMeta()" />
          </div>
        </div>

        <div id="insp-appsource-box" style="display:none;background:#2e1065;border:1px solid #8b5cf6;border-radius:6px;padding:8px 12px;margin-bottom:12px;font-size:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
            <div>
              <strong>🧩 Custom Visual AppSource:</strong> <span id="insp-appsource-desc"></span>
            </div>
            <label style="display:flex;align-items:center;color:#f8fafc;margin:0;cursor:pointer;">
              <input type="checkbox" id="insp-use-native" onchange="syncInspectorBasicMeta()" />
              Xuất trực tiếp dạng AppSource Native (`publicCustomVisuals`) — bỏ chọn để dùng biểu đồ Built-in thay thế an toàn khi offline
            </label>
          </div>
        </div>

        <div class="subtabs">
          <div class="subtab active" id="subtab-btn-build" onclick="switchInspectorSubtab('build')">📊 Build Visual (Gắn Cột & DAX Measures Vào Các Ô Field Wells)</div>
          <div class="subtab" id="subtab-btn-format" onclick="switchInspectorSubtab('format')">🎨 Format & Analytics (Tiêu đề, Legend, Top N, Sắp xếp, Đường Mục Tiêu, Tọa độ)</div>
        </div>

        <!-- BUILD VISUAL PANE -->
        <div id="insp-pane-build">
          <div id="insp-wells-container"></div>
          <div id="insp-script-box" style="display:none;" class="well-card">
            <div class="well-head">
              <span class="well-title" id="insp-script-label">🐍 Mã Script (Python / R)</span>
            </div>
            <textarea id="insp-script-code" rows="8" oninput="syncInspectorBasicMeta()" placeholder="# Viết mã Python (matplotlib/seaborn) hoặc R (ggplot2) dùng biến dataset..."></textarea>
          </div>
        </div>

        <!-- FORMAT & ANALYTICS PANE -->
        <div id="insp-pane-format" style="display:none;">
          <div class="well-card">
            <div class="well-head">
              <span class="well-title">📐 Vị Trí & Kích Thước Trên Canvas 16:9 (1280 × 720 px)</span>
              <div style="display:flex;gap:5px;flex-wrap:wrap;">
                <button class="btn-secondary btn-sm" onclick="applyPosPreset(16,212,1248,492)">Toàn Màn Hình</button>
                <button class="btn-secondary btn-sm" onclick="applyPosPreset(16,212,618,240)">1/2 Trên-Trái</button>
                <button class="btn-secondary btn-sm" onclick="applyPosPreset(646,212,618,240)">1/2 Trên-Phải</button>
                <button class="btn-secondary btn-sm" onclick="applyPosPreset(16,462,618,242)">1/2 Dưới-Trái</button>
                <button class="btn-secondary btn-sm" onclick="applyPosPreset(646,462,618,242)">1/2 Dưới-Phải</button>
                <button class="btn-secondary btn-sm" onclick="applyPosPreset(16,212,410,240)">1/3 Trên-Trái</button>
                <button class="btn-secondary btn-sm" onclick="applyPosPreset(436,212,410,240)">1/3 Trên-Giữa</button>
                <button class="btn-secondary btn-sm" onclick="applyPosPreset(856,212,408,240)">1/3 Trên-Phải</button>
              </div>
            </div>
            <div class="grid-4">
              <div><label>X (px)</label><input type="number" id="fmt-x" onchange="syncInspectorFormat()" /></div>
              <div><label>Y (px)</label><input type="number" id="fmt-y" onchange="syncInspectorFormat()" /></div>
              <div><label>Width (px)</label><input type="number" id="fmt-w" onchange="syncInspectorFormat()" /></div>
              <div><label>Height (px)</label><input type="number" id="fmt-h" onchange="syncInspectorFormat()" /></div>
            </div>
          </div>

          <div class="grid-2">
            <div class="well-card">
              <div class="well-head"><span class="well-title">🏷️ Hiển Thị Tiêu Đề, Chú Giải (Legend) & Nhãn Dữ Liệu</span></div>
              <div class="grid-2" style="gap:8px;">
                <label style="display:flex;align-items:center;"><input type="checkbox" id="fmt-title-show" onchange="syncInspectorFormat()" /> Hiện Tiêu đề (Title)</label>
                <label style="display:flex;align-items:center;"><input type="checkbox" id="fmt-legend-show" onchange="syncInspectorFormat()" /> Hiện Chú giải (Legend)</label>
                <label style="display:flex;align-items:center;"><input type="checkbox" id="fmt-labels-show" onchange="syncInspectorFormat()" /> Hiện Nhãn số (Data Labels)</label>
                <label style="display:flex;align-items:center;"><input type="checkbox" id="fmt-border-show" onchange="syncInspectorFormat()" /> Hiện Khung viền (Border)</label>
                <label style="display:flex;align-items:center;"><input type="checkbox" id="fmt-xaxis-show" onchange="syncInspectorFormat()" /> Hiện Trục X (X-Axis)</label>
                <label style="display:flex;align-items:center;"><input type="checkbox" id="fmt-yaxis-show" onchange="syncInspectorFormat()" /> Hiện Trục Y (Y-Axis)</label>
              </div>
              <div class="grid-3" style="margin-top:8px;">
                <div>
                  <label>Vị trí Legend</label>
                  <select id="fmt-legend-pos" onchange="syncInspectorFormat()">
                    <option value="Top">Top</option>
                    <option value="Bottom">Bottom</option>
                    <option value="Left">Left</option>
                    <option value="Right">Right</option>
                    <option value="TopCenter">TopCenter</option>
                  </select>
                </div>
                <div>
                  <label>Căn lề Tiêu đề</label>
                  <select id="fmt-title-align" onchange="syncInspectorFormat()">
                    <option value="left">Trái (left)</option>
                    <option value="center">Giữa (center)</option>
                    <option value="right">Phải (right)</option>
                  </select>
                </div>
                <div>
                  <label>Cỡ chữ Tiêu đề (pt)</label>
                  <input type="number" id="fmt-title-size" value="10" onchange="syncInspectorFormat()" />
                </div>
              </div>
              <div class="grid-4">
                <div><label>Màu chữ Title</label><input type="color" id="fmt-title-color" value="#0f172a" onchange="syncInspectorFormat()" /></div>
                <div><label>Màu nền Title</label><input type="color" id="fmt-title-bg" value="#f1f5f9" onchange="syncInspectorFormat()" /></div>
                <div><label>Màu nền Chart</label><input type="color" id="fmt-bg-color" value="#ffffff" onchange="syncInspectorFormat()" /></div>
                <div><label>Màu Viền</label><input type="color" id="fmt-border-color" value="#cbd5e1" onchange="syncInspectorFormat()" /></div>
              </div>
            </div>

            <div class="well-card">
              <div class="well-head"><span class="well-title">📈 Analytics: Lọc Top N, Sắp Xếp & Đường Mục Tiêu (Constant Line)</span></div>
              <div class="grid-2" style="gap:8px;">
                <div>
                  <label>Lọc Top N (Để trống hoặc 0 = Không lọc)</label>
                  <input type="number" id="fmt-topn" min="0" placeholder="VD: 10 cho Top 10" onchange="syncInspectorFormat()" />
                </div>
                <div>
                  <label>Kiểu Top / Bottom</label>
                  <select id="fmt-topn-dir" onchange="syncInspectorFormat()">
                    <option value="Top">Top (Cao nhất)</option>
                    <option value="Bottom">Bottom (Thấp nhất)</option>
                  </select>
                </div>
              </div>
              <div class="grid-2" style="gap:8px;">
                <div>
                  <label>Sắp xếp theo Trường/Measure</label>
                  <select id="fmt-sort-field" onchange="syncInspectorFormat()"></select>
                </div>
                <div>
                  <label>Chiều Sắp Xếp</label>
                  <select id="fmt-sort-dir" onchange="syncInspectorFormat()">
                    <option value="Descending">Giảm dần (Descending)</option>
                    <option value="Ascending">Tăng dần (Ascending)</option>
                  </select>
                </div>
              </div>
              <div class="grid-3" style="gap:8px;margin-top:6px;">
                <div>
                  <label>Đường Mục Tiêu (Constant Line Value)</label>
                  <input type="number" step="any" id="fmt-const-val" placeholder="VD: 0.80 cho 80%" onchange="syncInspectorFormat()" />
                </div>
                <div>
                  <label>Nhãn Đường Mục Tiêu</label>
                  <input type="text" id="fmt-const-lbl" placeholder="VD: Mục tiêu OTP 80%" onchange="syncInspectorFormat()" />
                </div>
                <div>
                  <label>Màu Đường Mục Tiêu</label>
                  <input type="color" id="fmt-const-col" value="#ef4444" onchange="syncInspectorFormat()" />
                </div>
              </div>
              <div style="margin-top:6px;">
                <label>Bo góc khung viền (Border Radius px)</label>
                <input type="number" id="fmt-radius" value="6" onchange="syncInspectorFormat()" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- DOCUMENT VIEWER (Requirement template / guide) -->
  <div class="modal-backdrop" id="doc-backdrop" onclick="if(event.target===this) closeDocModal()">
    <div class="inspector-modal" style="max-width:980px;">
      <div class="inspector-head">
        <h2 id="doc-title" style="font-size:15px;color:#60a5fa;"></h2>
        <div style="display:flex;gap:8px;">
          <button class="btn-accent" id="doc-copy-btn">📋 Copy toàn bộ</button>
          <button class="btn-secondary" id="doc-download-btn">⬇️ Tải về</button>
          <button class="btn-secondary" onclick="closeDocModal()">Đóng</button>
        </div>
      </div>
      <div class="inspector-body">
        <textarea id="doc-body" readonly rows="30" style="font-size:12px;line-height:1.5;margin:0;"></textarea>
      </div>
    </div>
  </div>

  <div class="status-toast" id="toast"></div>

  <script>
    let blueprint = null;
    let visualCatalog = [];
    let schemaTables = {};
    let currentDashIdx = 0;
    let editingVisualIdx = -1;

    function showToast(msg, isError=false) {
      const t = document.getElementById('toast');
      t.style.background = isError ? '#ef4444' : '#059669';
      t.innerText = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 5000);
    }

    function switchTab(tabId) {
      const map = {'tab-dash':0, 'tab-catalog':1, 'tab-dax':2, 'tab-req':3, 'tab-audit':4};
      document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab')[map[tabId]].classList.add('active');
      document.getElementById(tabId).classList.add('active');
    }

    function getVisualMeta(vtype) {
      return visualCatalog.find(v => v.visualType === vtype) || visualCatalog[0];
    }

    function ensureVisualFieldWells(v) {
      if (v.field_wells && Object.keys(v.field_wells).length > 0) return v.field_wells;
      const w = {};
      if (v.type === 'lineStackedColumnComboChart' || v.type === 'lineClusteredColumnComboChart') {
        if (v.category) w.Category = [v.category];
        if (v.column_values) w.Y = [...v.column_values];
        if (v.line_values) w.Y2 = [...v.line_values];
        if (v.series) w.Series = [v.series];
      } else if (v.type === 'scatterChart') {
        if (v.details) w.Category = [v.details];
        else if (v.category) w.Category = [v.category];
        if (v.x_axis) w.X = [v.x_axis];
        if (v.y_axis) w.Y = [v.y_axis];
        if (v.size) w.Size = [v.size];
        if (v.series) w.Series = [v.series];
        if (v.play_axis) w.Play = [v.play_axis];
      } else if (v.type === 'tableEx') {
        if (v.columns) w.Values = [...v.columns];
        else if (v.values) w.Values = [...v.values];
      } else if (v.type === 'matrix') {
        if (v.rows) w.Rows = [...v.rows];
        if (v.columns) w.Columns = [...v.columns];
        if (v.values) w.Values = [...v.values];
      } else if (v.type === 'treemap') {
        if (v.category) w.Group = [v.category];
        if (v.series) w.Details = [v.series];
        if (v.values) w.Values = [...v.values];
      } else if (v.type === 'gauge') {
        if (v.values) w.Y = [v.values[0]];
        if (v.target_value) w.TargetValue = [v.target_value];
      } else if (v.type === 'kpi') {
        if (v.values) w.Indicator = [v.values[0]];
        if (v.category) w.TrendAxis = [v.category];
        if (v.target_value) w.Goal = [v.target_value];
      } else if (v.type === 'decompositionTreeVisual' || v.type === 'keyDriversVisual') {
        if (v.values) w.Analyze = [v.values[0]];
        if (v.explain_by) w.ExplainBy = [...v.explain_by];
        else if (v.category) w.ExplainBy = [v.category];
      } else if (v.type === 'cardVisual') {
        if (v.values) w.Data = [...v.values];
      } else {
        if (v.category) w.Category = [v.category];
        if (v.series) w.Series = [v.series];
        if (v.breakdown) w.Breakdown = [v.breakdown];
        if (v.small_multiples) w.Rows = [v.small_multiples];
        if (v.values) w.Y = [...v.values];
      }
      if (v.tooltips && v.tooltips.length) {
        const ft = (blueprint && blueprint.project && blueprint.project.fact_table_name) || 'Fact_Flight';
        w.Tooltips = v.tooltips.map(t => typeof t === 'string' ? {table: ft, measure: t} : t);
      }
      v.field_wells = w;
      return v.field_wells;
    }

    function summarizeWellsHtml(v) {
      const w = ensureVisualFieldWells(v);
      const parts = [];
      for (const [rk, items] of Object.entries(w)) {
        if (!items || !items.length) continue;
        const labels = items.map(it => it.measure ? `[${it.measure}]` : `${it.table}.${it.column}`);
        parts.push(`<span class="role-pill"><strong>${rk}:</strong> ${labels.join(', ')}</span>`);
      }
      if (v.format && v.format.top_n) parts.push(`<span class="role-pill" style="border-color:#f59e0b;color:#fde68a;">Top ${v.format.top_n}</span>`);
      if (v.format && v.format.constant_line_value !== undefined && v.format.constant_line_value !== '' && v.format.constant_line_value !== null) {
        parts.push(`<span class="role-pill" style="border-color:#ef4444;color:#fecaca;">Target: ${v.format.constant_line_value}</span>`);
      }
      return parts.join(' ') || '<span style="color:#64748b;">Chưa gắn dữ liệu</span>';
    }

    async function loadAllData() {
      const res = await fetch('/api/state');
      const data = await res.json();
      blueprint = data.blueprint;
      visualCatalog = data.visual_catalog || [];
      schemaTables = data.schema_tables || {};

      document.getElementById('hdr-vcount').innerText = visualCatalog.length;
      document.getElementById('cat-count').innerText = visualCatalog.length;

      if (blueprint && blueprint.project) {
        document.getElementById('pipe-csv-path').value = blueprint.project.source_csv || '';
        document.getElementById('pipe-req-path').value = blueprint.project.requirement_doc || '';
        document.getElementById('pipe-proj-name').value = blueprint.project.name || 'My_Dashboard';
      }
      document.getElementById('req-md-editor').value = data.requirement_md || '';

      populateCatalogCategoryFilter();
      populateInspectorVisualSelect();
      renderCatalogGrid();
      renderDashboardPills();
      renderCurrentDashboard();
      renderDaxTable();
      renderAuditTab(data.profiling, data.kpi_validation);
    }

    function populateCatalogCategoryFilter() {
      const sel = document.getElementById('cat-group-filter');
      const cats = [...new Set(visualCatalog.map(v => v.category))];
      sel.innerHTML = '<option value="all">Tất cả 11+ nhóm biểu đồ</option>' +
        cats.map(c => `<option value="${c}">${c}</option>`).join('');
    }

    function populateInspectorVisualSelect() {
      const sel = document.getElementById('insp-vtype');
      const groups = {};
      visualCatalog.forEach(v => {
        if (!groups[v.category]) groups[v.category] = [];
        groups[v.category].push(v);
      });
      sel.innerHTML = Object.entries(groups).map(([cat, list]) =>
        `<optgroup label="${cat}">` +
        list.map(v => `<option value="${v.visualType}">${v.icon} ${v.name} — ${v.name_vi}</option>`).join('') +
        `</optgroup>`
      ).join('');
    }

    function renderCatalogGrid() {
      const q = (document.getElementById('cat-search').value || '').toLowerCase();
      const g = document.getElementById('cat-group-filter').value || 'all';
      const src = document.getElementById('cat-src-filter').value || 'all';
      const grid = document.getElementById('catalog-grid');
      const filtered = visualCatalog.filter(v => {
        if (g !== 'all' && v.category !== g) return false;
        if (src === 'builtin' && v.source !== 'builtin') return false;
        if (src === 'appsource' && !v.source.startsWith('appsource')) return false;
        if (src === 'imported_pbiviz' && v.source !== 'imported_pbiviz') return false;
        if (q) {
          const hay = `${v.visualType} ${v.name} ${v.name_vi} ${v.description} ${(v.keywords||[]).join(' ')}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });
      grid.innerHTML = filtered.map(v => {
        const badgeCls = v.source === 'builtin' ? 'src-builtin' : (v.source === 'imported_pbiviz' ? 'src-pbiviz' : 'src-appsource');
        const badgeTxt = v.source === 'builtin' ? 'Built-in PBI' : (v.source === 'imported_pbiviz' ? '.pbiviz Đã cài' : 'AppSource / Sample');
        const rolesHtml = (v.roles || []).map(r => `<span class="role-pill">${r.label.split(' (')[0]}</span>`).join('');
        return `
          <div class="vcat-card">
            <div>
              <div class="vcat-top">
                <div>
                  <div class="vcat-name">${v.icon} ${v.name}</div>
                  <div class="vcat-vi">${v.name_vi}</div>
                </div>
                <span class="vcat-src ${badgeCls}">${badgeTxt}</span>
              </div>
              <p style="font-size:11px;color:#94a3b8;margin:6px 0;">${v.description}</p>
              <div class="vcat-roles">${rolesHtml || '<span class="role-pill">Layout / UI Element</span>'}</div>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;padding-top:8px;border-top:1px solid #1e293b;">
              <code style="font-size:10px;color:#64748b;">${v.visualType}</code>
              <button class="btn-sm" onclick="addVisualFromCatalog('${v.visualType}')">+ Thêm Vào Trang</button>
            </div>
          </div>
        `;
      }).join('');
    }

    function addVisualFromCatalog(vtype) {
      addVisual(vtype);
      switchTab('tab-dash');
      openInspector(blueprint.dashboards[currentDashIdx].visuals.length - 1);
    }

    function renderDashboardPills() {
      const wrap = document.getElementById('dash-pills');
      wrap.innerHTML = '';
      blueprint.dashboards.forEach((d, idx) => {
        const pill = document.createElement('div');
        pill.className = 'dash-pill' + (idx === currentDashIdx ? ' active' : '');
        pill.innerText = `${idx + 1}. ${d.name} (${(d.slicers||[]).length} Slicers, ${(d.visuals||[]).length} Charts)`;
        pill.onclick = () => { currentDashIdx = idx; renderDashboardPills(); renderCurrentDashboard(); };
        wrap.appendChild(pill);
      });
    }

    function updateCurrentDashMeta() {
      const d = blueprint.dashboards[currentDashIdx];
      d.id = document.getElementById('d-id').value;
      d.name = document.getElementById('d-name').value;
      d.title = document.getElementById('d-title').value;
      d.subtitle = document.getElementById('d-subtitle').value;
      renderDashboardPills();
      renderCanvasPreview();
    }

    function renderCurrentDashboard() {
      const d = blueprint.dashboards[currentDashIdx];
      if (!d) return;
      document.getElementById('d-id').value = d.id || '';
      document.getElementById('d-name').value = d.name || '';
      document.getElementById('d-title').value = d.title || '';
      document.getElementById('d-subtitle').value = d.subtitle || '';

      const tableOptions = Object.keys(schemaTables);
      const stbody = document.getElementById('slicers-tbody');
      stbody.innerHTML = '';
      (d.slicers || []).forEach((s, sidx) => {
        const cols = schemaTables[s.table] || [s.column];
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><input value="${s.id}" onchange="blueprint.dashboards[${currentDashIdx}].slicers[${sidx}].id=this.value" /></td>
          <td><input value="${s.title}" onchange="blueprint.dashboards[${currentDashIdx}].slicers[${sidx}].title=this.value;renderCanvasPreview()" /></td>
          <td>
            <select onchange="blueprint.dashboards[${currentDashIdx}].slicers[${sidx}].visual_type=this.value">
              ${[['slicer','Classic Slicer'],['advancedSlicerVisual','Button Slicer (New)'],['listSlicer','List Slicer (New)'],['textSlicer','Text Input Slicer']].map(([k,l])=>`<option value="${k}" ${(s.visual_type||'slicer')===k?'selected':''}>${l}</option>`).join('')}
            </select>
          </td>
          <td>
            <select onchange="onSlicerTableChange(${sidx}, this.value)">
              ${tableOptions.map(t => `<option value="${t}" ${t===s.table?'selected':''}>${t}</option>`).join('')}
            </select>
          </td>
          <td>
            <select onchange="blueprint.dashboards[${currentDashIdx}].slicers[${sidx}].column=this.value;renderCanvasPreview()">
              ${cols.map(c => `<option value="${c}" ${c===s.column?'selected':''}>${c}</option>`).join('')}
            </select>
          </td>
          <td>
            <select onchange="blueprint.dashboards[${currentDashIdx}].slicers[${sidx}].mode=this.value">
              ${['Dropdown', 'Between', 'Basic'].map(m => `<option value="${m}" ${m===s.mode?'selected':''}>${m}</option>`).join('')}
            </select>
          </td>
          <td><input value="${s.sync_group||''}" onchange="blueprint.dashboards[${currentDashIdx}].slicers[${sidx}].sync_group=this.value" /></td>
          <td><button class="btn-danger" onclick="removeSlicer(${sidx})">Xóa</button></td>
        `;
        stbody.appendChild(tr);
      });

      const ktbody = document.getElementById('kpis-tbody');
      ktbody.innerHTML = '';
      const measureNames = blueprint.dax_measures.map(m => m.name);
      (d.kpis || []).forEach((k, kidx) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><input value="${k.id}" onchange="blueprint.dashboards[${currentDashIdx}].kpis[${kidx}].id=this.value" /></td>
          <td><input value="${k.title}" onchange="blueprint.dashboards[${currentDashIdx}].kpis[${kidx}].title=this.value;renderCanvasPreview()" /></td>
          <td>
            <select onchange="blueprint.dashboards[${currentDashIdx}].kpis[${kidx}].visual_type=this.value">
              <option value="card" ${(k.visual_type||'card')==='card'?'selected':''}>Classic Card</option>
              <option value="cardVisual" ${k.visual_type==='cardVisual'?'selected':''}>New Card Visual</option>
            </select>
          </td>
          <td>
            <select onchange="blueprint.dashboards[${currentDashIdx}].kpis[${kidx}].measure=this.value;renderCanvasPreview()">
              ${measureNames.map(m => `<option value="${m}" ${m===k.measure?'selected':''}>${m}</option>`).join('')}
            </select>
          </td>
          <td><button class="btn-danger" onclick="removeKpi(${kidx})">Xóa</button></td>
        `;
        ktbody.appendChild(tr);
      });

      const vtbody = document.getElementById('visuals-tbody');
      vtbody.innerHTML = '';
      (d.visuals || []).forEach((v, vidx) => {
        const meta = getVisualMeta(v.type);
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${v.id}</strong></td>
          <td><input value="${v.title}" onchange="blueprint.dashboards[${currentDashIdx}].visuals[${vidx}].title=this.value;renderCanvasPreview()" /></td>
          <td>
            <span class="role-pill" style="background:#1e3a8a;border-color:#3b82f6;color:#dbeafe;">${meta.icon} ${meta.name}</span>
          </td>
          <td><div style="display:flex;flex-wrap:wrap;gap:4px;">${summarizeWellsHtml(v)}</div></td>
          <td><code>X:${v.x}, Y:${v.y}, W:${v.w}, H:${v.h}</code></td>
          <td>
            <div style="display:flex;gap:5px;">
              <button class="btn-sm" onclick="openInspector(${vidx})">⚙️ Cấu Hình Đầy Đủ</button>
              <button class="btn-danger" onclick="removeVisual(${vidx})">Xóa</button>
            </div>
          </td>
        `;
        vtbody.appendChild(tr);
      });

      renderCanvasPreview();
    }

    // ==================== POWER BI VISUAL INSPECTOR ====================
    function openInspector(vidx) {
      editingVisualIdx = vidx;
      const v = blueprint.dashboards[currentDashIdx].visuals[vidx];
      ensureVisualFieldWells(v);
      if (!v.format) v.format = {};

      document.getElementById('insp-vtype').value = v.type;
      document.getElementById('insp-title').value = v.title || '';
      document.getElementById('insp-script-code').value = v.script_code || '';
      document.getElementById('insp-use-native').checked = !!v.use_appsource_native;

      switchInspectorSubtab('build');
      refreshInspectorDetails();
      document.getElementById('inspector-backdrop').classList.add('open');
      renderCanvasPreview();
    }

    function closeInspector() {
      editingVisualIdx = -1;
      document.getElementById('inspector-backdrop').classList.remove('open');
      renderCurrentDashboard();
    }

    function applyAndCloseInspector() {
      syncInspectorBasicMeta();
      syncInspectorFormat();
      closeInspector();
      showToast('✅ Đã cập nhật cấu hình biểu đồ! Nhấn nút "🚀 3. Lưu Thay Đổi & Mở Lại Power BI Desktop" để xem trên Power BI.');
    }

    function switchInspectorSubtab(mode) {
      document.getElementById('subtab-btn-build').classList.toggle('active', mode === 'build');
      document.getElementById('subtab-btn-format').classList.toggle('active', mode === 'format');
      document.getElementById('insp-pane-build').style.display = mode === 'build' ? 'block' : 'none';
      document.getElementById('insp-pane-format').style.display = mode === 'format' ? 'block' : 'none';
    }

    function onInspectorVisualTypeChange(newType) {
      if (editingVisualIdx < 0) return;
      const v = blueprint.dashboards[currentDashIdx].visuals[editingVisualIdx];
      const oldWells = ensureVisualFieldWells(v);
      // Preserve existing columns & measures and auto-map into the new visual's field wells!
      const allCols = [];
      const allMeasures = [];
      const tooltips = oldWells.Tooltips || [];
      for (const [rk, items] of Object.entries(oldWells)) {
        if (rk === 'Tooltips') continue;
        (items || []).forEach(it => {
          if (it.measure) allMeasures.push(it);
          else if (it.column) allCols.push(it);
        });
      }
      v.type = newType;
      const meta = getVisualMeta(newType);
      const newWells = {};
      let cIdx = 0, mIdx = 0;
      (meta.roles || []).forEach(role => {
        if (role.key === 'Tooltips') {
          if (tooltips.length) newWells.Tooltips = [...tooltips];
          return;
        }
        if (role.kind === 'column' && cIdx < allCols.length) {
          newWells[role.key] = [allCols[cIdx++]];
        } else if (role.kind === 'measure' && mIdx < allMeasures.length) {
          newWells[role.key] = [allMeasures[mIdx++]];
        } else if (role.kind === 'any') {
          if (role.multi) {
            const combined = [...allCols.slice(cIdx), ...allMeasures.slice(mIdx)];
            if (combined.length) newWells[role.key] = combined;
          } else if (mIdx < allMeasures.length) {
            newWells[role.key] = [allMeasures[mIdx++]];
          } else if (cIdx < allCols.length) {
            newWells[role.key] = [allCols[cIdx++]];
          }
        }
      });
      v.field_wells = newWells;
      refreshInspectorDetails();
    }

    function syncInspectorBasicMeta() {
      if (editingVisualIdx < 0) return;
      const v = blueprint.dashboards[currentDashIdx].visuals[editingVisualIdx];
      v.title = document.getElementById('insp-title').value;
      v.script_code = document.getElementById('insp-script-code').value;
      v.use_appsource_native = document.getElementById('insp-use-native').checked;
    }

    function refreshInspectorDetails() {
      if (editingVisualIdx < 0) return;
      const v = blueprint.dashboards[currentDashIdx].visuals[editingVisualIdx];
      const meta = getVisualMeta(v.type);
      const wells = ensureVisualFieldWells(v);

      document.getElementById('insp-heading').innerText = `${meta.icon} Cấu Hình Chi Tiết: ${v.id} (${meta.name} – ${meta.name_vi})`;
      document.getElementById('insp-sub').innerText = `${meta.description} | VisualType: ${meta.visualType}`;

      // AppSource notice box
      const isAppSrc = meta.source === 'appsource_microsoft' || meta.source === 'appsource_custom' || meta.source === 'imported_pbiviz';
      document.getElementById('insp-appsource-box').style.display = isAppSrc ? 'block' : 'none';
      if (isAppSrc) {
        document.getElementById('insp-appsource-desc').innerHTML = meta.source === 'imported_pbiviz'
          ? `Đã cài sẵn gói <code>.pbiviz</code> (${meta.visualType}).`
          : `Biểu đồ AppSource (<code>${meta.visualType}</code>). Nếu chưa cài trên Power BI, bỏ chọn bên phải để tự chuyển sang <code>${meta.fallback_builtin}</code>.` +
            (meta.appsource_url ? ` <a href="${meta.appsource_url}" target="_blank" style="color:#c4b5fd;">[Mở AppSource]</a>` : '');
      }

      // Script box for pythonVisual / scriptVisual
      const scType = (meta.capabilities && meta.capabilities.script) || '';
      document.getElementById('insp-script-box').style.display = scType ? 'block' : 'none';
      if (scType) {
        document.getElementById('insp-script-label').innerText = scType === 'python'
          ? '🐍 Mã Python Visual (Sử dụng biến DataFrame `dataset`, vẽ bằng matplotlib/seaborn)'
          : '📐 Mã R Script Visual (Sử dụng biến DataFrame `dataset`, vẽ bằng ggplot2/base R)';
      }

      // Build dynamic Field Wells UI
      const wrap = document.getElementById('insp-wells-container');
      const allTables = Object.keys(schemaTables);
      const allMeasures = blueprint.dax_measures.map(m => m.name);
      const factTbl = (blueprint.project && blueprint.project.fact_table_name) || 'Fact_Flight';

      if (!meta.roles || meta.roles.length === 0) {
        wrap.innerHTML = `<div class="well-card"><span style="color:#94a3b8;">Visual loại <strong>${meta.name}</strong> là phần tử giao diện (UI Element), không cần gắn bảng dữ liệu. Hãy chuyển sang tab <strong>Format & Analytics</strong> để chỉnh màu sắc, tiêu đề và tọa độ.</span></div>`;
      } else {
        wrap.innerHTML = meta.roles.map(role => {
          const items = wells[role.key] || [];
          const chipsHtml = items.length ? items.map((it, idx) => {
            const isM = !!it.measure;
            const txt = isM ? `📐 [${it.measure}]` : `📋 ${it.table}.${it.column}`;
            return `<span class="chip ${isM ? 'measure' : ''}">
              ${txt}
              ${idx > 0 ? `<button title="Lên" onclick="moveWellItem('${role.key}', ${idx}, -1)">←</button>` : ''}
              ${idx < items.length - 1 ? `<button title="Xuống" onclick="moveWellItem('${role.key}', ${idx}, 1)">→</button>` : ''}
              <button title="Xóa" onclick="removeWellItem('${role.key}', ${idx})">✕</button>
            </span>`;
          }).join('') : `<span style="font-size:11px;color:#64748b;">Chưa chọn trường nào cho ô ${role.label}</span>`;

          // Build dropdown options for Columns and Measures
          const colOpts = [];
          allTables.forEach(t => {
            (schemaTables[t] || []).forEach(c => {
              colOpts.push(`<option value="col::${t}::${c}">📋 ${t}.${c}</option>`);
            });
          });
          const measOpts = allMeasures.map(m => `<option value="meas::${factTbl}::${m}">📐 [DAX] ${m}</option>`);

          let selectorOptions = '';
          if (role.kind === 'measure') {
            selectorOptions = `<optgroup label="DAX Measures (${allMeasures.length})">${measOpts.join('')}</optgroup><optgroup label="Hoặc chọn Cột số">${colOpts.join('')}</optgroup>`;
          } else if (role.kind === 'column') {
            selectorOptions = `<optgroup label="Cột trong Star Schema">${colOpts.join('')}</optgroup><optgroup label="DAX Measures">${measOpts.join('')}</optgroup>`;
          } else {
            selectorOptions = `<optgroup label="DAX Measures (${allMeasures.length})">${measOpts.join('')}</optgroup><optgroup label="Cột trong Star Schema">${colOpts.join('')}</optgroup>`;
          }

          return `
            <div class="well-card">
              <div class="well-head">
                <div>
                  <span class="well-title">${role.label}</span>
                  ${role.hint ? `<span style="font-size:10px;color:#94a3b8;margin-left:8px;">— ${role.hint}</span>` : ''}
                </div>
                <div style="display:flex;gap:5px;">
                  <span class="well-tag ${role.required ? 'req' : ''}">${role.required ? 'Bắt buộc' : 'Tùy chọn'}</span>
                  <span class="well-tag">${role.multi ? 'Nhiều trường (Multi)' : '1 trường (Single)'}</span>
                  <span class="well-tag">Role: ${role.key}</span>
                </div>
              </div>
              <div class="well-chips">${chipsHtml}</div>
              <div class="well-add-row">
                <select id="add-sel-${role.key}" style="grid-column:span 2;">${selectorOptions}</select>
                <button class="btn-sm" onclick="addWellItem('${role.key}', ${role.multi})">+ Thêm Vào Ô</button>
              </div>
            </div>
          `;
        }).join('');
      }

      // Populate Format & Analytics inputs
      const f = v.format || {};
      document.getElementById('fmt-x').value = v.x;
      document.getElementById('fmt-y').value = v.y;
      document.getElementById('fmt-w').value = v.w;
      document.getElementById('fmt-h').value = v.h;
      document.getElementById('fmt-title-show').checked = f.title_show !== false;
      document.getElementById('fmt-legend-show').checked = f.legend_show !== false;
      document.getElementById('fmt-labels-show').checked = !!f.data_labels_show;
      document.getElementById('fmt-border-show').checked = f.border_show !== false;
      document.getElementById('fmt-xaxis-show').checked = f.x_axis_show !== false;
      document.getElementById('fmt-yaxis-show').checked = f.y_axis_show !== false;
      document.getElementById('fmt-legend-pos').value = f.legend_position || 'Top';
      document.getElementById('fmt-title-align').value = f.title_align || 'left';
      document.getElementById('fmt-title-size').value = f.title_font_size || 10;
      document.getElementById('fmt-title-color').value = f.title_color || '#0f172a';
      document.getElementById('fmt-title-bg').value = f.title_bg || '#f1f5f9';
      document.getElementById('fmt-bg-color').value = f.bg_color || '#ffffff';
      document.getElementById('fmt-border-color').value = f.border_color || '#cbd5e1';
      document.getElementById('fmt-topn').value = f.top_n || '';
      document.getElementById('fmt-topn-dir').value = f.top_n_direction || 'Top';
      document.getElementById('fmt-sort-dir').value = f.sort_direction || 'Descending';
      document.getElementById('fmt-const-val').value = (f.constant_line_value !== undefined && f.constant_line_value !== null) ? f.constant_line_value : '';
      document.getElementById('fmt-const-lbl').value = f.constant_line_label || '';
      document.getElementById('fmt-const-col').value = f.constant_line_color || '#ef4444';
      document.getElementById('fmt-radius').value = f.border_radius !== undefined ? f.border_radius : 6;

      // Sort field options from currently bound fields
      const sortSel = document.getElementById('fmt-sort-field');
      const boundFields = [];
      for (const items of Object.values(wells)) {
        (items || []).forEach(it => {
          const fn = it.measure || it.column;
          if (fn && !boundFields.includes(fn)) boundFields.push(fn);
        });
      }
      sortSel.innerHTML = '<option value="">(Mặc định Power BI)</option>' +
        boundFields.map(fn => `<option value="${fn}" ${f.sort_field===fn?'selected':''}>${fn}</option>`).join('');
    }

    function addWellItem(roleKey, isMulti) {
      if (editingVisualIdx < 0) return;
      const v = blueprint.dashboards[currentDashIdx].visuals[editingVisualIdx];
      const wells = ensureVisualFieldWells(v);
      const raw = document.getElementById(`add-sel-${roleKey}`).value;
      const [kind, tbl, fname] = raw.split('::');
      const item = kind === 'meas' ? {table: tbl, measure: fname} : {table: tbl, column: fname};
      if (!wells[roleKey] || !isMulti) {
        wells[roleKey] = [item];
      } else {
        const exists = wells[roleKey].some(x => (x.measure && x.measure === item.measure) || (x.column && x.column === item.column && x.table === item.table));
        if (!exists) wells[roleKey].push(item);
      }
      refreshInspectorDetails();
    }

    function removeWellItem(roleKey, idx) {
      const v = blueprint.dashboards[currentDashIdx].visuals[editingVisualIdx];
      const wells = ensureVisualFieldWells(v);
      wells[roleKey].splice(idx, 1);
      if (wells[roleKey].length === 0) delete wells[roleKey];
      refreshInspectorDetails();
    }

    function moveWellItem(roleKey, idx, delta) {
      const v = blueprint.dashboards[currentDashIdx].visuals[editingVisualIdx];
      const arr = v.field_wells[roleKey];
      const target = idx + delta;
      if (target < 0 || target >= arr.length) return;
      [arr[idx], arr[target]] = [arr[target], arr[idx]];
      refreshInspectorDetails();
    }

    function applyPosPreset(x, y, w, h) {
      document.getElementById('fmt-x').value = x;
      document.getElementById('fmt-y').value = y;
      document.getElementById('fmt-w').value = w;
      document.getElementById('fmt-h').value = h;
      syncInspectorFormat();
    }

    function syncInspectorFormat() {
      if (editingVisualIdx < 0) return;
      const v = blueprint.dashboards[currentDashIdx].visuals[editingVisualIdx];
      v.x = parseInt(document.getElementById('fmt-x').value) || 16;
      v.y = parseInt(document.getElementById('fmt-y').value) || 212;
      v.w = parseInt(document.getElementById('fmt-w').value) || 400;
      v.h = parseInt(document.getElementById('fmt-h').value) || 240;
      const topnRaw = document.getElementById('fmt-topn').value;
      const constRaw = document.getElementById('fmt-const-val').value;
      v.format = {
        title_show: document.getElementById('fmt-title-show').checked,
        legend_show: document.getElementById('fmt-legend-show').checked,
        legend_position: document.getElementById('fmt-legend-pos').value,
        data_labels_show: document.getElementById('fmt-labels-show').checked,
        x_axis_show: document.getElementById('fmt-xaxis-show').checked,
        y_axis_show: document.getElementById('fmt-yaxis-show').checked,
        title_align: document.getElementById('fmt-title-align').value,
        title_font_size: parseInt(document.getElementById('fmt-title-size').value) || 10,
        title_color: document.getElementById('fmt-title-color').value,
        title_bg: document.getElementById('fmt-title-bg').value,
        bg_color: document.getElementById('fmt-bg-color').value,
        border_show: document.getElementById('fmt-border-show').checked,
        border_color: document.getElementById('fmt-border-color').value,
        border_radius: parseInt(document.getElementById('fmt-radius').value) || 0,
        top_n: topnRaw ? parseInt(topnRaw) : null,
        top_n_direction: document.getElementById('fmt-topn-dir').value,
        sort_field: document.getElementById('fmt-sort-field').value,
        sort_direction: document.getElementById('fmt-sort-dir').value,
        constant_line_value: constRaw !== '' ? parseFloat(constRaw) : null,
        constant_line_label: document.getElementById('fmt-const-lbl').value,
        constant_line_color: document.getElementById('fmt-const-col').value,
      };
      renderCanvasPreview();
    }

    // ==================== ADD / REMOVE HELPERS ====================
    function onSlicerTableChange(sidx, newTable) {
      const s = blueprint.dashboards[currentDashIdx].slicers[sidx];
      s.table = newTable;
      s.column = (schemaTables[newTable] || [''])[0];
      renderCurrentDashboard();
    }

    function addSlicer() {
      const d = blueprint.dashboards[currentDashIdx];
      const firstTbl = Object.keys(schemaTables)[0] || 'Dim_Airline';
      const firstCol = (schemaTables[firstTbl] || ['Reporting_Airline'])[0];
      d.slicers.push({
        id: `S_${d.id.replace('-','')}_${d.slicers.length+1}`,
        title: firstCol,
        visual_type: 'slicer',
        table: firstTbl,
        column: firstCol,
        mode: 'Dropdown',
        sync_group: ''
      });
      renderCurrentDashboard();
      renderDashboardPills();
    }

    function removeSlicer(sidx) {
      blueprint.dashboards[currentDashIdx].slicers.splice(sidx, 1);
      renderCurrentDashboard();
      renderDashboardPills();
    }

    function addKpiCard() {
      const d = blueprint.dashboards[currentDashIdx];
      const firstM = (blueprint.dax_measures[0] && blueprint.dax_measures[0].name) || 'Total Flights';
      d.kpis.push({
        id: `KPI_${d.id.replace('-','')}_${d.kpis.length+1}`,
        title: firstM,
        visual_type: 'card',
        measure: firstM,
        tooltip_measures: []
      });
      renderCurrentDashboard();
    }

    function removeKpi(kidx) {
      blueprint.dashboards[currentDashIdx].kpis.splice(kidx, 1);
      renderCurrentDashboard();
    }

    function addVisual(vtype='clusteredBarChart') {
      const d = blueprint.dashboards[currentDashIdx];
      const meta = getVisualMeta(vtype);
      const factTbl = (blueprint.project && blueprint.project.fact_table_name) || 'Fact_Flight';
      const firstM = (blueprint.dax_measures[0] && blueprint.dax_measures[0].name) || 'Total Flights';
      const firstDimTbl = Object.keys(schemaTables).find(t => t.startsWith('Dim_') && t !== 'Dim_Date') || Object.keys(schemaTables)[0] || 'Dim_Airline';
      const firstDimCol = (schemaTables[firstDimTbl] || ['Reporting_Airline'])[0];

      const defaultWells = {};
      (meta.roles || []).forEach(r => {
        if (r.required) {
          if (r.kind === 'measure') defaultWells[r.key] = [{table: factTbl, measure: firstM}];
          else defaultWells[r.key] = [{table: firstDimTbl, column: firstDimCol}];
        }
      });

      d.visuals.push({
        id: `${d.id.replace('-','')}-0${d.visuals.length+1}`,
        title: `${meta.name_vi} mới`,
        type: vtype,
        x: 16, y: 212, w: 410, h: 240,
        field_wells: defaultWells,
        format: { title_show: true, legend_show: true, legend_position: 'Top', border_show: true, border_radius: 6 }
      });
      renderCurrentDashboard();
      renderDashboardPills();
    }

    function removeVisual(vidx) {
      blueprint.dashboards[currentDashIdx].visuals.splice(vidx, 1);
      renderCurrentDashboard();
      renderDashboardPills();
    }

    function addNewDashboard() {
      const idx = blueprint.dashboards.length + 1;
      const firstM = (blueprint.dax_measures[0] && blueprint.dax_measures[0].name) || 'Total Flights';
      blueprint.dashboards.push({
        id: `CU-0${idx}`,
        name: `CU-0${idx} Custom Page`,
        title: `CU-0${idx}: CUSTOM ANALYTICS DASHBOARD`,
        subtitle: "Trang dashboard tùy chỉnh",
        slicers: [],
        kpis: [{id: `KPI_CU${idx}_1`, title: firstM, measure: firstM, tooltip_measures: []}],
        visuals: []
      });
      currentDashIdx = blueprint.dashboards.length - 1;
      renderDashboardPills();
      renderCurrentDashboard();
    }

    function deleteCurrentDashboard() {
      if (blueprint.dashboards.length <= 1) { showToast('Phải giữ lại ít nhất 1 trang Dashboard!', true); return; }
      blueprint.dashboards.splice(currentDashIdx, 1);
      currentDashIdx = Math.max(0, currentDashIdx - 1);
      renderDashboardPills();
      renderCurrentDashboard();
    }

    function renderCanvasPreview() {
      const d = blueprint.dashboards[currentDashIdx];
      const canvas = document.getElementById('canvas-preview');
      if (!d || !canvas) return;
      canvas.innerHTML = '';
      const W = 1280, H = 720;
      const pctX = x => (x * 100 / W) + '%';
      const pctY = y => (y * 100 / H) + '%';

      const hdr = document.createElement('div');
      hdr.className = 'cv-box cv-header';
      hdr.style.left = pctX(16); hdr.style.top = pctY(8);
      hdr.style.width = pctX(1248); hdr.style.height = pctY(46);
      hdr.innerText = d.title;
      canvas.appendChild(hdr);

      const slicers = d.slicers || [];
      if (slicers.length > 0) {
        const gap = 8, sw = Math.floor((1248 - gap * (slicers.length - 1)) / slicers.length);
        slicers.forEach((s, idx) => {
          const el = document.createElement('div');
          el.className = 'cv-box cv-slicer';
          el.style.left = pctX(16 + idx * (sw + gap)); el.style.top = pctY(58);
          el.style.width = pctX(sw); el.style.height = pctY(64);
          el.innerHTML = `<strong>🔻 ${s.title}</strong><span>${s.table}.${s.column}</span>`;
          canvas.appendChild(el);
        });
      }

      const kpis = d.kpis || [];
      if (kpis.length > 0) {
        const gap = 8, kw = Math.floor((1248 - gap * (kpis.length - 1)) / kpis.length);
        kpis.forEach((k, idx) => {
          const el = document.createElement('div');
          el.className = 'cv-box cv-kpi';
          el.style.left = pctX(16 + idx * (kw + gap)); el.style.top = pctY(128);
          el.style.width = pctX(kw); el.style.height = pctY(76);
          el.innerHTML = `<div style="font-size:8.5px;color:#475569;">${k.title}</div><div style="color:#1d4ed8;">[${k.measure}]</div>`;
          canvas.appendChild(el);
        });
      }

      (d.visuals || []).forEach((v, vidx) => {
        const meta = getVisualMeta(v.type);
        const el = document.createElement('div');
        el.className = 'cv-box cv-visual' + (vidx === editingVisualIdx ? ' selected' : '');
        el.style.left = pctX(v.x); el.style.top = pctY(v.y);
        el.style.width = pctX(v.w); el.style.height = pctY(v.h);
        el.title = 'Nhấp để mở Power BI Field Wells & Format Inspector';
        el.onclick = () => openInspector(vidx);
        const w = ensureVisualFieldWells(v);
        const wellText = Object.entries(w).slice(0, 3).map(([rk, items]) => `${rk}: ${items.map(i => i.measure || i.column).join(', ')}`).join(' | ');
        el.innerHTML = `<div class="cv-visual-title">${v.title}</div><span class="cv-badge">${meta.icon} ${meta.name}</span><div class="cv-wells-mini">${wellText}</div>`;
        canvas.appendChild(el);
      });
    }

    function renderDaxTable() {
      document.getElementById('dax-count').innerText = blueprint.dax_measures.length;
      const tbody = document.getElementById('dax-tbody');
      tbody.innerHTML = '';
      blueprint.dax_measures.forEach((m, idx) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><input value="${m.name}" onchange="blueprint.dax_measures[${idx}].name=this.value" /></td>
          <td><input value="${m.folder||''}" onchange="blueprint.dax_measures[${idx}].folder=this.value" /></td>
          <td><input value="${m.expression.replace(/"/g, '&quot;')}" onchange="blueprint.dax_measures[${idx}].expression=this.value" style="font-family:Consolas,monospace;" /></td>
          <td><input value="${m.formatString||''}" onchange="blueprint.dax_measures[${idx}].formatString=this.value" /></td>
          <td><input value="${m.description||''}" onchange="blueprint.dax_measures[${idx}].description=this.value" /></td>
          <td><button class="btn-danger" onclick="blueprint.dax_measures.splice(${idx},1);renderDaxTable()">Xóa</button></td>
        `;
        tbody.appendChild(tr);
      });
    }

    function addDaxMeasure() {
      blueprint.dax_measures.unshift({
        name: "Custom KPI Measure",
        folder: "07. Custom Measures",
        expression: `COUNTROWS('${(blueprint.project && blueprint.project.fact_table_name) || 'Fact_Flight'}')`,
        formatString: "#,##0",
        description: "Measure tùy chỉnh"
      });
      renderDaxTable();
    }

    const esc = s => String(s === null || s === undefined ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

    function renderAuditTab(prof, kpi) {
      const ms = (kpi && kpi.measures) || [];
      const meta = (kpi && kpi.measures_meta) || null;
      const topBox = document.getElementById('audit-top-stats');
      const kpiBox = document.getElementById('audit-kpi-table');
      if (!ms.length) {
        topBox.innerHTML = '';
        kpiBox.innerHTML = '<p style="color:#94a3b8;padding:8px;">Chưa có kết quả đối soát. Hãy chạy "⚡ Chạy Tự Động A–Z" để tính KPI theo Requirement.md.</p>';
      } else {
        topBox.innerHTML = ms.filter(m => m.status === 'OK').slice(0, 6).map(m =>
          `<div class="stat-box"><div class="val">${esc(m.display)}</div><div class="lbl">${esc(m.name)}</div></div>`).join('');
        const bp = (blueprint && blueprint.dax_measures) || [];
        const bpExpr = {}; bp.forEach(m => bpExpr[m.name] = m.expression);
        const stale = bp.length !== ms.length || ms.some(m => bpExpr[m.name] !== m.expression);
        let html = '';
        if (stale) html += '<div style="background:#78350f;color:#fef3c7;padding:8px 10px;border-radius:6px;font-size:12px;margin-bottom:8px;">⚠️ Kết quả đối soát CHƯA khớp danh sách DAX hiện tại (đã sửa Requirement/DAX sau lần chạy trước). Bấm "🔄 Đối soát lại KPI theo Requirement hiện tại".</div>';
        if (meta) html += `<div style="font-size:11px;color:#93c5fd;margin-bottom:8px;">Nguồn: <strong>${esc(meta.requirement_doc || '')}</strong> (sửa lần cuối: ${esc(meta.requirement_modified || 'N/A')}) · đối soát lúc ${esc(meta.evaluated_at)} · ✅ ${meta.ok} OK · ⚪ ${meta.blank} Blank · ⚠️ ${meta.unsupported} chưa hỗ trợ · ❌ ${meta.error} lỗi / ${meta.total} measure</div>`;
        html += '<table><thead><tr><th>Measure</th><th>Giá trị</th><th>Trạng thái</th><th>Công thức DAX</th></tr></thead><tbody>' +
          ms.map(m => `<tr><td><strong>${esc(m.name)}</strong></td><td>${esc(m.display)}</td><td>${esc(m.status)}</td><td><code style="font-size:10px;">${esc(m.expression)}</code></td></tr>`).join('') +
          '</tbody></table>';
        kpiBox.innerHTML = html;
      }
      const dq = (prof && prof.dq_checks) || [];
      document.getElementById('audit-dq-table').innerHTML = dq.length
        ? '<table><thead><tr><th>Mã</th><th>Tiêu chí kiểm tra</th><th>Số dòng</th><th>Tỷ lệ (%)</th><th>Trạng thái</th></tr></thead><tbody>' +
          dq.map(c => `<tr><td>${esc(c.CheckID)}</td><td>${esc(c.CheckName)}</td><td>${Number(c.RecordCount).toLocaleString()}</td><td>${c.Percentage}%</td><td><strong>${esc(c.Status)}</strong></td></tr>`).join('') + '</tbody></table>'
        : '<p style="color:#94a3b8;padding:8px;">Chưa có kết quả kiểm toán dữ liệu.</p>';
    }

    async function revalidateKpi() {
      showToast('⏳ Đang đối soát lại toàn bộ DAX measure trên dữ liệu (có thể mất vài chục giây với file lớn)...');
      const res = await fetch('/api/revalidate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({blueprint})});
      const out = await res.json();
      if (out.status === 'ok') { showToast(`✅ Đã đối soát ${out.meta.total} measure: ${out.meta.ok} OK`); await loadAllData(); }
      else showToast('❌ ' + out.error, true);
    }

    // ---------- Requirement template / guide viewer ----------
    const docCache = {};
    async function fetchDoc(name) {
      if (docCache[name]) return docCache[name];
      const res = await fetch('/api/doc/' + encodeURIComponent(name));
      const out = await res.json();
      if (out.status !== 'ok') throw new Error(out.error || 'Không đọc được tài liệu');
      docCache[name] = out.content;
      return out.content;
    }
    async function openDocModal(name, title) {
      try {
        const text = await fetchDoc(name);
        document.getElementById('doc-title').innerText = title || name;
        document.getElementById('doc-body').value = text;
        document.getElementById('doc-copy-btn').onclick = () => copyText(text, name);
        document.getElementById('doc-download-btn').onclick = () => downloadText(name, text);
        document.getElementById('doc-backdrop').classList.add('open');
      } catch (e) { showToast('❌ ' + e.message, true); }
    }
    function closeDocModal() { document.getElementById('doc-backdrop').classList.remove('open'); }
    async function copyDocByName(name) { try { copyText(await fetchDoc(name), name); } catch (e) { showToast('❌ ' + e.message, true); } }
    async function downloadDocByName(name) { try { downloadText(name, await fetchDoc(name)); } catch (e) { showToast('❌ ' + e.message, true); } }
    async function copyText(text, label) {
      try { await navigator.clipboard.writeText(text); }
      catch (e) { const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); }
      showToast(`📋 Đã copy ${label} (${text.length.toLocaleString()} ký tự) vào clipboard`);
    }
    function downloadText(name, text) {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([text], {type: 'text/markdown;charset=utf-8'}));
      a.download = name; a.click(); URL.revokeObjectURL(a.href);
    }

    // ---------- In-app AppSource marketplace ----------
    async function searchMarketplace() {
      const q = document.getElementById('mp-search').value.trim();
      const box = document.getElementById('mp-results');
      box.innerHTML = '<span style="color:#94a3b8;">Đang tải danh mục...</span>';
      try {
        const res = await fetch('/api/marketplace?q=' + encodeURIComponent(q));
        const out = await res.json();
        if (out.status !== 'ok') { box.innerHTML = `<span style="color:#fca5a5;">${esc(out.error)}</span>`; return; }
        document.getElementById('mp-count').innerText = `${out.matched.toLocaleString()} / ${out.total.toLocaleString()} visual${out.matched > out.items.length ? ` (hiển thị ${out.items.length} đầu tiên)` : ''}`;
        box.innerHTML = out.items.map(it => `
          <div class="vcat-card">
            <div>
              <div class="vcat-top">
                <div><div class="vcat-name">🧩 ${esc(it.name)}</div><div class="vcat-vi">${esc(it.publisher)} · v${esc(it.version)}</div></div>
                <span class="vcat-src ${it.certified ? 'src-builtin' : 'src-appsource'}">${it.certified ? 'Certified' : 'Community'}</span>
              </div>
              <p style="font-size:11px;color:#94a3b8;margin:6px 0;">${esc(it.description)}</p>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;padding-top:8px;border-top:1px solid #1e293b;">
              <code style="font-size:10px;color:#64748b;word-break:break-all;">${esc(it.guid)}</code>
              ${it.installed ? '<span class="well-tag" style="background:#065f46;color:#a7f3d0;">✔ Đã cài</span>' : `<button class="btn-sm" onclick="installMarketplaceVisual('${esc(it.guid)}')">⬇️ Tải & Cài</button>`}
            </div>
          </div>`).join('') || '<span style="color:#94a3b8;">Không có kết quả phù hợp.</span>';
      } catch (e) { box.innerHTML = `<span style="color:#fca5a5;">${esc(e.message)}</span>`; }
    }

    async function installMarketplaceVisual(guid) {
      showToast('⏳ Đang tải gói .pbiviz từ kho AppSource...');
      const res = await fetch('/api/marketplace/install', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({guid})});
      const out = await res.json();
      if (out.status === 'ok') {
        showToast(`✅ Đã cài ${out.visual.name} (${(out.size_bytes / 1024).toFixed(0)} KB, ${out.visual.roles.length} field wells)`);
        await loadAllData();
        searchMarketplace();
      } else showToast('❌ ' + out.error, true);
    }

    // ==================== API ACTIONS ====================
    async function uploadInputFile(inputEl, kind) {
      if (!inputEl.files || !inputEl.files[0]) return;
      const formData = new FormData();
      formData.append('file', inputEl.files[0]);
      formData.append('kind', kind);
      showToast(`⏳ Đang tải file ${inputEl.files[0].name} lên workspace...`);
      const res = await fetch('/api/upload-input', {method: 'POST', body: formData});
      const out = await res.json();
      if (out.status === 'ok') {
        document.getElementById(kind === 'csv' ? 'pipe-csv-path' : 'pipe-req-path').value = out.saved_path;
        showToast(`✅ Đã nạp file: ${out.saved_path}`);
      } else {
        showToast('❌ Lỗi tải file: ' + out.error, true);
      }
    }

    async function uploadPbiviz() {
      const inp = document.getElementById('pbiviz-upload');
      if (!inp.files || !inp.files[0]) { showToast('Hãy chọn file .pbiviz trước!', true); return; }
      const formData = new FormData();
      formData.append('file', inp.files[0]);
      showToast(`⏳ Đang giải nén & đăng ký ${inp.files[0].name}...`);
      const res = await fetch('/api/upload-pbiviz', {method: 'POST', body: formData});
      const out = await res.json();
      if (out.status === 'ok') {
        showToast(`✅ Đã import thành công Custom Visual: ${out.visual.name} (${out.visual.roles.length} Field Wells)!`);
        await loadAllData();
      } else {
        showToast('❌ Lỗi import .pbiviz: ' + out.error, true);
      }
    }

    async function runAutomatedPipeline() {
      const csvPath = document.getElementById('pipe-csv-path').value.trim();
      const reqPath = document.getElementById('pipe-req-path').value.trim();
      const projName = document.getElementById('pipe-proj-name').value.trim();
      const bar = document.getElementById('pipe-status-bar');
      bar.style.display = 'block';
      bar.style.color = '#fbbf24';
      bar.innerText = `⏳ Đang chạy tự động toàn trình cho '${csvPath}' & '${reqPath}'...`;
      const res = await fetch('/api/run-pipeline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({csv_path: csvPath, req_path: reqPath, project_name: projName})
      });
      const out = await res.json();
      if (out.status === 'ok') {
        const pbi = out.result.pbi_artifacts || {};
        bar.style.color = '#10b981';
        bar.innerText = `✅ Hoàn tất trong ${out.result.total_elapsed_seconds}s! (${pbi.pages_count} trang, ${pbi.visuals_count} visuals/slicers, ${pbi.dax_measures_count} DAX measures) -> ${pbi.pbip_path}`;
        showToast(`✅ Pipeline A-Z hoàn tất (${out.result.total_elapsed_seconds}s)!`);
        currentDashIdx = 0;
        await loadAllData();
      } else {
        bar.style.color = '#ef4444';
        bar.innerText = '❌ Lỗi: ' + out.error;
        showToast('❌ Lỗi: ' + out.error, true);
      }
    }

    async function saveAndGeneratePBI() {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({blueprint})
      });
      const out = await res.json();
      if (out.status === 'ok') {
        showToast(`✅ Đã sinh Power BI Project (.pbip & .pbit): ${out.summary.pages_count} trang, ${out.summary.visuals_count} visuals, ${out.summary.dax_measures_count} DAX measures!`);
      } else {
        showToast('❌ Lỗi: ' + out.error, true);
      }
    }

    async function openInPowerBIDesktop() {
      await saveAndGeneratePBI();
      showToast('⏳ Đang đóng cửa sổ cũ, mở Power BI Desktop với bố cục mới và tự động nạp dữ liệu...');
      const res = await fetch('/api/open-pbi', {method: 'POST'});
      const out = await res.json();
      if (out.status === 'ok') {
        showToast('🚀 Đã mở Power BI Desktop & nạp dữ liệu thành công! Hãy chuyển tab dưới thanh Power BI để xem số liệu mới.');
      } else {
        showToast('⚠️ ' + out.message, true);
      }
    }

    async function refreshLivePowerBI() {
      showToast('⏳ Đang kết nối vào Power BI Desktop đang mở và nạp dữ liệu...');
      const res = await fetch('/api/refresh-live', {method: 'POST'});
      const out = await res.json();
      if (out.status === 'ok') {
        const k = out.result.kpis || {};
        showToast(`✅ Đã nạp dữ liệu vào Power BI (Cổng ${out.result.port})! Hãy bấm chuyển tab trên Power BI Desktop.`);
      } else {
        showToast('⚠️ ' + (out.message || 'Chưa tìm thấy Power BI Desktop đang mở'), true);
      }
    }

    async function saveRequirementMd() {
      const text = document.getElementById('req-md-editor').value;
      const res = await fetch('/api/save-requirement', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({content: text})
      });
      const out = await res.json();
      if (out.status === 'ok') showToast('✅ Đã lưu cập nhật vào Requirement.md!');
    }

    loadAllData();
  </script>
</body>
</html>
"""


def _extract_dynamic_schema_tables(root: Path, blueprint: Dict[str, Any]) -> Dict[str, List[str]]:
    """Dynamically extract {TableName: [ColumnName, ...]} from model.bim so Web UI works with ANY CSV dataset."""
    proj_name = blueprint.get("project", {}).get("name", "US_Flight_Operations")
    out_dir = blueprint.get("project", {}).get("output_pbi_dir", "output_pbi")
    bim_path = root / out_dir / f"{proj_name}.SemanticModel" / "model.bim"
    if bim_path.exists():
        try:
            bim = json.loads(bim_path.read_text(encoding="utf-8"))
            res = {}
            for t in bim.get("model", {}).get("tables", []):
                cols = [c["name"] for c in t.get("columns", []) if not c.get("isHidden")]
                if cols:
                    res[t["name"]] = cols
            if res:
                return res
        except Exception:
            pass
    if blueprint.get("is_empty"):
        return {}
    # Fallback default aviation schema
    return {
        "Dim_Date": ["Date", "Year", "QuarterLabel", "MonthName", "MonthShort", "YearMonth", "DayName", "WeekendFlag"],
        "Dim_Airline": ["Reporting_Airline", "AirlineName", "AirlineLabel"],
        "Dim_OriginAirport": ["AirportCode", "AirportLabel", "CityName", "State", "AirportGroup"],
        "Dim_DestinationAirport": ["AirportCode", "AirportLabel", "CityName", "State", "AirportGroup"],
        "Dim_Route": ["RouteLabel", "Origin", "Dest", "OriginState", "DestState", "DistanceBand", "RouteGroup"],
        "Dim_TimeBlock": ["DepTimeBlock", "DepHour", "HourLabel"],
        "Fact_Flight": ["FlightOutcome", "ArrDelayBand", "DepDelayBand", "DistanceBand", "CancellationReasonLabel", "FlightKey", "Flight_Number_Reporting_Airline"],
        "Fact_DelayCause": ["CauseName", "ArrDelayBand"],
        "Data_Quality_Stats": ["CheckID", "Category", "CheckName", "RecordCount", "Percentage", "Status"],
    }


ALLOWED_DOCS = {"Requirement_Template.md", "HUONG_DAN_REQUIREMENT.md"}
PACKAGE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)


def _read_requirement(root: Path, bp: Dict[str, Any]) -> str:
    req_file = bp.get("project", {}).get("requirement_doc") or ""
    if not req_file:
        return ""
    p = Path(req_file) if Path(req_file).is_absolute() else (root / req_file)
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def create_app(workspace_dir: str) -> Flask:
    app = Flask(__name__)
    root = Path(workspace_dir)
    parser = SpecParser(str(root))

    @app.route("/")
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.route("/api/state", methods=["GET"])
    def get_state():
        bp = parser.load_blueprint_or_empty()
        req_md = _read_requirement(root, bp)
        prof_path = root / "reports" / "profiling_summary.json"
        kpi_path = root / "reports" / "kpi_validation_results.json"
        prof = json.loads(prof_path.read_text(encoding="utf-8")) if prof_path.exists() else {}
        kpi = json.loads(kpi_path.read_text(encoding="utf-8")) if kpi_path.exists() else {}
        return jsonify({
            "blueprint": bp,
            "visual_catalog": get_full_visual_catalog(str(root)),
            "schema_tables": _extract_dynamic_schema_tables(root, bp),
            "requirement_md": req_md,
            "profiling": prof,
            "kpi_validation": kpi,
        })

    @app.route("/api/doc/<name>", methods=["GET"])
    def api_doc(name):
        if name not in ALLOWED_DOCS:
            return jsonify({"status": "error", "error": "Tài liệu không tồn tại"}), 404
        for base in (root, PACKAGE_DIR):
            p = base / name
            if p.is_file():
                return jsonify({"status": "ok", "name": name, "content": p.read_text(encoding="utf-8")})
        return jsonify({"status": "error", "error": f"Không tìm thấy {name}"}), 404

    @app.route("/api/marketplace", methods=["GET"])
    def api_marketplace():
        try:
            return jsonify({"status": "ok", **marketplace.search(root, request.args.get("q", ""))})
        except Exception as e:
            return jsonify({"status": "error", "error": f"Không tải được danh mục (cần Internet): {e}"}), 500

    @app.route("/api/marketplace/install", methods=["POST"])
    def api_marketplace_install():
        try:
            guid = (request.get_json(force=True) or {}).get("guid", "")
            return jsonify({"status": "ok", **marketplace.install(root, guid)})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/api/revalidate", methods=["POST"])
    def api_revalidate():
        try:
            payload = request.get_json(force=True) or {}
            bp = payload.get("blueprint")
            if bp and not bp.get("is_empty"):
                parser.save_blueprint(bp)
            else:
                bp = parser.load_blueprint_or_empty()
            if bp.get("is_empty"):
                return jsonify({"status": "error", "error": "Chưa có dữ liệu/Requirement. Hãy chạy 'Chạy Tự Động A–Z' trước."}), 400
            result = run_kpi_validation(str(root), blueprint=bp)
            return jsonify({"status": "ok", "meta": result.get("measures_meta", {})})
        except Exception as e:
            return jsonify({"status": "error", "error": f"{e} (đã chạy ETL cho dữ liệu này chưa?)"}), 500

    @app.route("/api/catalog", methods=["GET"])
    def get_catalog():
        return jsonify({"visual_catalog": get_full_visual_catalog(str(root))})

    @app.route("/api/generate", methods=["POST"])
    def api_generate():
        try:
            payload = request.get_json(force=True) or {}
            bp = payload.get("blueprint")
            if bp and not bp.get("is_empty"):
                parser.save_blueprint(bp)
            else:
                bp = parser.load_blueprint_or_empty()
            if bp.get("is_empty"):
                return jsonify({"status": "error", "error": "Chưa có dự án nào. Hãy nạp CSV + Requirement.md và chạy 'Chạy Tự Động A–Z' trước."}), 400
            summary = generate_pbi_artifacts(str(root), bp)
            return jsonify({"status": "ok", "summary": summary})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/api/open-pbi", methods=["POST"])
    def api_open_pbi():
        bp = parser.load_blueprint_or_empty()
        if bp.get("is_empty"):
            return jsonify({"status": "warn", "message": "Chưa có dự án Power BI. Hãy nạp CSV + Requirement.md và chạy 'Chạy Tự Động A–Z' trước."})
        pbip_path = root / bp["project"].get("output_pbi_dir", "output_pbi") / f"{bp['project']['name']}.pbip"
        if not pbip_path.exists():
            return jsonify({"status": "warn", "message": "Chưa có dự án Power BI. Hãy chạy 'Chạy Tự Động A–Z' hoặc '1. Lưu & Sinh File Power BI' trước."})
        ok = launch_powerbi_desktop(str(pbip_path), restart_if_open=True)
        refresh_res = refresh_running_powerbi(wait_for_model_seconds=30)
        return jsonify({
            "status": "ok" if ok else "warn",
            "path": str(pbip_path),
            "refresh": refresh_res,
            "message": "Launched Power BI Desktop and refreshed model" if ok else f"Please open {pbip_path} manually in Power BI Desktop",
        })

    @app.route("/api/refresh-live", methods=["POST"])
    def api_refresh_live():
        res = refresh_running_powerbi(wait_for_model_seconds=12)
        return jsonify({
            "status": "ok" if res.get("status") == "ok" else "warn",
            "result": res,
            "message": "Refreshed live Power BI model" if res.get("status") == "ok" else "No active Power BI Desktop model found",
        })

    @app.route("/api/save-requirement", methods=["POST"])
    def api_save_req():
        payload = request.get_json(force=True)
        content = payload.get("content", "")
        bp = parser.load_blueprint_or_empty()
        req_file = bp.get("project", {}).get("requirement_doc") or "inputs/Requirement.md"
        req_path = Path(req_file) if Path(req_file).is_absolute() else (root / req_file)
        req_path.parent.mkdir(parents=True, exist_ok=True)
        req_path.write_text(content, encoding="utf-8")
        return jsonify({"status": "ok"})

    @app.route("/api/upload-input", methods=["POST"])
    def api_upload_input():
        try:
            f = request.files.get("file")
            if not f or not f.filename:
                return jsonify({"status": "error", "error": "No file uploaded"}), 400
            safe_name = Path(f.filename).name
            inputs_dir = root / "inputs"
            inputs_dir.mkdir(parents=True, exist_ok=True)
            f.save(str(inputs_dir / safe_name))
            return jsonify({"status": "ok", "saved_path": f"inputs/{safe_name}"})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/api/upload-pbiviz", methods=["POST"])
    def api_upload_pbiviz():
        try:
            f = request.files.get("file")
            if not f or not f.filename or not f.filename.lower().endswith(".pbiviz"):
                return jsonify({"status": "error", "error": "Vui lòng chọn file định dạng .pbiviz"}), 400
            cv_dir = root / "custom_visuals"
            cv_dir.mkdir(parents=True, exist_ok=True)
            dest = cv_dir / Path(f.filename).name
            f.save(str(dest))
            meta = inspect_pbiviz_package(dest)
            if not meta:
                return jsonify({"status": "error", "error": "File .pbiviz không chứa package.json hợp lệ"}), 400
            return jsonify({"status": "ok", "visual": meta})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    @app.route("/api/run-pipeline", methods=["POST"])
    def api_run_pipeline():
        try:
            payload = request.get_json(force=True)
            csv_path = payload.get("csv_path") or None
            req_path = payload.get("req_path") or None
            proj_name = payload.get("project_name") or None
            result = run_full_pipeline(
                str(root),
                csv_path=csv_path,
                req_md_path=req_path,
                project_name=proj_name,
                skip_etl=False,
                open_pbi=False,
            )
            return jsonify({"status": "ok", "result": result})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500

    return app


def _find_free_port(start: int) -> int:
    for p in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def start_web_server(workspace_dir: str, port: int = 8505, open_browser: bool = True):
    port = _find_free_port(port)
    app = create_app(workspace_dir)
    url = f"http://127.0.0.1:{port}"
    print(f"[Auto-PBI Web UI] Studio is running at {url}  (workspace: {workspace_dir})")
    print("[Auto-PBI Web UI] Everything stays on this machine. Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    start_web_server(str(root), port=8505)
