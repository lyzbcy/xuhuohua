@echo off
chcp 936 >nul
title 续火花 - 引擎一键安装
cd /d "%~dp0"

echo ============================================
echo   续火花 运行引擎 一键安装（全自动）
echo   全程约 5-10 分钟，请保持网络畅通
echo   不需要你操作任何东西，等它跑完即可
echo ============================================
echo.

if exist "runtime\python.exe" (
  echo [√] 嵌入式 Python 已就位
  goto :deps
)

echo [1/4] 下载嵌入式 Python（约 11MB，免安装版）...
if not exist "runtime_tmp" mkdir runtime_tmp
curl -L --connect-timeout 15 -o runtime_tmp\py.zip "https://mirrors.huaweicloud.com/python/3.12.10/python-3.12.10-embed-amd64.zip" 2>nul
if not exist "runtime_tmp\py.zip" (
  echo       华为镜像失败，改用官方源...
  curl -L --connect-timeout 15 -o runtime_tmp\py.zip "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
)
if not exist "runtime_tmp\py.zip" (
  echo [X] Python 下载失败：请检查网络（可开代理）后重新双击本脚本
  pause
  exit /b 1
)
powershell -NoProfile -Command "Expand-Archive -Path runtime_tmp\py.zip -DestinationPath runtime -Force"
echo import site>> runtime\python312._pth
echo [√] Python 就位

:deps
echo [2/4] 准备 pip...
runtime\python.exe -m pip --version >nul 2>&1
if errorlevel 1 (
  curl -L -o runtime_tmp\get-pip.py "https://bootstrap.pypa.io/get-pip.py"
  runtime\python.exe runtime_tmp\get-pip.py -q --no-warn-script-location -i https://pypi.tuna.tsinghua.edu.cn/simple
)
echo [√] pip 就位

echo [3/4] 安装抖音引擎依赖（约 2-4 分钟）...
runtime\python.exe -m pip install -q --no-warn-script-location --target douyin-auto-fire\deps -r douyin-auto-fire\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
  echo       清华镜像失败，改用官方源重试...
  runtime\python.exe -m pip install -q --no-warn-script-location --target douyin-auto-fire\deps -r douyin-auto-fire\requirements.txt
  if errorlevel 1 ( echo [X] 依赖安装失败，请检查网络后重新双击本脚本 & pause & exit /b 1 )
)
echo [√] 依赖就位
rem 嵌入式 Python 的 _pth 模式无视 PYTHONPATH，必须把 deps 写进 _pth
findstr /C:"douyin-auto-fire\deps" runtime\python312._pth >nul 2>&1 || echo ..\douyin-auto-fire\deps>> runtime\python312._pth

echo [4/4] 下载浏览器组件（约 300MB，最大的一步，请耐心等待）...
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
runtime\python.exe -c "import sys; sys.path.insert(0, r'douyin-auto-fire\deps'); from playwright.__main__ import main; sys.argv=['playwright','install','chromium']; main()"
if errorlevel 1 (
  echo       国内镜像失败，改用官方源重试（较慢）...
  set PLAYWRIGHT_DOWNLOAD_HOST=
  runtime\python.exe -c "import sys; sys.path.insert(0, r'douyin-auto-fire\deps'); from playwright.__main__ import main; sys.argv=['playwright','install','chromium']; main()"
  if errorlevel 1 ( echo [X] 浏览器下载失败，请检查网络后重新双击本脚本 & pause & exit /b 1 )
)
echo [√] 浏览器就位

echo.
echo ============================================
echo   [OK] 安装完成！现在可以：
echo   1. 双击 xuhuohua.exe 打开控制台
echo   2. 到「抖音」页扫码登录，然后点「演练」验证
echo ============================================
pause
