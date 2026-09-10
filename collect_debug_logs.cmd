@echo off
setlocal

set "TOKENPET_LOG_SOURCE=%LOCALAPPDATA%\TokenPet\logs"
set "UNITY_LOG_SOURCE=%USERPROFILE%\AppData\LocalLow\TokenPet\TokenPet Unity Renderer PoC"
set "TOKENPET_DEBUG_DIR=%USERPROFILE%\Desktop\TokenPet-debug-logs-%RANDOM%"
set "TOKENPET_DEBUG_ZIP=%TOKENPET_DEBUG_DIR%.zip"

mkdir "%TOKENPET_DEBUG_DIR%" >nul 2>&1
if exist "%TOKENPET_LOG_SOURCE%\TokenPet-runtime.log" copy /y "%TOKENPET_LOG_SOURCE%\TokenPet-runtime.log" "%TOKENPET_DEBUG_DIR%\" >nul
if exist "%TOKENPET_LOG_SOURCE%\TokenPet-runtime.previous.log" copy /y "%TOKENPET_LOG_SOURCE%\TokenPet-runtime.previous.log" "%TOKENPET_DEBUG_DIR%\" >nul
if exist "%UNITY_LOG_SOURCE%\Player.log" copy /y "%UNITY_LOG_SOURCE%\Player.log" "%TOKENPET_DEBUG_DIR%\Unity-Player.log" >nul
if exist "%UNITY_LOG_SOURCE%\Player-prev.log" copy /y "%UNITY_LOG_SOURCE%\Player-prev.log" "%TOKENPET_DEBUG_DIR%\Unity-Player-prev.log" >nul

(
  echo TokenPet debug bundle
  echo Created: %DATE% %TIME%
  echo Windows: %OS%
  echo Processor architecture: %PROCESSOR_ARCHITECTURE%
) > "%TOKENPET_DEBUG_DIR%\system-summary.txt"

tar.exe -a -c -f "%TOKENPET_DEBUG_ZIP%" -C "%TOKENPET_DEBUG_DIR%" .
if errorlevel 1 (
  echo Failed to create ZIP. Logs remain in:
  echo %TOKENPET_DEBUG_DIR%
  pause
  exit /b 1
)

echo Debug logs collected:
echo %TOKENPET_DEBUG_ZIP%
explorer.exe /select,"%TOKENPET_DEBUG_ZIP%"
pause
