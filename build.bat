@echo off
chcp 65001 >nul
rem ============================================
rem  桌面助手 · Windows 一键打包脚本
rem  用法：双击 build.bat，或命令行执行
rem  产物：dist\DesktopAssistant.exe（单文件免安装）
rem ============================================
cd /d "%~dp0"

echo [1/3] 安装依赖（PySide6 + psutil + PyInstaller）...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 ( echo 依赖安装失败，请检查 Python 环境 & pause & exit /b 1 )

echo [2/3] 生成应用图标...
python build_icon.py
if errorlevel 1 ( echo 图标生成失败，继续使用默认图标 )

echo [3/3] 使用 PyInstaller 打包为单文件 exe...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name DesktopAssistant ^
  --icon assets\app.ico ^
  main.py
if errorlevel 1 ( echo 打包失败 & pause & exit /b 1 )

echo.
echo 打包完成：dist\DesktopAssistant.exe
echo 双击即可运行；也可复制到任意电脑使用（无需安装 Python）。
pause
