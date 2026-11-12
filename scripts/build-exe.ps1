# gera dist\MouKey.exe, um arquivo so, que abre a janela sem terminal
# uso: .\scripts\build-exe.ps1   (precisa de: pip install -e . pyinstaller)

python -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --name MouKey `
    --icon "$PWD\assets\icone\moukey.ico" `
    --paths . `
    --specpath build `
    --add-data "$PWD\moukey\ui;moukey\ui" `
    --hidden-import pynput.keyboard._win32 `
    --hidden-import pynput.mouse._win32 `
    --hidden-import pystray._win32 `
    --collect-submodules zeroconf `
    --collect-all webview `
    moukey/webapp.py
