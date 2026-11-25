> **Branch `v1-rasppi3b`: quiosque Raspberry Pi 3B + Touch Display 2.**
> Voz → código → clique em Executar → Bluetooth Classic/HC-06 → Pololu.

## Quiosque web

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.kiosk.example .env   # preencha as chaves; preserve seu .env se já existir
python kiosk.py
```

A interface já vem compilada: não precisa de Node na Raspberry. Tem microfone,
Executar, Repetir, Modificar, Novo código, animações de foguete/cintos/manivela,
Wi-Fi com teclado na tela e reconexão Bluetooth automática. `python kiosk.py
--demo` abre uma demonstração sem hardware nem APIs. Para iniciar na sessão
gráfica ao ligar: `python kiosk.py --install-autostart` e login automático no SO.

**Primeira preparação:** Raspberry Pi OS Desktop, Chromium, PortAudio, BlueZ,
NetworkManager, APIs configuradas e HC-06 pareado com esta Raspi. Use o
`receiver.py` do exemplo Bluetooth no Pololu; o receptor atual não tem parada
remota durante execução. O guia abaixo registra os comandos e limites.

[Instalação, pareamento, APIs e inicialização automática](docs/quiosque-rasppi3b.md).
As dependências originais dos scripts antigos estão em `requirements-legacy.txt`.

---

# Speach2Pi

Controle um robô Pololu Zumo 2040 falando. Você segura a barra de espaço, diz o que
quer — *"anda para frente por dois segundos e depois gira para a direita"* — solta a
tecla, e pouco depois o robô já está se comportando assim.

Projeto de horas complementares (Insper).

Também é possível enviar arquivos MicroPython fixos pelo **Bluetooth do laptop
→ HC-06 → UART do Zumo 2040**. Esse fluxo foi testado com sucesso, incluindo
movimento por 5 segundos, e está descrito abaixo. O fluxo de voz de
`host/main.py` continua usando USB; a integração da voz com Bluetooth ainda
não está implementada.

## Como funciona

```
┌──────────────────────── computador (host) ────────────────────────┐
│                                                                   │
│  [ESPAÇO] ──▶ grava microfone ──▶ API speech-to-text ──▶ texto    │
│                                                          │        │
│                              prompt + instrução ─────────┘        │
│                                        │                          │
│                                        ▼                          │
│                       LLM (Claude / GPT) ──▶ código MicroPython   │
│                                        │                          │
└────────────────────────────────────────┼──────────────────────────┘
                                         │ USB (mpremote)
                                         ▼
          ┌──────────── Pololu Zumo 2040 (RP2040) ────────────┐
          │  executa o código ──▶ motores, LEDs, buzzer,       │
          │                       display, botões e sensores   │
          └────────────────────────────────────────────────────┘
```

| Etapa | Arquivo |
|---|---|
| Captura de áudio pela barra de espaço | [host/recorder.py](host/recorder.py), [host/main.py](host/main.py) |
| Áudio → texto | [host/transcribe.py](host/transcribe.py) |
| Texto → código MicroPython | [host/codegen.py](host/codegen.py), [prompts/system_prompt.md](prompts/system_prompt.md) |
| Envio e execução no Zumo | [host/deploy.py](host/deploy.py) |

O código roda direto na memória do robô, sem alterar os arquivos dele: o botão de
reset volta para o menu original da Pololu.

## Instalação (no computador)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows;  no Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env        # depois preencha as chaves de API
```

## Robô Pololu Zumo 2040

Ver [zumo/setup_zumo.md](zumo/setup_zumo.md) — conexão, energia, hardware disponível
e teste do hardware.

## Uso

```bash
python host/main.py
```

1. Segure **ESPAÇO** e fale a instrução
2. Solte a tecla
3. O código gerado aparece no terminal e já começa a rodar no Zumo
4. Se o programa usa os motores, aperte o botão **A** do robô para ele começar a andar
5. **ESC** para o robô e encerra

## Código estático por Bluetooth (validado)

Configuração utilizada: laptop Linux, **HC-06-20190901**, nome **POLOLU**, UART0
a **115200 baud, 8N1**, com **TXD do HC-06 → GP29**, **RXD → GP28** e GND comum.
O endereço do módulo desta montagem é `00:23:04:00:33:75`; outros módulos terão
outro endereço. A alimentação depende da placa do módulo; veja o guia antes
de montar.

