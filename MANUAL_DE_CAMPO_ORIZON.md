# Manual de campo — Orizon

Este manual usa a estrutura recuperada que já foi testada:

```text
C:\Recuperacao\detecta (recente)_restaurado_20260826_030000
├── config\camera_1.json
├── venv\
└── orizon_teste_real\teste_real_orizon\
    ├── best.pt
    ├── webhook_client.py
    ├── zone_loader.py
    └── yolo11objectdetection-track.py
```

> Regra principal: execute o Python que está dentro de
> `orizon_teste_real\teste_real_orizon`. O JSON fica fora dessa pasta, em
> `config`.

## 1. Antes de sair

- Leve uma cópia da pasta recuperada sem alterações.
- Não apague os arquivos duplicados no dia do teste.
- Não envie senhas ou URLs RTSP com credenciais ao GitHub.
- Confirme com Jhonatan o domínio atual do backend.
- Confirme se o computador poderá entrar na rede das câmeras da fábrica.

## 2. Abrir o PowerShell na pasta correta

Execute:

```powershell
Set-Location "C:\Recuperacao\detecta (recente)_restaurado_20260826_030000"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\venv\Scripts\Activate.ps1
Set-Location ".\orizon_teste_real\teste_real_orizon"
```

O terminal deve terminar assim:

```text
(venv) PS C:\Recuperacao\detecta (recente)_restaurado_20260826_030000\orizon_teste_real\teste_real_orizon>
```

Não execute outro `cd` depois disso.

## 3. Verificação obrigatória

```powershell
Test-Path .\yolo11objectdetection-track.py
Test-Path .\webhook_client.py
Test-Path .\best.pt
Test-Path ..\..\config\camera_1.json
python -c "import sys; print('PYTHON:', sys.executable)"
python -c "import webhook_client; print('ARQUIVO:', webhook_client.__file__); print('URL:', webhook_client.BASE_URL)"
```

Os quatro `Test-Path` precisam mostrar `True`. O caminho de
`webhook_client.py` precisa terminar em:

```text
orizon_teste_real\teste_real_orizon\webhook_client.py
```

Se aparecer outro caminho, você está executando a cópia errada.

## 4. Trocar o endereço de destino

Abra somente o cliente que está na pasta de execução:

```powershell
code -r .\webhook_client.py
```

Localize `BASE_URL`.

Para o backend do Jhonatan, informe somente o domínio, sem acrescentar endpoint:

```python
BASE_URL = "https://DOMINIO-ATUAL-DO-BACKEND"
```

O programa acrescenta sozinho:

```text
/api/ocorrencia
/api/alerta
/api/zona/{id}
```

Para testar no Webhook.site, use a URL completa do token:

```python
BASE_URL = "https://webhook.site/TOKEN-ATUAL"
```

Salve e confirme antes de executar:

```powershell
python -c "import webhook_client; print(webhook_client.__file__); print(webhook_client.BASE_URL)"
```

## 5. Conferir a configuração da câmera

```powershell
python -c "import json; p=r'..\..\config\camera_1.json'; c=json.load(open(p,encoding='utf-8-sig')); print('FONTE:',c.get('camera_source')); print('ZONAS:',list(c.get('zonas',{}))); print('ESP32:',c.get('esp32_habilitado'),c.get('esp32_port'))"
```

Fontes comuns:

```json
"camera_source": 0
```

é a webcam principal. `1` costuma ser Camo ou uma segunda câmera. Uma câmera de
rede usa uma URL RTSP, mas não coloque credenciais em um arquivo que irá para o
GitHub.

## 6. Executar o sistema recuperado

```powershell
python .\yolo11objectdetection-track.py ..\..\config\camera_1.json
```

O funcionamento básico está confirmado quando aparecem:

```text
Iniciando monitoramento: Oficina A
Câmera resolução detectada: 640x480
MAQUINA_1 pontos escalados: ...
MAQUINA_2 pontos escalados: ...
```

