@echo off
chcp 936 >nul
cd /d "%~dp0..\douyin-auto-fire"
where python >nul 2>&1
if errorlevel 1 (
  echo [X] 未检测到 Python。请先安装 Python 3.11+（安装时勾选 Add to PATH），然后重新运行本脚本。
  pause
  exit /b 1
)
if not exist .venv (
  echo [1/3] 创建虚拟环境...
  python -m venv .venv
)
echo [2/3] 安装依赖...
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 ( echo [X] 依赖安装失败，请检查网络后重试 & pause & exit /b 1 )
echo [3/3] 下载浏览器组件（约 300MB，请耐心等待）...
.venv\Scripts\python -m playwright install chromium
echo.
echo [OK] 抖音引擎安装完成！回到控制台即可使用抖音续火花。
pause
