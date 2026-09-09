@echo off
cd /d "%~dp0"
if not exist "software\.venv\Scripts\pythonw.exe" (
  powershell -NoProfile -EncodedCommand QQBkAGQALQBUAHkAcABlACAALQBBAHMAcwBlAG0AYgBsAHkATgBhAG0AZQAgAFMAeQBzAHQAZQBtAC4AVwBpAG4AZABvAHcAcwAuAEYAbwByAG0AcwA7ACAAWwBTAHkAcwB0AGUAbQAuAFcAaQBuAGQAbwB3AHMALgBGAG8AcgBtAHMALgBNAGUAcwBzAGEAZwBlAEIAbwB4AF0AOgA6AFMAaABvAHcAKAAnAO1+a3CxgqdjNlLwUy9UqFLEfvZOOn8xWQz/71P9gKuIQGfSa2+P9k7viyBSAjD3i4piLGeHZfZOOVmgUmVRQGfSa2+P9k59dg1UVVMOVAz/zZGwZcxT+1EsZ/5WB2gCMCcALAAnAO1+a3CxgqdjNlLwUycAKQAgAHwAIABPAHUAdAAtAE4AdQBsAGwA
  exit /b
)
start "" "software\.venv\Scripts\pythonw.exe" main.py