Depois devem aparecer as detecções do YOLO. Quando o estado de uma zona mudar,
o terminal deve mostrar algo como:

```text
[webhook] POST /api/ocorrencia -> status 200
```

Pressione `q` na janela do vídeo para encerrar. Se necessário, volte ao terminal
e pressione `Ctrl+C`.

## 7. Testar o backend antes de abrir a câmera

### Webhook.site

```powershell
python -c "import webhook_client,requests; r=requests.post(webhook_client.BASE_URL,json={'teste':'orizon'}); print(r.url); print(r.status_code); print(r.text[:200])"
```

O esperado é `200` e a requisição deve aparecer na página do Webhook.site.

### Cadastro de câmeras do backend

No pacote multicâmeras preparado:

```powershell
$env:ORIZON_BACKEND_URL = "https://DOMINIO-ATUAL-DO-BACKEND"
python .\executar_multiplas_cameras.py --listar-api
```

Esse comando apenas consulta `GET /api/cameras`; ele não abre os streams.

## 8. Testar a rede das câmeras da fábrica

O computador precisa estar na rede da fábrica ou em uma VPN autorizada.

Para cada IP fornecido, teste a porta RTSP:

```powershell
Test-NetConnection IP_DA_CAMERA -Port 554
```

O resultado necessário é:

```text
TcpTestSucceeded : True
```

Isso confirma acesso à porta, não confirma usuário, senha nem caminho do vídeo.

## 9. ESP32

Feche o Monitor Serial do Arduino IDE antes de executar o Python. Veja as portas:

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
```

Se o ESP32 estiver em outra porta, altere `esp32_port` no arquivo:

```text
..\..\config\camera_1.json
```

Se o teste não usar o ESP32:

```json
"esp32_habilitado": false
```

Uma falha na `COM6` afeta o LED, mas não significa que a câmera ou o YOLO
falharam.

## 10. Erros mais comuns

### `can't open file`

Você está na pasta errada ou executou a cópia externa do Python. Repita as
seções 2 e 3.

### `SyntaxError` na primeira linha

Uma linha de comando foi colada dentro do arquivo Python. Não use essa cópia.
Execute o arquivo interno confirmado na seção 3.

### `No module named ...`

Confirme se o terminal mostra `(venv)` e se `sys.executable` aponta para o
`venv` recuperado. Não instale ou remova pacotes durante a visita sem antes
guardar uma cópia do ambiente funcionando.

### `POST ... status 404` no Webhook.site

O token expirou ou a URL não é mais válida. Gere outro endereço e altere
`BASE_URL` no `webhook_client.py` interno.

### Falha em `/api/zona/{id}` e `usando fallback local`

Durante teste com Webhook.site isso é esperado: ele não implementa a API de
zonas. O programa continua usando os polígonos do JSON local.

### Caracteres como `CÃ¢mera` ou `ocorrÃªncia`

É um problema de exibição/codificação do terminal. Não significa falha na
detecção nem no envio.

### A câmera abre, mas não envia ocorrências

O webhook envia somente quando o status da zona muda. Entre ou saia da zona,
coloque ou retire o EPI e observe o terminal. Confirme também o caminho e a URL
com o último comando da seção 3.

## 11. Ordem curta para o dia do teste

1. Entrar na rede da fábrica.
2. Confirmar o domínio do backend.
3. Ativar o `venv` recuperado.
4. Entrar em `orizon_teste_real\teste_real_orizon`.
5. Executar os quatro `Test-Path`.
6. Confirmar `webhook_client.__file__` e `BASE_URL`.
7. Testar `GET /api/cameras` ou um POST de teste.
8. Confirmar porta `554` das câmeras.
9. Executar o programa.
10. Procurar `status 200` no terminal e confirmar o recebimento com Jhonatan.

## Comando principal

```powershell
python .\yolo11objectdetection-track.py ..\..\config\camera_1.json
```