O [guia Bluetooth/UART](examples/bluetooth_uart/README.md) cobre alimentação,
renomeação, descoberta, pareamento e criação de `/dev/rfcomm0`. Essa porta não
é criada automaticamente ao conectar os fios ou iniciar o receptor.

Com a `.venv` ativa, `pyserial` e `mpremote` instalados e `/dev/rfcomm0` já
configurada, execute os comandos **a partir da raiz do repositório**.

**Terminal 1 — iniciar o receptor pela USB e manter aberto:**

```bash
python -m mpremote connect /dev/ttyACM0 run examples/bluetooth_uart/receiver.py
```

**Terminal 2 — testar ida e volta pelo Bluetooth:**

```bash
python examples/bluetooth_uart/send_static.py --port /dev/rfcomm0 --baud 115200 --ping
```

Ao receber `PONG`, envie um dos exemplos:

```bash
# Cinco piscadas do LED amarelo
python examples/bluetooth_uart/send_static.py --port /dev/rfcomm0 --baud 115200

# Movimento imediato: frente por 5 segundos, depois parada
python examples/bluetooth_uart/send_static.py --port /dev/rfcomm0 --baud 115200 --file examples/bluetooth_uart/static_forward.py
```

**O exemplo de movimento não espera botão:** começa ao receber o código, com
velocidade `1500` nos dois motores, e os desliga ao terminar. Coloque o robô no
chão, com espaço livre e folga no cabo USB, antes de enviar. Os motores precisam
das pilhas e da chave ligada. O terminal deve mostrar `READY`, `RUNNING` e `DONE`.

| Arquivo | Função |
|---|---|
| [receiver.py](examples/bluetooth_uart/receiver.py) | Recebe pela UART, verifica integridade e executa em RAM |
| [send_static.py](examples/bluetooth_uart/send_static.py) | Envia o arquivo pelo Bluetooth do computador |
| [control_gui.py](examples/bluetooth_uart/control_gui.py) | Interface com direção, velocidade e parada por soltura |
| [control_receiver.py](examples/bluetooth_uart/control_receiver.py) | Controle contínuo com parada local por falta de comunicação |
| [static_blink.py](examples/bluetooth_uart/static_blink.py) | Pisca o LED amarelo cinco vezes |
| [static_forward.py](examples/bluetooth_uart/static_forward.py) | Anda por 5 segundos sem esperar botão e para |
| [rename_hc06.py](examples/bluetooth_uart/rename_hc06.py) | Identifica a velocidade/firmware e define o nome POLOLU |
| [test_uart_loopback.py](examples/bluetooth_uart/test_uart_loopback.py) | Diagnostica a UART com jumper, sem o módulo nas linhas |

Um reset remove o receptor da RAM: será necessário iniciá-lo novamente pela
USB. Não há parada remota por Bluetooth neste exemplo; o timeout do emissor
não interrompe o robô. Os programas enviados devem terminar por conta própria.

## Controle com interface gráfica

O controle contínuo usa **`control_receiver.py`**, um programa persistente no
Zumo que recebe velocidades. `receiver.py` continua sendo usado para enviar
arquivos estáticos. Pare a sessão anterior e inicie o receptor apropriado.

**Terminal 1 — Pololu pela USB:**

```bash
python -m mpremote connect /dev/ttyACM0 run examples/bluetooth_uart/control_receiver.py
```

**Terminal 2 — laptop, com `.venv` ativa e `/dev/rfcomm0` configurada:**

```bash
sudo apt install python3-tk
python examples/bluetooth_uart/control_gui.py
```

Clique em **Conectar** e aguarde a confirmação. **Segure** os botões para andar
para frente, dar ré ou girar; solte para enviar parada. Um clique rápido produz
um movimento curto. A velocidade vai de 500 a 3000. Parar, Espaço, Esc, perda de
foco e desconexão cancelam movimentos. Use o robô no chão com espaço livre.

A interface renova a direção aproximadamente a cada **50 ms**, sem esperar
cada confirmação para enviar a próxima atualização. O protocolo V2 numera os
comandos e as respostas, mantém no máximo oito envios pendentes e mostra a
latência na janela. A intenção de movimento expira em 200 ms se a janela parar
de atualizá-la. Soltar/Parar envia `STOP`, inclusive com a janela de ACKs cheia.

