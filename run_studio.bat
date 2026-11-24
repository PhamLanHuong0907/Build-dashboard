@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONPATH=.

echo ============================================================================
echo   AUTO-PBI DASHBOARD STUDIO (Local Portable Edition)
echo   Moi du lieu luu cuc bo tren may cua ban - khong gui ra ngoai.
echo ============================================================================

set "PY_CMD="
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if !errorlevel! equ 0 (
        set "PY_CMD=py -3"
    ) else (
        where python >nul 2>nul
        if !errorlevel! equ 0 (
            set "PY_CMD=python"
        )
    )
)

if "%PY_CMD%"=="" (
    echo [LOI] Khong tim thay Python 3.10+ tren may nay.
    echo Hay cai Python tu https://www.python.org/downloads/ ^(tich chon "Add python.exe to PATH"^).
    pause
    exit /b 1
)

%PY_CMD% -c "import flask, pandas, pyarrow, yaml, requests" >nul 2>nul
if %errorlevel% neq 0 (
    echo [Lan dau chay] Dang tao moi truong ao .venv va cai dat thu vien tu requirements.txt...
    %PY_CMD% -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        set "PY_CMD=.venv\Scripts\python.exe"
    )
    !PY_CMD! -m pip install --upgrade pip
    !PY_CMD! -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [LOI] Cai dat thu vien that bai. Hay kiem tra ket noi Internet va thu lai.
        pause
        exit /b 1
    )
)

echo [OK] Dang khoi dong Web UI ^(trinh duyet se tu dong mo^)...
%PY_CMD% src\main.py --web --port 8505
pause
