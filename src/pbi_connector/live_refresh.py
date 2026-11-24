"""
Live Power BI Desktop Tabular Refresh & DAX Query Executor.
Automatically discovers running Power BI Desktop Analysis Services (msmdsrv.exe) instances
(both standard %LOCALAPPDATA% and Microsoft Store App paths), loads Microsoft.PowerBI.Tabular.dll,
and refreshes all tables from 'NoData' -> 'Ready' so visuals populate without manual clicking.
"""
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List


POWERSHELL_REFRESH_SCRIPT = r"""
$ErrorActionPreference = "Stop"
$procs = Get-Process msmdsrv -ErrorAction SilentlyContinue
if (-not $procs) {
    Write-Output '{"status":"no_instance","message":"No running Power BI Desktop (msmdsrv.exe) found"}'
    exit 0
}
$pbiBin = $null
try {
    $msmdPath = ($procs | Select-Object -First 1).Path
    if ($msmdPath) { $pbiBin = Split-Path $msmdPath -Parent }
} catch {}
if (-not $pbiBin) {
    $store = Get-ChildItem "C:\Program Files\WindowsApps" -Filter "Microsoft.MicrosoftPowerBIDesktop_*" -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($store -and (Test-Path "$($store.FullName)\bin\Microsoft.PowerBI.Tabular.dll")) { $pbiBin = "$($store.FullName)\bin" }
}
if (-not $pbiBin -and (Test-Path "C:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")) {
    $pbiBin = "C:\Program Files\Microsoft Power BI Desktop\bin"
}
if (-not $pbiBin) {
    Write-Output '{"status":"error","message":"Power BI Desktop bin directory not found"}'
    exit 1
}

[System.Reflection.Assembly]::LoadFrom("$pbiBin\Microsoft.PowerBI.Amo.Core.dll") | Out-Null
[System.Reflection.Assembly]::LoadFrom("$pbiBin\Microsoft.PowerBI.Amo.dll") | Out-Null
[System.Reflection.Assembly]::LoadFrom("$pbiBin\Microsoft.PowerBI.Tabular.dll") | Out-Null
[System.Reflection.Assembly]::LoadFrom("$pbiBin\Microsoft.PowerBI.AdomdClient.dll") | Out-Null

$pids = $procs.Id
$conns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $pids -and $_.LocalAddress -eq "127.0.0.1" }
$ports = $conns.LocalPort | Select-Object -Unique

$refreshedPort = $null
$kpis = @{}

foreach ($port in $ports) {
    try {
        $srv = New-Object Microsoft.AnalysisServices.Tabular.Server
        $srv.Connect("Data Source=localhost:$port")
        if ($srv.Databases.Count -gt 0) {
            $db = $srv.Databases[0]
            if ($db.Model.Tables.Count -ge 6) {
                $needsRefresh = $false
                foreach ($t in $db.Model.Tables) {
                    if ($t.Partitions[0].State -ne "Ready") {
                        $t.RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Full)
                        $needsRefresh = $true
                    }
                }
                if ($needsRefresh) {
                    $db.Model.RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Calculate)
                    $null = $db.Model.SaveChanges()
                }
                $refreshedPort = $port

                $adomd = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port")
                $adomd.Open()
                $cmd = $adomd.CreateCommand()
                $cmd.CommandText = 'EVALUATE ROW("TotalFlights", [Total Flights], "DepOTP", [Departure OTP], "ArrOTP", [Arrival OTP], "CancelRate", [Cancellation Rate])'
                $rdr = $cmd.ExecuteReader()
                if ($rdr.Read()) {
                    $kpis["TotalFlights"] = $rdr[0]
                    $kpis["DepOTP"] = [math]::Round([double]$rdr[1] * 100, 2)
                    $kpis["ArrOTP"] = [math]::Round([double]$rdr[2] * 100, 2)
                    $kpis["CancelRate"] = [math]::Round([double]$rdr[3] * 100, 2)
                }
                $adomd.Close()
            }
        }
        $srv.Disconnect()
    } catch {
        continue
    }
}

$out = @{
    status = if ($refreshedPort) { "ok" } else { "not_loaded_yet" }
    port = $refreshedPort
    kpis = $kpis
}
Write-Output ($out | ConvertTo-Json -Compress)
"""


def refresh_running_powerbi(wait_for_model_seconds: int = 30) -> Dict[str, Any]:
    """Wait for Power BI Desktop's local SSAS engine to load the model, then refresh all tables."""
    deadline = time.time() + wait_for_model_seconds
    last_res: Dict[str, Any] = {"status": "timeout"}
    while time.time() < deadline:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", POWERSHELL_REFRESH_SCRIPT],
            capture_output=True,
            text=True,
        )
        stdout = (proc.stdout or "").strip().splitlines()
        if stdout:
            try:
                import json
                last_res = json.loads(stdout[-1])
                if last_res.get("status") == "ok":
                    return last_res
            except Exception:
                pass
        time.sleep(2)
    return last_res