O receptor mantém a velocidade entre atualizações e desliga os motores após
**300 ms sem receber renovação válida**. Esse limite local não foi aumentado.
Após **1 s sem confirmação nova**, o laptop tenta recuperar a conexão. Ele
fecha a porta anterior, tenta reabrir a cada 1 s e encerra as tentativas após
**5 s sem comunicação confirmada**. A recuperação exige resposta do receptor
e confirmação de comandos; apenas abrir a porta não basta. Desconectar ou
fechar a janela cancela as tentativas. Ao recuperar a conexão, pressione uma
direção novamente: movimentos antigos não são restaurados. A parada local dos
motores continua em 300 ms; o prazo de 5 s é de reconexão.

É necessário reiniciar **ambos** os programas após atualizar: o novo controle
exige `POLOLU_CONTROL_V2`. Não é enviado código Python durante a condução.
O controle não pareia o módulo nem cria `/dev/rfcomm0`; não abra dois programas
na mesma porta Bluetooth.

Em uma medição de 15 segundos com motores parados e o receptor V1, foram
recebidas 66 respostas: mediana 154,7 ms, p95 251,3 ms e máximo 287,7 ms, sem
respostas acima de 500 ms. Isso evidencia latência, não prova defeito físico
nem descarta ruído durante movimento. Veja o [diagnóstico Bluetooth](examples/bluetooth_uart/README.md#diagnóstico-de-latência-e-transmissão)
para repetir o teste sem movimento. A versão V2 passou em simulações de atraso
de ACK de 600 ms, perda de retorno, parada e janela limitada; a medição física
após a atualização e com motores ligados ainda está pendente.

## Como o código recebido é executado

**O firmware MicroPython não foi modificado.** `receiver.py` é um programa
MicroPython iniciado por USB. Ele fica em um laço esperando dados na UART do
HC-06. Ao chegar um arquivo, recebe o cabeçalho com tamanho e SHA-256, responde
`READY`, recebe todos os bytes, confere a integridade, compila com `compile()` e
executa com `exec()`. Responde `RUNNING` antes da execução e `DONE` ao concluir;
desliga os motores e volta a esperar. Erros de execução geram `ERR EXEC`.

O gerenciador de memória do MicroPython aloca os buffers e o código compilado
no heap da RAM; objetos sem referências podem ser recuperados pelo coletor de
lixo. Cada envio recebe um novo dicionário de variáveis globais, mas compartilha
o interpretador, os módulos importados e o hardware. Isso não é isolamento de
segurança. Nada é salvo em `main.py` pelo receptor.

Enquanto o programa executa, o receptor não processa outro pedido. Um laço
infinito impede que ele volte a esperar. A interface gráfica usa o receptor separado `control_receiver.py`, que
processa comandos de velocidade sem compilar ou executar novos arquivos. Após reset ou desligamento, é necessário
iniciar `receiver.py` novamente: a inicialização automática não foi configurada.

## Hardware

Tudo já vem no chassi do Zumo 2040: 2 motores com encoders, display OLED, 6 LEDs
RGB, LED amarelo, buzzer, 3 botões, 5 sensores de linha, sensores de proximidade e
IMU. Detalhes em [zumo/setup_zumo.md](zumo/setup_zumo.md).

## Segurança

No fluxo de voz por USB, o código gerado por um LLM é executado no robô, então há três barreiras: o
*system prompt* restringe o que pode ser gerado (e exige apertar o botão A antes de
mover os motores), `codegen.is_safe()` bloqueia padrões perigosos (`os`, `open`,
`eval`, `exec`, `_thread`, `machine.reset`, `bootloader`…) antes do envio, e cada
envio (e o ESC) desliga motores, LEDs e buzzer antes de qualquer outra coisa. O
código é sempre impresso no terminal antes de rodar.

O exemplo Bluetooth executa arquivos escolhidos pelo usuário e não passa por
`codegen.is_safe()` nem exige o botão A. `static_forward.py` desliga os motores
em `finally`, inclusive em caso de exceção Python. O SHA-256 do transporte
confere integridade do arquivo; não autentica quem o enviou.

## Status

Em desenvolvimento. Em **18/11/2026**, o usuário confirmou o funcionamento do
envio e execução de `static_forward.py` pelo Bluetooth do laptop, com HC-06 e
Zumo 2040. A renomeação para POLOLU e o loopback em 9600/115200 também foram
confirmados. A execução desse fluxo em uma Raspberry Pi e sua integração com
voz ainda não foram validadas. Ver [docs/roadmap.md](docs/roadmap.md).
