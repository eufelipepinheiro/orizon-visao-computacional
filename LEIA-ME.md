# Arquivos atualizados — apresentação Orizon

## O que substituir

Copie estes arquivos para a raiz do projeto:

- `yolo11objectdetection-track.py`
- `webhook_client.py`
- `zone_loader.py`
- `esp32_led.py`
- `testar_integracao_orizon.py`

Copie `config/camera_1.json` para a pasta `config`.

O arquivo `best.pt`, as fotos, os demais módulos e o ambiente virtual não precisam ser substituídos.

## Antes do teste

1. Confirme que o Jhonatan ligou o backend e o túnel ngrok.
2. Feche o Monitor Serial da Arduino IDE.
3. Instale a comunicação serial:

```powershell
.\.venv\Scripts\python.exe -m pip install pyserial requests
```

4. Abra no navegador:

- https://unideographical-nonnocturnally-jarred.ngrok-free.dev/api/zona
- https://unideographical-nonnocturnally-jarred.ngrok-free.dev/funcionario

O config está pré-preenchido com `id_zona: 1` e `funcionario_padrao_id: 1`, com base no banco incluído no backend. Se os IDs mostrados pelo servidor forem diferentes, altere-os em `config/camera_1.json`.

## Teste do backend

Este comando cria uma ocorrência e um alerta reais:

```powershell
.\.venv\Scripts\python.exe testar_integracao_orizon.py --zona-id 1 --funcionario-id 1 --status BLOQUEADA --enviar
```

O teste correto termina com:

```text
[SUCESSO] Encadeamento ocorrência -> alerta validado.
```

## Executar o sistema

```powershell
.\.venv\Scripts\python.exe yolo11objectdetection-track.py config\camera_1.json
```

Comportamento:

- sem humano real: LED vermelho piscando;
- EPI faltando ou postura inadequada: LED vermelho piscando;
- todas as condições aprovadas: LED verde aceso;
- mudança de status: ocorrência enviada ao backend;
- estado BLOQUEADA: ocorrência seguida de alerta.

Se aparecer erro de acesso à COM6, feche o Monitor Serial e qualquer outro programa usando a porta.

