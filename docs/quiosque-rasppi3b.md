# Quiosque Raspberry Pi 3B

Interface local para **Raspberry Pi 3B + Touch Display 2 + microfone**, enviando
programas para o **Zumo 2040 via HC-06 POLOLU**. A branch é `v1-rasppi3b`.
O display se conecta à Raspberry Pi pelo DSI. O rádio utilizado é o Bluetooth
integrado da Raspi, com Bluetooth clássico/SPP, não BLE.

A tela tem microfone, **Executar, Repetir, Modificar, Novo código**, além de
Wi-Fi e Bluetooth. Durante a API, o foguete anima e os controles de cintos e
manivela respondem ao toque. Não há porcentagem fictícia: os controles da
brincadeira não alteram nem aceleram o processamento da IA.

## Instalação e uso

Depois que a branch tiver sido publicada pelo mantenedor:

```bash
git clone --branch v1-rasppi3b https://github.com/insper-embarcados/Speach2Pico.git
cd Speach2Pico
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.kiosk.example .env
# Preencha a chave e confirme os provedores/modelos em .env.
python kiosk.py
```

O frontend já está em `kiosk_app/static`, incluindo todos os ícones, desenhos,
CSS e JavaScript. **Não precisa de Node, npm, CDN, fontes externas ou build na
Raspberry Pi**. O aplicativo abre Chromium em tela cheia e atende somente em
`http://127.0.0.1:8765`. Para encerrar pelo teclado: Alt+F4 fecha a janela;
Ctrl+C no terminal encerra também o serviço. Fechar a tela não para um programa
já enviado ao robô.

Use Raspberry Pi OS **Desktop de 64 bits**, Python 3.10+ e uma sessão gráfica.
A versão Lite não fornece a sessão gráfica/Chromium. No primeiro preparo da
Raspi, se faltarem componentes do sistema:

```bash
sudo apt update
sudo apt install python3-venv libportaudio2 bluez network-manager chromium
```

Esses são componentes do sistema; `pip install` não instala drivers, BlueZ,
Chromium ou NetworkManager. Em versões da distribuição que usam outro nome
para Chromium, instale `chromium-browser`. A conta precisa de acesso normal
a áudio/Bluetooth e permissão do NetworkManager para alterar conexões. Rode
a aplicação como usuário da sessão gráfica, sem `sudo`.

`requirements.txt` desta branch contém as dependências do quiosque. A lista
original foi preservada em `requirements-legacy.txt` para os programas antigos
em `host/`; esses programas continuam disponíveis, mas seu fluxo segue separado.

### APIs

A aplicação lê `.env` na raiz. São preservados os nomes usados pelo Speach2Pico:
`LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, `STT_PROVIDER`, `STT_MODEL`,
`STT_FUNCTION_ID`, `STT_LANGUAGE` e `NVIDIA_RIVA_SERVER`.

- LLM: OpenAI, Anthropic ou NVIDIA com endpoint compatível com OpenAI.
- Voz: OpenAI, NVIDIA/Riva ou Google Cloud Speech-to-Text.
- Para voz NVIDIA: `python -m pip install -r requirements-nvidia.txt`.
- Para Google: `python -m pip install -r requirements-google.txt`,
  `STT_PROVIDER=google` e credenciais do Google Cloud configuradas.

Escolha um modelo habilitado na sua conta. A chave fica no backend, nunca no
JavaScript. O áudio é enviado ao provedor de voz selecionado, e a transcrição
vai ao LLM. Não há Whisper local na Pi 3B. O microfone é o da própria Raspi;
o navegador não pede acesso a microfone. A captura usa o dispositivo padrão,
ou `KIOSK_AUDIO_DEVICE` com índice/nome aceito por sounddevice. A gravação
termina automaticamente em 30 segundos e seu WAV temporário é removido após
a transcrição, inclusive quando a API falha.

## Bluetooth: reaproveitando a montagem validada

```text
Raspberry Pi 3B (Bluetooth integrado)
       ↓ Bluetooth Classic / RFCOMM, canal 1
HC-06 POLOLU — 00:23:04:00:33:75
       ↓ UART0, 115200 baud, TX GP28 / RX GP29
