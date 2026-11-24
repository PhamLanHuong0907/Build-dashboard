@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONPATH=.

set "CSV_FILE=%~1"
set "REQ_FILE=%~2"
set "PROJ_NAME=%~3"

if "%CSV_FILE%"=="" set "CSV_FILE=sample_data\sample_sales.csv"
if "%REQ_FILE%"=="" set "REQ_FILE=Requirement_Template.md"
if "%PROJ_NAME%"=="" set "PROJ_NAME=Sales_Demo_Dashboard"

set "PY_CMD="
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if !errorlevel! equ 0 (
        set "PY_CMD=py -3"
    ) else (
        set "PY_CMD=python"
    )
)

echo ============================================================================
echo   AUTO-PBI PIPELINE RUNNER (CLI A-Z)
echo   Input CSV : %CSV_FILE%
echo   Input Spec: %REQ_FILE%
echo   Project   : %PROJ_NAME%
echo ============================================================================
%PY_CMD% src\main.py --csv "%CSV_FILE%" --req "%REQ_FILE%" --project-name "%PROJ_NAME%" --open-pbi
pause
