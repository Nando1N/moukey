; installer for windows, built by github actions with inno setup:
;   iscc /DAppVersion=0.5.0 /DExeDir=..\dist installer\moukey.iss
; per user, no admin prompt, like discord or vs code. it lands in
; %LOCALAPPDATA%\Programs\MouKey, so the in-app updater can replace it later

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef ExeDir
  #define ExeDir "..\dist"
#endif

[Setup]
; never change this id, it's how windows knows a new version is the same app
AppId={{CDE3B5F3-0832-4094-88CA-9C9D7E11FF0C}
AppName=MouKey
AppVersion={#AppVersion}
AppVerName=MouKey {#AppVersion}
AppPublisher=Nando
AppPublisherURL=https://github.com/Nando1N/moukey
AppSupportURL=https://github.com/Nando1N/moukey/issues
AppUpdatesURL=https://github.com/Nando1N/moukey/releases/latest
DefaultDirName={autopf}\MouKey
DefaultGroupName=MouKey
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir={#ExeDir}
OutputBaseFilename=MouKey-Setup
SetupIconFile=..\assets\icone\moukey.ico
UninstallDisplayIcon={app}\MouKey.exe
UninstallDisplayName=MouKey
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
; closes a running MouKey before replacing it (updates and uninstall)
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
pt.DesktopIcon=Criar atalho na área de trabalho
en.DesktopIcon=Create a desktop shortcut
pt.StartWithWindows=Abrir o MouKey quando o Windows iniciar (os computadores se conectam sozinhos)
en.StartWithWindows=Open MouKey when Windows starts (computers connect on their own)
pt.OpenNow=Abrir o MouKey agora
en.OpenNow=Open MouKey now

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"
Name: "startup"; Description: "{cm:StartWithWindows}"

[Files]
Source: "{#ExeDir}\MouKey.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; the start menu entry is what makes it show up when you search "moukey" in windows
Name: "{autoprograms}\MouKey"; Filename: "{app}\MouKey.exe"; Comment: "Um mouse e um teclado para os seus computadores"
Name: "{autodesktop}\MouKey"; Filename: "{app}\MouKey.exe"; Tasks: desktopicon

[Registry]
; the same value the app's own "Iniciar com o Windows" switch uses, so both agree
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MouKey"; ValueData: """{app}\MouKey.exe"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\MouKey.exe"; Description: "{cm:OpenNow}"; Flags: nowait postinstall skipifsilent
; after a silent update (the in-app button) the app comes back on its own
Filename: "{app}\MouKey.exe"; Flags: nowait; Check: WizardSilent

[UninstallDelete]
; the switch inside the app may have written this even if the task wasn't picked
Type: files; Name: "{app}\MouKey.antigo.exe"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'MouKey');
end;
