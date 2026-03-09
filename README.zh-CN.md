# 🦞 OpenClaw Desk

[English](README.md)

🦞 一个面向 OpenClaw Gateway 的轻量级桌面控制器，内置仪表盘视图，并提供简洁的本地控制面板。

------

## ✨ 功能特性

- 🚀 启动、停止和重启本地 OpenClaw Gateway
- 📊 实时查看网关状态
- 🌐 直接在桌面应用内打开 OpenClaw Dashboard
- 🖥️ 通过系统托盘进行快速访问和后台运行
- 🦞 交互式 Welcome Page 欢迎页，支持将小龙虾吉祥物移动到指定位置

------

## ⚡ 快速开始

### 预览

当前桌面界面预览：

![OpenClaw Desk Screenshot](assets/Screenshot.png)

------

### 从源码运行

1. 创建虚拟环境，或激活已有虚拟环境。
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 启动应用：

```bash
python main.py
```

------

## 🧩 环境要求

- Python **3.10+**
- 推荐在 Windows 桌面环境中运行
- 需要已在本地安装 **OpenClaw**，并能被系统识别
- 如果你要使用内嵌仪表盘视图，需要具备 **Qt WebEngine**

如果未安装 OpenClaw，应用会保持锁定的错误状态，并提示先完成安装。

------

## 🔧 安装 OpenClaw

- GitHub: https://github.com/openclaw/openclaw
- 文档: https://docs.openclaw.ai/

------

## 📂 项目结构

```text
.
├── main.py
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
├── README.md
└── README.zh-CN.md
```

**文件说明**

- `assets/emoji.png`
  桌面应用使用的图标资源。
- `utils/emoji_icon.py`
  用于根据 emoji 生成自定义图标的工具脚本。

------

## 📝 说明

- 这个桌面应用默认管理运行在 **18789** 端口上的本地 **OpenClaw Gateway** 进程。
- 内嵌浏览器依赖你当前环境中的 **Qt WebEngine** 支持。
- 如果 WebEngine 不可用，项目仍可通过降级 UI 暴露仪表盘 URL。

------

## 📜 许可证

MIT License © 2026 wobudaoa

OpenClaw Desk 基于 MIT License 发布。

本项目是 OpenClaw 的独立桌面封装，**与 OpenClaw 项目不存在隶属关系，也未获得其背书**。

完整许可证文本见 `LICENSE` 文件。
