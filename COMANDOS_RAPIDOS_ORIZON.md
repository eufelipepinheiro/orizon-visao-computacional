# Orizon — comandos rápidos

## 1. Abrir o projeto e ativar o ambiente

Cole este bloco no PowerShell:

```powershell
Set-Location "C:\Recuperacao\detecta (recente)_restaurado_20260826_030000"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& ".\venv\Scripts\Activate.ps1"
Set-Location ".\orizon_teste_real\teste_real_orizon"
```

## 2. Confirmar que está tudo no lugar certo

```powershell
Get-Location
Test-Path .\yolo11objectdetection-track.py
Test-Path .\webhook_client.py
Test-Path .\best.pt
Test-Path ..\..\config\camera_1.json
python -c "import sys,webhook_client; print('PYTHON:',sys.executable); print('WEBHOOK:',webhook_client.__file__); print('URL:',webhook_client.BASE_URL)"
```

Os quatro `Test-Path` precisam retornar `True`.

## 3. Trocar a URL do backend ou Webhook.site

Troque somente o conteúdo de `$NovaUrl` e cole o bloco inteiro:

```powershell
$NovaUrl = "https://COLE-A-URL-AQUI"
$Arquivo = (Resolve-Path .\webhook_client.py).Path
$Conteudo = [System.IO.File]::ReadAllText($Arquivo)
$Conteudo = [regex]::Replace($Conteudo, '(?m)^BASE_URL\s*=\s*["''][^"'']+["'']', "BASE_URL = `"$NovaUrl`"")
[System.IO.File]::WriteAllText($Arquivo, $Conteudo, [System.Text.UTF8Encoding]::new($false))
python -c "import webhook_client; print(webhook_client.__file__); print(webhook_client.BASE_URL)"
```

Para o backend do Jhonatan, use somente o domínio:

```text
https://DOMINIO-DO-BACKEND
```

Não acrescente `/api/ocorrencia`, `/api/alerta` ou `/api/cameras` em
`BASE_URL`.

## 4. Executar o programa

```powershell
python .\yolo11objectdetection-track.py ..\..\config\camera_1.json
```

Para encerrar, pressione `q` na janela do vídeo ou `Ctrl+C` no terminal.

## 5. Conferir qual câmera está configurada

```powershell
python -c "import json; c=json.load(open(r'..\..\config\camera_1.json',encoding='utf-8-sig')); print('CAMERA:',c.get('camera_source')); print('ZONAS:',list(c.get('zonas',{}))); print('ESP32:',c.get('esp32_habilitado'),c.get('esp32_port'))"
```

## 6. Testar um endereço do Webhook.site

```powershell
python -c "import webhook_client,requests; r=requests.post(webhook_client.BASE_URL,json={'teste':'orizon'}); print('STATUS:',r.status_code); print('URL:',r.url)"
```

O resultado esperado é `STATUS: 200`.

## 7. Consultar as câmeras cadastradas no backend

Execute isto na pasta do pacote multicâmeras, onde está
`executar_multiplas_cameras.py`:

```powershell
$env:ORIZON_BACKEND_URL = "https://DOMINIO-DO-BACKEND"
python .\executar_multiplas_cameras.py --listar-api
```

## 8. Testar acesso à câmera de rede

```powershell
Test-NetConnection IP_DA_CAMERA -Port 554
```

Precisa aparecer:

```text
TcpTestSucceeded : True
```

## 9. Ver as portas do ESP32

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
```

Feche o Monitor Serial do Arduino IDE antes de executar o Python.

## Resultado que indica sucesso

```text
Câmera resolução detectada: ...
MAQUINA_1 pontos escalados: ...
[webhook] POST /api/ocorrencia -> status 200
```
