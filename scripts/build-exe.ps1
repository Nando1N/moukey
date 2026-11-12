# gera dist\MouKey.exe, um arquivo so, que abre a janela sem terminal
# uso: .\scripts\build-exe.ps1   (precisa de: pip install -e . pyinstaller)

python -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --name MouKey `
    --paths . `
    --hidden-import pynput.keyboard._win32 `
    --hidden-import pynput.mouse._win32 `
    --collect-submodules zeroconf `
    moukey/gui.py
