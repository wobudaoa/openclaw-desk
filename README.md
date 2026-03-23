<div align="center">

# 🦞 OpenClaw Desk

**[简体中文](README.zh-CN.md) | English**

🦞 A lightweight desktop controller for the OpenClaw Gateway, with an embedded dashboard view, local controls, and a cleaner daily workflow for Windows users.

[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

</div>

------

## ✨ Features

- 🚀 Support starting, stopping, and restarting the local OpenClaw Gateway
- 📊 Support real-time gateway status in the desktop UI
- 🌐 Support opening the OpenClaw Dashboard directly inside the app
- 😡 Support an error screen for installation failures, gateway errors, and dashboard fallback states
- 🧠 Support getting Skills from the desktop app without switching back to a terminal
- 🧩 Support plugin downloads and the full plugin installation flow from the desktop app
- 📋 Dedicated plugin list page with refresh, cached loading, and enable / disable actions
- 🔓 Support external link access through Expose Mode inside the embedded browser
- 🌍 Support English / Simplified Chinese language switching
- 💾 Support persistent preferences for language, expose mode, gateway port, window size, and more
- ⚙️ Support settings for local directory access, port changes, expose mode, language, and app information
- 🖥️ Support optionally keeping the gateway running after closing the app
- 🦞 Interactive welcome page with the movable lobster mascot

------

## ⚡ Quickstart

### Preview

Current desktop UI preview:

![OpenClaw Desk Screenshot](assets/Screenshot-running.png)

![OpenClaw Desk Screenshot](assets/Screenshot.png)

------

### 💥 Direct Installation

If you only want to use **ClawDesk** quickly, without configuring Python or building from source, download the Windows installer directly.

1. Download the latest installer:
   **ClawDesk-Setup-1.0.1.exe**
   https://github.com/wobudaoa/openclaw-desk/releases/download/v1.0.1/ClawDesk-Setup-1.0.1.exe
2. Run the installer and follow the setup steps.

After installation, you can launch **ClawDesk** from:

- Start Menu: **ClawDesk**
- Desktop shortcut, if you chose to create one
- `ClawDesk.exe` in the installation directory

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

4. If you use Conda, you can edit `openclaw-desk.bat`, replace the environment name `openclaw` with your own, then launch it by double-clicking the script.

------

## 🫡 Usage

- If installed through the packaged installer, press `Win+Q` and search for `ClawDesk`.
- The header provides direct entry points for the dashboard, plugin list, error info, and settings.
- `Get Plugins` lets you download plugins directly from the desktop app.
- `Get Skills` lets you get skills directly from the desktop app.
- The plugin list page loads current plugin states, supports refresh, and allows enable / disable actions.
- `Settings` lets you open the local config directory, change the gateway port, switch Expose Mode, and change the app language.
- The app remembers language, expose mode, port, window size, and cached plugin list data across restarts.
- When closing, you can choose:
  - `Yes` = stop gateway and exit
  - `No` = keep gateway running and exit
  - `Cancel` = stay in the app

------

## 🧩 Requirements

- Python **>=3.10, <=3.12**
- Windows desktop environment recommended
- **OpenClaw** must already be installed locally and available in the system path
- **Qt WebEngine** is required for the embedded dashboard view

If OpenClaw is not installed yet, the app stays in an error state and prompts you to install it first.

------

## 🔧 Install OpenClaw

- GitHub: https://github.com/openclaw/openclaw
- Docs: https://docs.openclaw.ai/

------

## 📝 Notes

- ClawDesk manages a local **OpenClaw Gateway** process on port **18789** by default, and you can change it at any time in Settings.
- The embedded browser stays local-only by default. When **Expose Mode** is enabled, clicked external `http/https` links can open inside the embedded browser.
- Settings are written to local `config.json`, and plugin list data is cached for faster startup.
- If WebEngine is unavailable, the app can still show fallback UI and expose the dashboard URL.

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
|   `-- translations.py
|-- utils/
|   `-- emoji_icon.py
|-- README.md
`-- README.zh-CN.md
```

------

## 📜 License

MIT License Copyright (c) 2026 wobudaoa

OpenClaw Desk is released under the MIT License.

This project is an independent desktop wrapper for OpenClaw. It is not affiliated with or endorsed by the OpenClaw project.

See the `LICENSE` file for the full license text.

------

## ⭐ Star History

<div align="center">

[![Star History Chart](https://api.star-history.com/image?repos=wobudaoa/openclaw-desk&type=date&legend=top-left)](https://www.star-history.com/?repos=wobudaoa%2Fopenclaw-desk&type=date&legend=top-left)

</div>