Pololu Zumo 2040 — examples/bluetooth_uart/receiver.py
```

Consulte o [guia Bluetooth existente](../examples/bluetooth_uart/README.md)
para fiação, alimentação e carregamento do receptor. Use **`receiver.py`**;
`control_receiver.py` é outro protocolo e não recebe arquivos MicroPython.
Nenhum firmware é instalado ou sobrescrito automaticamente pelo quiosque.

É necessário parear o HC-06 **uma vez em cada Raspberry Pi**, mesmo se ele já
foi pareado no laptop. No `bluetoothctl` da Raspi:

```text
power on
agent KeyboardOnly
default-agent
scan bredr
# Depois que POLOLU aparecer:
scan off
pair 00:23:04:00:33:75
trust 00:23:04:00:33:75
quit
```

Informe o PIN da sua unidade quando solicitado. O quiosque abre diretamente
um socket RFCOMM; **não exige `sudo rfcomm bind` nem `/dev/rfcomm0`**. Feche
outras aplicações conectadas ao mesmo módulo. `BLUETOOTH_ADDRESS` e
`BLUETOOTH_CHANNEL` permitem usar outro endereço/canal.

O serviço verifica a conexão em ciclos de 1 segundo. Quando desconectado,
continua tentando sem limite de tentativas. Uma tentativa de conexão do Linux
pode levar até 3 segundos e uma confirmação até 2; não são abertas conexões
concorrentes para simular uma frequência impossível. O estado conectado só
aparece após `PING` → `PONG`, confirmando rádio, UART e receptor. O ícone é
estado de conexão, não uma medição de RSSI/intensidade do rádio.

### Execução e confirmação

1. O microfone ou **Novo código** inicia uma gravação; toque novamente no
   microfone para terminar. A transcrição inicia a geração automaticamente.
2. O código é mantido no backend. Nada é enviado ao robô durante a geração.
3. **Executar** envia exatamente esse código pelo protocolo S2P1, com SHA-256.
4. O receptor confirma `READY`, `RUNNING` e `DONE`. Somente `DONE` habilita
   **Repetir**, que reutiliza o programa sem outra chamada de IA.
5. **Modificar** grava uma nova instrução e envia o código anterior como
   contexto. O novo resultado também exige clique em **Executar**.

A confirmação usa um identificador da missão; requisições antigas e cliques
simultâneos não executam versões diferentes ou duplicam o envio. Reconectar
**nunca reexecuta automaticamente** um programa. Se a conexão cair depois do
início do envio e a confirmação se perder, a tela marca execução incerta.
Confira o robô e reconheça o aviso no painel Bluetooth antes de novo envio.

**Limitação do receptor existente:** enquanto `exec()` está rodando, ele não
responde a `PING`, não recebe `STOP` e não possui watchdog de execução. A UI
mostra o estado em missão e pausa heartbeats durante esse período; encerrar o
host, perder Bluetooth ou expirar os 120 s de espera **não interrompe o robô**.
Para interromper fisicamente, desligue o robô. Uma transferência incompleta
pode exigir reiniciar o receptor, conforme o guia existente.

O prompt pede programas finitos de até 60 s, velocidades até 1500, motores em
`finally` e no máximo 4096 bytes; o clique na tela autoriza o começo, sem pedir
botão A adicional. A checagem AST rejeita módulos fora do escopo, operações
óbvias de execução/arquivos e `while True`. **Esses filtros não são uma sandbox
nem provam duração ou segurança do programa gerado**. O programa roda com os
privilégios do MicroPython, como no receptor já existente.

## Wi-Fi

Toque no ícone de Wi-Fi para listar redes, selecionar, digitar senha com o
teclado na tela e conectar/reconectar. Senha vazia permite usar credencial já
salva ou rede aberta. O painel usa `nmcli`/NetworkManager, sem shell e sem senha
nos argumentos do processo. A senha não é devolvida pela API nem gravada pelo
quiosque; o NetworkManager pode salvar a credencial no perfil da rede.

Redes empresariais/802.1X ou portais cativos exigem preparação pelas ferramentas
do sistema; o formulário é para redes pessoais e perfis já configurados.
Conectar ao Wi-Fi não garante acesso às APIs. A API local distingue a indicação
de conectividade do NetworkManager do estado de associação à rede.

## Iniciar ao alimentar a Raspberry

Uma vez, com a venv ativa:

```bash
python kiosk.py --install-autostart
```

Depois habilite o **login automático na sessão gráfica** nas configurações do
Raspberry Pi OS. A entrada XDG inicia o quiosque nessa sessão e abre o Chromium.
O receptor também precisa estar rodando no Pololu após cada alimentação;
preparar a inicialização dele é separado e deve preservar o menu/main.py
existente. Para remover o autostart, exclua
`~/.config/autostart/speech2pico.desktop`.

## Demonstração e desenvolvimento

```bash
python kiosk.py --demo              # sem APIs, rádio, microfone ou mudança de Wi-Fi
python kiosk.py --demo --no-browser # abre manualmente http://127.0.0.1:8765
```

No modo DEMO, o botão de voz simula a preparação de um programa fixo de LED,
e o clique Executar simula uma execução. O selo DEMO e o painel Bluetooth
identificam a simulação. O modo real é o padrão, sem `--demo`.

Para alterar o frontend, somente na máquina de desenvolvimento:

```bash
cd web
npm ci
npm run build
```

O build atualiza `kiosk_app/static`; **inclua esses arquivos no commit** para
que um clone na Raspberry funcione sem Node. O manifesto e lockfile do frontend
ficam em `web/`.

Testes (transporte e APIs simulados, não movimentam hardware):

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s kiosk_tests -v
# Com o servidor --demo --no-browser em outro terminal:
cd web
npx playwright install chromium --only-shell
npm test
```

O teste web percorre geração, brincadeira, clique de execução, modificação,
Wi-Fi e teclado, verificando ausência de rolagem em 720×1280, 1280×720 e
360×800. Testes locais não certificam o desempenho físico na Pi 3B, o display,
pareamento, microfone, permissões do NetworkManager ou acesso real às APIs.
