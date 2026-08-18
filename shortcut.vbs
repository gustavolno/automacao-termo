Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "C:\Users\Gustavo\Desktop\Gerador Boletos.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "C:\Users\Gustavo\Documents\automacoes-aldrigues\venv\Scripts\pythonw.exe"
oLink.Arguments = "interface.py"
oLink.WorkingDirectory = "C:\Users\Gustavo\Documents\automacoes-aldrigues"
oLink.Save()
