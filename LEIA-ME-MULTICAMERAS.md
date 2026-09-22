# Orizon - preparação para múltiplas câmeras

Este pacote é uma **cópia de adaptação**. Não substitua a versão recuperada antes
de testar. Copie estes arquivos para uma duplicata da pasta que já contém
`best.pt`, `pose_check.py`, `face_id.py` e `esp32_led.py`.

## O que foi preparado

- Webcam e Camo por índice (`camera_source: 0`, `1`, etc.).
- RTSP diretamente no JSON ou, preferencialmente, por variável de ambiente.
- Reconexão automática quando um stream cai.
- Um JSON independente por câmera, com zonas e EPIs próprios.
- Inicialização simultânea de várias configurações.
- Consulta tolerante do cadastro `GET /api/cameras`.
- `funcionario.id_funcionario` restaurado nas ocorrências, usando o rosto
  reconhecido ou `funcionario_padrao_id`.
- URL do backend configurável por câmera ou variável de ambiente.
- Zonas locais usadas diretamente durante testes com Webhook.site.
- Identificação da origem no cabeçalho HTTP `X-Camera-Id`.
- Campo opcional `camera_id` no JSON do payload. Mantenha
  `incluir_camera_payload: false` até o backend confirmar que aceita esse campo.

## Teste com webcam ou Camo

Edite `config/camera_usb.json`, coloque a URL atual do Webhook.site em
`backend_url` e selecione o índice da câmera:

```json
"camera_source": 0
```

Execute na pasta que contém `best.pt`:

```powershell
python .\yolo11objectdetection-track.py .\config\camera_usb.json
```

## Teste RTSP sem gravar senha no projeto

Copie `config/camera_rtsp.example.json` para um arquivo próprio, mantendo
`camera_source_env`. No PowerShell, defina a URL apenas para o terminal atual:

```powershell
$env:CAMERA_FRESA_1_RTSP = "rtsp://USUARIO:SENHA@IP:554/CAMINHO"
$env:ORIZON_BACKEND_URL = "https://DOMINIO-ATUAL-DO-BACKEND"
python .\yolo11objectdetection-track.py .\config\camera_rtsp.example.json
```

O terminal não imprime usuário ou senha da URL. Ao fechar o PowerShell, essas
variáveis deixam de existir.

Os endereços privados das câmeras da fábrica só funcionarão dentro da rede da
Metaindústria ou por uma VPN autorizada.

## Duas câmeras simultâneas

Cada processo carrega uma cópia do modelo e consome CPU/GPU própria. Comece com
duas câmeras e monitore o desempenho:

```powershell
python .\executar_multiplas_cameras.py `
  .\config\camera_rtsp.example.json `
  .\config\camera_rtsp_2.example.json
```

Use `Ctrl+C` para encerrar o gerenciador.

## Câmeras cadastradas pelo Jhonatan

O adaptador aceita uma lista JSON direta e também coleções dentro de chaves
comuns como `cameras`, `data`, `content`, `items` e `_embedded`. Ele reconhece
automaticamente variações usuais de `id`, `nome`, `descricao` e `acesso`.

Primeiro apenas consulte e confira o cadastro, sem abrir os vídeos:

```powershell
$env:ORIZON_BACKEND_URL = "https://DOMINIO-DO-BACKEND"
python .\executar_multiplas_cameras.py --listar-api
```

Não é necessário comentar ou descomentar campos. Quando o JSON real chegar,
se houver alguma diferença, a correção ficará concentrada em `camera_api.py`.

Para executar, a API também precisa informar as zonas de cada câmera. Enquanto
essa relação não existir, o modo seguro recusa a inicialização. Somente para um
teste controlado é possível reutilizar as zonas do template:

```powershell
python .\executar_multiplas_cameras.py --executar-api `
  --template .\config\camera_usb.json `
  --usar-zonas-template
```

Não use `--usar-zonas-template` na fábrica: os polígonos mudam conforme o
enquadramento de cada câmera.

## Campos de configuração importantes

| Campo | Uso |
|---|---|
| `camera_id` | Nome técnico único da origem |
| `camera_source` | Índice da webcam/Camo ou URL não secreta |
| `camera_source_env` | Nome da variável que contém a URL RTSP |
| `backend_url` | URL base do backend/Webhook.site |
| `backend_url_env` | Variável que contém a URL do backend |
| `carregar_zonas_backend` | `false` para zonas locais; `true` para API |
| `reconnect_seconds` | Intervalo entre tentativas de reconexão |
| `reconnect_attempts` | `0` tenta indefinidamente |

## Segurança e GitHub

Não envie ao GitHub o PDF de acesso, URLs com senha, rostos cadastrados,
ambientes virtuais, vídeos ou modelos. O `.gitignore` incluído cobre os itens
mais comuns. O arquivo `configurar_fontes.example.ps1` contém apenas valores
fictícios e pode servir como referência.
