@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo 未找到 Python。请先安装 Python 3.10 及以上版本，并勾选“Add Python to PATH”。
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo   简化广州中考公办高中录取模拟系统
echo.
echo   启动后请用浏览器打开：http://127.0.0.1:8000
echo   保持此窗口打开；关闭窗口即可停止服务。
echo ============================================================
echo.

python run.py

echo.
echo 服务已停止。按任意键关闭窗口。
pause >nul
