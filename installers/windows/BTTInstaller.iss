#define MyAppName "BTT Local"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "zpp0103"
#define MyAppURL "https://github.com/zpp0103/BTT"
#define MyAppExeName "install-btt.bat"

[Setup]
AppId={{7C44E7D1-D90D-4A59-87BD-011A49956B9E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\BTT
DefaultGroupName=BTT
DisableDirPage=no
OutputDir=dist
OutputBaseFilename=btt-windows-installer
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".git\*,.venv\*,dist\*,__pycache__\*,*.pyc,*.pyo,*.sqlite*,logfile.txt,user_data\*"

[Icons]
Name: "{group}\BTT One-Click Installer"; Filename: "{app}\installers\windows\install-btt.bat"
Name: "{group}\README"; Filename: "{app}\README.md"

[Run]
Filename: "{cmd}"; Parameters: "/c ""{app}\installers\windows\install-btt.bat"""; Description: "Run BTT one-click installer now"; Flags: postinstall shellexec skipifsilent
