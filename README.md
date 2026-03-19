<div align="center">

# 🦞 OpenClaw Desk

**[简体中文](README.zh-CN.md) | English**

🦞 A lightweight desktop controller for the OpenClaw Gateway, with an embedded dashboard view and a simple local control panel.

[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

</div>

------

## ✨ Features

- 🚀 Start, stop, and restart the local OpenClaw Gateway
- 📊 View gateway status in real time
- 🌐 Open the OpenClaw Dashboard directly inside the desktop app
- 🖥️ Optionally keep OpenClaw running in the background after closing the window
- 🦞 Interactive Welcome Page where the pet lobster can be moved to a target position

------

## ⚡ Quickstart

### Preview

Current desktop UI preview:

![OpenClaw Desk Screenshot](assets/Screenshot-running.png)

![OpenClaw Desk Screenshot](assets/Screenshot.png)

------

### 💥 Direct Installation

If you only want to use **ClawDesk** quickly, without configuring a Python environment or building manually, you can download the official Windows installer directly.

1. Download the installer from the latest release:
   **ClawDesk-Setup-1.0.0.exe**
   https://github.com/wobudaoa/openclaw-desk/releases/download/v1.0.0/ClawDesk-Setup-1.0.0.exe

2. Run the installer and follow the setup steps.

After installation, you can launch **ClawDesk** from:

- The Start Menu: **ClawDesk**
- The desktop shortcut, if you chose to create one during setup
- `ClawDesk.exe` in the installation directory

Once started, you can manage the **OpenClaw Gateway** from the desktop UI and open the dashboard directly inside the app.

------

### Run from Source

1. Create and activate a Python virtual environment. Conda is recommended, with Python **3.10 - 3.12**.

2. Install dependencies from the project root:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python main.py
```

4. If you use Conda, you can also edit `openclaw-desk.bat`, replace the environment name `openclaw` with your own, then launch it by double-clicking the script. The batch file looks like this:

```batch
@echo off
chcp 65001 >nul
title OpenClaw Launcher
echo ========================================
echo      OpenClaw Auto Launcher
echo ========================================
echo.

:: Activate the Conda environment. It is called openclaw here.
call conda activate openclaw

:: Check whether activation succeeded
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate environment. Please check:
    echo     1. Whether Conda is installed correctly
    echo     2. Whether the openclaw environment exists
    echo     3. Run: conda info --envs
    pause
    exit /b 1
)

echo [OK] Conda environment activated: openclaw
echo.

:: Run the Python app
echo [START] Launching OpenClaw Desk...
python main.py

:: Pause after the app exits
echo.
echo [EXIT] Program closed.
pause
```

------

## 🫡 Usage Instructions

- If installed via the installation package, simply press Win+Q and search for ClawDesk!
- When closing, you will be prompted with the following three options:
    - Yes = Stop gateway and exit
    - No = Keep gateway running and exit
    - Cancel = Stay in application

------

## 🧩 Requirements

- Python **>=3.10, <=3.12**
- Running on a Windows desktop environment is recommended
- **OpenClaw** must already be installed locally and available in the system path
- **Qt WebEngine** is required if you want to use the embedded dashboard view

If OpenClaw is not installed yet, the app will remain in a locked error state and prompt you to install it first.

------

## 🔧 Install OpenClaw

- GitHub: https://github.com/openclaw/openclaw
- Docs: https://docs.openclaw.ai/

------

## 📂 Project Structure

```text
.
|-- main.py
|-- openclaw-desk.bat
|-- requirements.txt
|-- assets/
|   |-- emoji.png
|-- src/
|   |-- browser_view.py
|   |-- gateway_manager.py
|   |-- main_window.py
|   |-- tray_icon.py
|-- utils/
|   |-- emoji_icon.py
|-- README.md
`-- README.zh-CN.md
```

**File Description**

- `assets/emoji.png`
  Icon asset used by the desktop application.
- `utils/emoji_icon.py`
  Utility script for generating a custom icon from an emoji.

------

## 📝 Notes

- This desktop app manages a local **OpenClaw Gateway** process running on port **18789** by default.
- The embedded browser depends on **Qt WebEngine** support in the current environment.
- If WebEngine is unavailable, the app can still expose the dashboard URL through the fallback UI.

------

## 📜 License

MIT License © 2026 wobudaoa

OpenClaw Desk is released under the MIT License.

This project is an independent desktop wrapper for OpenClaw. It is **not affiliated with or endorsed by the OpenClaw project**.

## ⭐ Star History

<div align="center">

[![Star History Chart](https://api.star-history.com/image?repos=wobudaoa/openclaw-desk&type=date&legend=top-left)](https://www.star-history.com/?repos=wobudaoa%2Fopenclaw-desk&type=date&legend=top-left)

</div>

See the `LICENSE` file for the full license text.
