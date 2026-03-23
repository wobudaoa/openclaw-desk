"""Shared UI translations for OpenClaw Desktop."""

from __future__ import annotations


DEFAULT_LANGUAGE = "en"


def app_base_dir() -> Path:
    """Return the writable application base directory for local config/log files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def app_config_path() -> Path:
    """Path to the persistent desktop config file."""
    return app_base_dir() / "config.json"


def ensure_app_config_dir() -> Path:
    """Ensure the local config directory exists before reading or writing config.json."""
    base_dir = app_base_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def load_app_config() -> dict:
    """Load the desktop config JSON; create an empty config file when missing."""
    ensure_app_config_dir()
    path = app_config_path()
    if not path.exists():
        save_app_config({})
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("failed to load app config %s: %s", path, exc)
        save_app_config({})
        return {}
    return data if isinstance(data, dict) else {}


def save_app_config(config: dict) -> None:
    """Persist desktop config as UTF-8 JSON."""
    ensure_app_config_dir()
    path = app_config_path()
    try:
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("failed to save app config %s: %s", path, exc)

TRANSLATIONS = {
    "en": {
        "app_title": "ClawDesk🦞",
        "nav_welcome": "Welcome",
        "nav_start": "Start",
        "nav_stop": "Stop",
        "nav_restart": "Restart",
        "nav_dashboard": "Dashboard",
        "nav_plugins": "Plugins",
        "nav_error_info": "Error Info",
        "nav_get_more": "Get More",
        "nav_open_clawhub": "Open ClawHub",
        "nav_settings": "Settings",
        "label_status": "Status:",
        "label_port": "Port:",
        "footer_ready": "Ready",
        "welcome_title": "Welcome to OpenClaw Desktop",
        "welcome_desc": "Start the gateway to access the OpenClaw dashboard",
        "welcome_hint": "Click anywhere with your mouse to guide the lobster around.",
        "welcome_quick_start_html": "<p style='color: #666; margin-top: 30px;'><b>Quick Start:</b><br>1. Click <b>Start</b> in the header to launch the gateway<br>2. Wait for the status to show <b>Running</b><br>3. Click <b>Dashboard</b> to access the web interface</p>",
        "missing_title": "Please install OpenClaw before using this desktop app.",
        "dialog_exit_title": "Exit OpenClaw Desktop",
        "dialog_exit_question": "Do you want to stop the gateway when exiting?",
        "dialog_exit_info_with_cancel": "Yes = Stop gateway and exit\nNo = Keep gateway running and exit\nCancel = Stay in application",
        "dialog_exit_info_without_cancel": "Yes = Stop gateway and exit\nNo = Keep gateway running and exit",
        "dialog_get_more_title": "Get More",
        "get_more_update_tab": "OpenClaw Update",
        "get_more_plugins_tab": "Get Plugins",
        "get_more_skills_tab": "Get Skills",
        "get_more_output_placeholder": "Command output will appear here.",
        "get_more_check_latest": "Check Latest Version",
        "get_more_install_update": "Install Update",
        "get_more_use_mirror": "Use npm mirror: https://registry.npmmirror.com",
        "get_more_plugin_placeholder": "Enter plugin name",
        "get_more_skill_placeholder": "Enter skill name",
        "get_more_install_plugins": "Get Plugins",
        "get_more_install_skills": "Get Skills",
        "get_more_checking": "Checking...",
        "get_more_updating": "Updating...",
        "get_more_installing": "Installing...",
        "get_more_update_check_completed": "Update status check completed.",
        "get_more_update_completed": "OpenClaw update completed.",
        "get_more_plugin_completed": "Plugin installation completed successfully.",
        "get_more_skill_completed": "Skill installation completed successfully.",
        "get_more_enter_plugin": "Please enter a plugin name.",
        "get_more_enter_skill": "Please enter a skill name.",
        "plugins_dialog_title": "Plugins",
        "plugins_refresh": "Update Plugin List",
        "plugins_add_tooltip": "Get More Plugins",
        "plugins_loading": "Loading plugin list...",
        "plugins_empty": "No plugins were found.",
        "plugins_failed": "Failed to load plugin list.",
        "plugins_status_enabled": "Enabled",
        "plugins_status_disabled": "Disabled",
        "plugins_count": "{count} plugin(s)",
        "plugins_count_summary": "{count} plugin(s). <span style=\"color:#22c55e; font-weight:600;\">{enabled} enabled</span>, <span style=\"color:#ef4444; font-weight:600;\">{disabled} disabled</span>.",
        "plugins_toggle_dialog_title": "Plugin Status",
        "plugins_toggle_enable_title": "Enable Plugin",
        "plugins_toggle_disable_title": "Disable Plugin",
        "plugins_toggle_enable_body": "Enable plugin `{name}`?",
        "plugins_toggle_disable_body": "Disable plugin `{name}`?",
        "plugins_toggle_enable_confirm": "Enable",
        "plugins_toggle_disable_confirm": "Disable",
        "plugins_toggle_cancel": "Cancel",
        "plugins_toggle_close": "Close",
        "plugins_toggle_output_placeholder": "Plugin command output will appear here.",
        "plugins_toggle_enable_completed": "Plugin enabled successfully.",
        "plugins_toggle_disable_completed": "Plugin disabled successfully.",
        "plugins_toggle_busy_enable": "Enabling plugin. Do not close this window.",
        "plugins_toggle_busy_disable": "Disabling plugin. Do not close this window.",
        "settings_title": "Settings",
        "settings_tab_general": "General",
        "settings_tab_language": "Language",
        "settings_tab_about": "About",
        "settings_general_title": "General Settings",
        "settings_general_body": "",
        "settings_general_local_dir_title": "Local Directory",
        "settings_general_local_dir_body": "Click the field to reveal the current local OpenClaw config directory, or open it directly with the button on the right.",
        "settings_general_expose_title": "Expose Mode",
        "settings_general_expose_body": "When enabled, clicked external links may open inside the embedded browser instead of being limited to localhost only.",
        "settings_general_port_title": "Port",
        "settings_general_port_body": "Click the field to reveal the current gateway port. Use the edit button inside the field to enter edit mode, then apply and restart to switch the local dashboard port.",
        "settings_general_port_masked": "Port",
        "settings_general_apply_port": "Apply and Restart",
        "settings_general_open_dir": "Open Folder",
        "settings_port_invalid_title": "Invalid Port",
        "settings_port_invalid_body": "Enter a valid port number between 1 and 65535.",
        "settings_port_saved_only": "Port saved. Start the gateway to use the new port.",
        "settings_language_title": "Language",
        "settings_language_body": "Use the switch below to change the app display language.",
        "settings_about_title": "About",
        "settings_about_body": "This page can hold version information, update notes, and diagnostics entry points.",
        "settings_language_english": "English",
        "settings_language_zh": "简体中文",
        "error_gateway_title": "Gateway Error",
        "error_dashboard_title": "Dashboard Error",
        "error_summary_title": "Summary",
        "error_no_output": "No error output was captured.",
        "error_gateway_reported": "Gateway reported an error.",
        "message_missing_openclaw_status": "OpenClaw is not installed on this computer",
        "message_starting_gateway": "Starting gateway...",
        "message_restarting_gateway": "Restarting gateway...",
        "message_stopping_gateway": "Stopping gateway...",
        "message_dashboard_loading": "Dashboard is loading...",
        "message_dashboard_loaded": "Dashboard loaded successfully",
        "message_dashboard_failed": "Failed to load dashboard",
        "message_gateway_error": "Gateway error",
        "message_gateway_stopped": "Gateway stopped",
        "message_dashboard_ready": "Dashboard ready",
        "warning_gateway_not_running_title": "Gateway Not Running",
        "warning_gateway_not_running_body": "Please start the OpenClaw gateway first.",
        "status_stopped": "Stopped",
        "status_starting": "Starting...",
        "status_loading": "Loading...",
        "status_running": "Running",
        "status_stopping": "Stopping...",
        "status_error": "Error",
        "status_unknown": "Unknown"
    },
    "zh-CN": {
        "app_title": "ClawDesk🦞",
        "nav_welcome": "欢迎页",
        "nav_start": "启动",
        "nav_stop": "停止",
        "nav_restart": "重启",
        "nav_dashboard": "控制台",
        "nav_plugins": "插件",
        "nav_error_info": "错误信息",
        "nav_get_more": "获取更多",
        "nav_open_clawhub": "打开技能市场",
        "nav_settings": "设置",
        "label_status": "状态:",
        "label_port": "端口:",
        "footer_ready": "就绪",
        "welcome_title": "欢迎使用 OpenClaw 桌面端",
        "welcome_desc": "启动网关以访问 OpenClaw 控制台",
        "welcome_hint": "点击任意位置，用鼠标引导龙虾移动。",
        "welcome_quick_start_html": "<p style='color: #666; margin-top: 30px;'><b>快速开始:</b><br>1. 点击顶部的 <b>启动</b> 按钮启动网关<br>2. 等待状态显示为 <b>运行中</b><br>3. 点击 <b>控制台</b> 打开 Web 界面</p>",
        "missing_title": "请先安装 OpenClaw，再使用这个桌面应用。",
        "dialog_exit_title": "退出 OpenClaw 桌面端",
        "dialog_exit_question": "退出时是否停止网关？",
        "dialog_exit_info_with_cancel": "是： 停止Openclaw并退出应用\n否： 保持Openclaw后台运行并退出应用\n取消： 留在应用中",
        "dialog_exit_info_without_cancel": "是： 停止Openclaw并退出应用\n否： 保持Openclaw后台运行并退出应用",
        "dialog_get_more_title": "获取更多",
        "get_more_update_tab": "OpenClaw 更新",
        "get_more_plugins_tab": "下载插件",
        "get_more_skills_tab": "下载技能",
        "get_more_output_placeholder": "命令输出将显示在这里。",
        "get_more_check_latest": "检查最新版本",
        "get_more_install_update": "安装更新",
        "get_more_use_mirror": "启用 npm 镜像源: https://registry.npmmirror.com",
        "get_more_plugin_placeholder": "输入插件名称",
        "get_more_skill_placeholder": "输入技能名称",
        "get_more_install_plugins": "获取插件",
        "get_more_install_skills": "下载技能",
        "get_more_checking": "检查中...",
        "get_more_updating": "更新中...",
        "get_more_installing": "安装中...",
        "get_more_update_check_completed": "版本检查完成。",
        "get_more_update_completed": "OpenClaw 更新完成。",
        "get_more_plugin_completed": "插件安装成功。",
        "get_more_skill_completed": "技能安装成功。",
        "get_more_enter_plugin": "请输入插件名称。",
        "get_more_enter_skill": "请输入技能名称。",
        "plugins_dialog_title": "插件列表",
        "plugins_refresh": "刷新",
        "plugins_add_tooltip": "获取插件",
        "plugins_loading": "正在加载插件列表...",
        "plugins_empty": "未找到任何插件。",
        "plugins_failed": "加载插件列表失败。",
        "plugins_status_enabled": "已启用",
        "plugins_status_disabled": "未启用",
        "plugins_count": "共 {count} 个插件",
        "plugins_count_summary": "共 {count} 个插件. 其中 <span style=\"color:#22c55e; font-weight:600;\">{enabled} 个已启用</span>， <span style=\"color:#ef4444; font-weight:600;\">{disabled} 个未启用</span>。",
        "plugins_toggle_dialog_title": "插件状态",
        "plugins_toggle_enable_title": "启用插件",
        "plugins_toggle_disable_title": "禁用插件",
        "plugins_toggle_enable_body": "是否启用插件 `{name}`？",
        "plugins_toggle_disable_body": "是否禁用插件 `{name}`？",
        "plugins_toggle_enable_confirm": "启用",
        "plugins_toggle_disable_confirm": "禁用",
        "plugins_toggle_cancel": "取消",
        "plugins_toggle_close": "关闭",
        "plugins_toggle_output_placeholder": "插件命令输出将显示在这里。",
        "plugins_toggle_enable_completed": "插件启用成功。",
        "plugins_toggle_disable_completed": "插件禁用成功。",
        "plugins_toggle_busy_enable": "插件启用中，请不要关闭此窗口。",
        "plugins_toggle_busy_disable": "插件关闭中，请不要关闭此窗口。",
        "settings_title": "设置",
        "settings_tab_general": "通用",
        "settings_tab_language": "语言",
        "settings_tab_about": "关于",
        "settings_general_title": "通用设置",
        "settings_general_body": "",
        "settings_general_local_dir_title": "本地目录",
        "settings_general_local_dir_body": "点击输入栏可显示当前本地 OpenClaw 配置目录，也可以使用右侧按钮直接打开该文件夹。",
        "settings_general_expose_title": "暴露模式",
        "settings_general_expose_body": "启用后，页面内点击的外部链接可以在内置浏览器中打开，而不再只限制访问 localhost。",
        "settings_general_port_title": "端口",
        "settings_general_port_body": "点击输入框可显示当前网络端口。点击输入框内的编辑按钮后可进入编辑状态，随后使用应用并重启来切换本地控制台端口。",
        "settings_general_port_masked": "端口",
        "settings_general_apply_port": "应用并重启",
        "settings_general_open_dir": "打开文件夹",
        "settings_port_invalid_title": "端口无效",
        "settings_port_invalid_body": "请输入 1 到 65535 之间的有效端口号。2",
        "settings_port_saved_only": "端口已保存。启动网络后会使用新的端口。",
        "settings_language_title": "语言",
        "settings_language_body": "使用下面的开关切换应用显示语言。",
        "settings_about_title": "关于",
        "settings_about_body": "这个页面可以放版本信息、更新说明和诊断入口。",
        "settings_language_english": "English",
        "settings_language_zh": "简体中文",
        "error_gateway_title": "网关错误",
        "error_dashboard_title": "控制台错误",
        "error_summary_title": "摘要",
        "error_no_output": "未捕获到错误输出。",
        "error_gateway_reported": "网关报告了错误。",
        "message_missing_openclaw_status": "此电脑尚未安装 OpenClaw",
        "message_starting_gateway": "正在启动网关...",
        "message_restarting_gateway": "正在重启网关...",
        "message_stopping_gateway": "正在停止网关...",
        "message_dashboard_loading": "控制台加载中...",
        "message_dashboard_loaded": "控制台加载成功",
        "message_dashboard_failed": "控制台加载失败",
        "message_gateway_error": "网关错误",
        "message_gateway_stopped": "网关已停止",
        "message_dashboard_ready": "控制台已就绪",
        "warning_gateway_not_running_title": "网关未运行",
        "warning_gateway_not_running_body": "请先启动 OpenClaw 网关。",
        "status_stopped": "已停止",
        "status_starting": "启动中...",
        "status_loading": "加载中...",
        "status_running": "运行中",
        "status_stopping": "停止中...",
        "status_error": "错误",
        "status_unknown": "未知"
    },
}


def tr_text(language: str, key: str) -> str:
    bundle = TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE])
    return bundle.get(key, TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key))
