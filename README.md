# 🦞 OpenClaw Desk

[简体中文](README.zh-CN.md)

🦞 A lightweight desktop controller for the OpenClaw Gateway, with an embedded dashboard view and a simple local control panel.

------

## ✨ Features

- 🚀 Start, stop, and restart the local OpenClaw Gateway
- 📊 View gateway status in real time
- 🌐 Open the OpenClaw Dashboard directly inside the desktop app
- 🖥️ Use the system tray for quick access and background operation
- 🦞 Interactive welcome page where the pet lobster can be moved to a specified position

------

## ⚡ Quickstart

### Preview

Current desktop UI preview:

![OpenClaw Desk Screenshot](assets/Screenshot.png)

------

### Run from source

1. Create and activate a Python virtual environment. Conda is recommended, with Python **3.10 - 3.12**.
2. Install dependencies from the project root:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python main.py
```

4. If you use Conda, you can also edit `openclaw-desk.bat`, replace the `openclaw` environment name with your own, and launch the app by double-clicking the script.

------

## 🧩 Requirements

- Python **>=3.10, <=3.12**
- Windows desktop environment recommended
- **OpenClaw** installed locally and available to the system
- **Qt WebEngine** available if you want to use the embedded dashboard view

If OpenClaw is not installed, the app will stay in a locked error state and prompt you to install it first.

------

## 🔧 Install OpenClaw

- GitHub: https://github.com/openclaw/openclaw
- Docs: https://docs.openclaw.ai/

------

## 📂 Project Structure

```
.
├── main.py
├── openclaw-desk.bat
├── requirements.txt
├── assets/
│   └── emoji.png
├── src/
│   ├── browser_view.py
│   ├── gateway_manager.py
│   ├── main_window.py
│   └── tray_icon.py
├── utils/
│   └── emoji_icon.py
└── README.md
```

**File description**

- `assets/emoji.png`
  App icon asset used by the desktop application.
- `utils/emoji_icon.py`
  Utility script for generating a custom icon from an emoji.

------

## 📝 Notes

- The desktop app manages a local **OpenClaw Gateway** process on port **18789** by default.
- The embedded browser depends on **Qt WebEngine** support in your environment.
- If WebEngine is unavailable, the app can still expose the dashboard URL through the fallback UI.

------

## 📜 License

MIT License © 2026 wobudaoa

OpenClaw Desk is released under the MIT License.

This project is an independent desktop wrapper for OpenClaw and is **not affiliated with or endorsed by the OpenClaw project**.

See the `LICENSE` file for the full license text.
