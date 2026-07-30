@echo off
rem Detiene al guardian y a la interfaz de I.R.I.S. (los procesos python del proyecto)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like '%%python%%'\" | Where-Object { $_.CommandLine -match 'guardia\.py|main\.py' -and $_.CommandLine -match 'Mi-JARVIS' } | ForEach-Object { Write-Host ('Cerrando PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force }"
echo I.R.I.S. detenida.
pause
