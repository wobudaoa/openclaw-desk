; =========================================================
; ClawDesk Installer Script
; Supports: English / 简体中文
; Project: https://github.com/wobudaoa/openclaw-desk
; =========================================================

#define MyAppName "ClawDesk"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "wobudaoa"
#define MyAppURL "https://github.com/wobudaoa/openclaw-desk"
#define MyAppExeName "ClawDesk.exe"
#define MyAppIcon "assets\emoji.ico"
#define MySourceDir "dist\ClawDesk"

[Setup]
AppId={{C7E1A8D2-6A7E-4F2A-9E31-CLAWDESK}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

OutputDir=installer-dist
OutputBaseFilename=ClawDesk-Setup-{#MyAppVersion}

Compression=lzma
SolidCompression=yes
WizardStyle=modern

PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}

DisableProgramGroupPage=yes
LicenseFile=LICENSE

; 这个选项可让安装界面更现代
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[CustomMessages]
english.AppDescription=ClawDesk is a lightweight desktop control panel for OpenClaw Gateway.
chinesesimp.AppDescription=ClawDesk 是一个面向 OpenClaw Gateway 的轻量级桌面控制面板。

english.CreateDesktopIcon=Create a desktop shortcut
chinesesimp.CreateDesktopIcon=创建桌面快捷方式

english.AdditionalTasks=Additional tasks
chinesesimp.AdditionalTasks=附加任务

english.LaunchProgram=Launch ClawDesk
chinesesimp.LaunchProgram=启动 ClawDesk

english.UninstallProgram=Uninstall ClawDesk
chinesesimp.UninstallProgram=卸载 ClawDesk

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalTasks}"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;