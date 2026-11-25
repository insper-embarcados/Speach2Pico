# Código estático: Bluetooth do laptop → HC-06 → Zumo 2040

O computador envia um arquivo MicroPython pelo Bluetooth e o Zumo 2040 o
executa em RAM. Não usa voz, APIs nem geração de código. Há dois exemplos:

- [`static_blink.py`](static_blink.py): cinco piscadas do LED amarelo.
- [`static_forward.py`](static_forward.py): movimento imediato para frente por
  5 segundos, sem botão, com velocidade `1500` nos dois motores e parada em `finally`.

**Funcionamento confirmado pelo usuário em 18/11/2026:** envio e execução do
movimento pelo Bluetooth do laptop Linux. O módulo respondeu com firmware
`HC-06-20190901`, aceitou o nome `POLOLU` e opera em **115200 baud**.
Seu endereço nesta montagem é **00:23:04:00:33:75**; substitua-o nos comandos
se usar outro módulo. A UART também passou no loopback em 9600 e 115200.
O uso em Raspberry Pi/Linux é uma possibilidade, ainda não validada nesta montagem.

O HC-06 transporta bytes; quem recebe e executa é `receiver.py`, no Zumo.
Este guia é para **Zumo 2040**, não para Zumo 32U4.

```text
Laptop Linux: send_static.py + arquivo MicroPython
              │ Bluetooth Classic/SPP
              ▼
       HC-06 — POLOLU
        TXD         RXD
         │           ▲
         ▼           │
      GP29/RX     GP28/TX    UART0, 115200 baud, 8N1
          Zumo 2040: receiver.py → execução em RAM
```

## 1. Material e identificação

- Pololu **Zumo 2040**, com o MicroPython e a biblioteca `zumo_2040_robot`.
- Laptop Linux com Bluetooth **Classic/SPP** integrado ou por
  adaptador USB. O HC-06 não é um dispositivo BLE.
- HC-06, fios e conexões firmes nos pontos de expansão do Zumo.
- Cabo USB para carregar inicialmente o receptor no Zumo.
- Alimentação apropriada à **placa exata** do HC-06, conforme abaixo.

Não use a numeração física de uma Raspberry Pi Pico: os nomes **GP28 e GP29**
referem-se aos pontos de expansão do próprio Zumo. Eles aparecem na expansão
superior esquerda e na expansão frontal. Veja o desenho oficial em
[conectores e pinagem do Zumo](https://www.pololu.com/docs/0J87/all#6.9).
Se esses pontos não tiverem conectores soldados, solde um conector adequado com
tudo desligado; encostar fios nos furos não garante contato.

## 2. Ligação elétrica

Desconecte USB e pilhas antes de montar.

| Pino do HC-06 | Conectar a | Função |
|---|---|---|
| TXD | **GP29** do Zumo | Dados do HC-06 para RX da UART0 |
| RXD | **GP28** do Zumo | Dados de TX da UART0 para o HC-06 |
| GND | **GND** do Zumo e GND da fonte do módulo | Referência comum |
| VCC | Alimentação compatível com sua placa, explicada abaixo | Alimentação do HC-06 |
| KEY/EN | Conforme a placa, no modo normal de dados | Não entrar em modo AT durante o teste |
| STATE | Sem conexão neste exemplo | Não utilizado |

**TX cruza com RX. Os sinais da UART devem ser de 3,3 V.** O RP2040 não tolera
5 V nas entradas. Com um HC-06 de UART de 3,3 V, a ligação dos sinais é direta;
não se aplica aqui o divisor usado para baixar o TX de um Arduino de 5 V.

### Como alimentar o HC-06

Na montagem utilizada, o usuário conectou VCC ao **VSW** e mediu **5,9 V**.
Isso registra a montagem, mas não estabelece uma faixa de alimentação segura
para outras placas. VSW depende das pilhas e da chave; USB sozinha não fornece
alimentação por esse ponto. Confira a especificação da sua placa antes de usá-lo.

A inscrição “HC-06” não identifica sozinha a faixa de tensão de **VCC**:

- **Plaquinha adaptadora com regulador e entrada especificada para 5 V:** use
  uma fonte **regulada de 5 V**, por exemplo uma fonte USB com adaptador para
  alimentação, no VCC da plaquinha. Ligue o negativo dessa fonte ao GND do Zumo.
  Confirme essa faixa na inscrição ou documentação da sua placa. Não presuma
  que alimentar essa entrada com 3,3 V funcionará: o regulador pode reduzir
  demais a tensão que chega ao módulo.
- **Módulo/placa cuja entrada esteja explicitamente especificada para 3,3 V:**
  pode usar **3V3 do Zumo → VCC**, com GND comum. Não aplique 5 V nessa entrada.

Para a primeira montagem com uma plaquinha de entrada de 5 V, use a fonte
regulada externa; o Zumo pode ficar alimentado pela USB. O laptop se
comunica pelo rádio, sem conexão UART por fios com o robô.

**Não use VBST ou VB/VU como se fossem saídas de 5 V.** VBST é normalmente
8,3 V e VB/VU pode vir dessa tensão. VBAT/VSW também não são saídas reguladas
de 5 V. Para alimentar posteriormente tudo pelas pilhas, uma placa HC-06 que
exija 5 V precisará de um regulador adequado à faixa das quatro pilhas.

A [Pololu documenta GP28/GP29 como pinos livres para UART0 e os níveis de 3,3 V](https://www.pololu.com/docs/0J87/all#6.11).
As [tensões de alimentação do Zumo estão na seção 6.8](https://www.pololu.com/docs/0J87/all#6.8).
Não use GP0/GP1 neste exemplo: eles são compartilhados com o display.

## 3. Preparar o laptop Linux

Execute os comandos a partir da raiz deste repositório. A conexão Bluetooth
precisa ocorrer na máquina em que você executará `send_static.py`.

```bash
sudo apt update
sudo apt install bluez python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pyserial mpremote
```

Esses são os únicos pacotes Python necessários para este teste. Não precisa
instalar as dependências de voz do projeto nem configurar `.env`.

## 4. Iniciar o receptor no Zumo por USB

O receptor está configurado para **115200 baud, 8 bits, sem paridade, 1 stop bit**,
valor confirmado no módulo desta montagem. Se usar outra unidade, a velocidade
da UART do módulo deve coincidir com `BAUDRATE` em `receiver.py`.
O receptor recebe programas pelo canal Bluetooth de dados; não é um terminal AT.

Localize a porta do Zumo:

```bash
python -m mpremote connect list
```

No terminal 1, substitua `/dev/ttyACM0` pela porta que apareceu:

```bash
python -m mpremote connect /dev/ttyACM0 run examples/bluetooth_uart/receiver.py
```

Saída esperada:

```text
Bluetooth pronto: UART0 TX=GP28 RX=GP29, 115200 baud
Aguardando PING ou codigo. Ctrl+C via USB encerra.
```

Deixe esse terminal aberto. A USB inicia o receptor e mostra mensagens de
diagnóstico; o programa de teste será enviado pela conexão Bluetooth. O
receptor desliga os motores ao iniciar. A USB pode alimentar a lógica do Zumo;
**motores e HC-06 ligado ao VSW precisam das pilhas e da chave ligada**. Para
um teste apenas de LED, a chave pode ficar desligada somente se o HC-06 tiver
alimentação independente adequada.

Nada é copiado para `main.py`: um reset remove o receptor da RAM e volta ao
programa de inicialização existente. Depois do reset, execute novamente o
comando acima. Iniciar automaticamente sem USB é uma etapa posterior.

## Opcional: renomear um HC-06 para POLOLU

Se estiver usando **HC-06 com firmware `HC-06-20190901`**, há um script separado:
[`rename_hc06.py`](rename_hc06.py). Ele usa UART0, GP28/GP29, e procura o módulo
em **115200 baud primeiro, depois 9600 baud**. Se não responder, o diagnóstico
também tenta 38400, 19200, 57600, 4800, 2400 e 1200. Essa busca ampliada é uma
extensão local, não parte do procedimento validado pelo Insper. A busca completa
pode levar de 2 a 3 minutos e não altera a velocidade configurada no HC-06.
Não use esse script como procedimento de configuração do HC-05, que pode
exigir outro modo AT e outra sintaxe.

Interrompa `receiver.py` com Ctrl+C e encerre a sessão `mpremote` anterior
(Ctrl+] se estiver no console). O módulo deve estar alimentado corretamente
e **sem conexão Bluetooth ativa** com laptop, celular ou outro dispositivo.
Não precisa estar pareado nem ter `/dev/rfcomm0` para esta etapa.

Execute pela USB do Zumo:

```bash
python -m mpremote connect /dev/ttyACM0 run examples/bluetooth_uart/rename_hc06.py
```

O procedimento segue a [referência de bancada do Insper](https://github.com/insper-embarcados/pico-rtos-hc06-rx-tx/blob/f8bb3c48f3469c18edf3e9f043305f566ba9ee9c/docs/HC-06-20190901.md)
e o [código de configuração do módulo](https://github.com/insper-embarcados/pico-rtos-hc06-rx-tx/blob/f8bb3c48f3469c18edf3e9f043305f566ba9ee9c/main/hc06.c):

1. Aguarda 5 segundos para inicialização.
2. Testa `AT` até três vezes em cada velocidade, com pausas de 5 segundos
   entre tentativas. Uma tentativa sem resposta não encerra a busca.
3. Ao receber `OK`, consulta `AT+VERSION` e exige `HC-06-20190901`.
4. Envia `AT+NAMEPOLOLU` e procura `OKsetname` na resposta.

Todos os comandos são enviados sem CR/LF. Os bytes recebidos são impressos.
O script **não muda baud rate nem PIN**: apenas detecta a velocidade existente
e configura o nome. Módulos previamente configurados pelo exemplo do Insper
podem estar em 115200, em vez de 9600 baud.

O exemplo do Insper usa **Pico 2, UART1 e GP4/GP5**. Aqui, os pinos continuam
**UART0, GP28/GP29**, próprios desta montagem no Zumo. A alimentação descrita
lá é VBUS/5 V para o breakout; isso **não significa que VSW do Zumo seja 5 V
regulado**. A referência registra testes do Insper, não uma especificação
universal de todos os módulos comercializados como HC-06.

Após confirmação, desligue e religue a alimentação do **módulo** e faça uma
nova busca no laptop por `POLOLU`. Um nome antigo pode permanecer no cache do
computador. Antes de iniciar novamente `receiver.py`, ajuste seu `BAUDRATE`
para o valor detectado e impresso pelo script. O script de
renomeação encerra e não recebe programas. Alterar `--baud` no emissor não
substitui esse ajuste da UART do Pololu.

Se mostrar `(sem resposta)`, ainda não há confirmação de comunicação AT.
Deixe terminar as tentativas em todas as velocidades e guarde a saída completa.
Se todas falharem, confira alimentação, TX/RX e ausência de conexão Bluetooth.
Se `AT` responder, mas a versão for diferente, o script informa a versão e
não envia o nome; outras variantes precisam de sua própria referência.
Nesta montagem, foram recebidos `OK`, `HC-06-20190901` e `OKsetname`,
confirmando comunicação a 115200 e aceitação do nome POLOLU.

## 5. Parear o HC-06 e criar a porta serial Bluetooth

Em outro terminal do laptop Linux:

```bash
bluetoothctl
```

Dentro do `bluetoothctl`:

```text
power on
agent KeyboardOnly
default-agent
scan bredr
```

Espere cerca de 30 segundos, execute `scan off` e `devices` para listar os
dispositivos encontrados. Procure `POLOLU`.

Identifique o endereço do seu módulo. Nos comandos seguintes, substitua
`00:23:04:00:33:75` se estiver usando outra unidade:

```text
pair 00:23:04:00:33:75
trust 00:23:04:00:33:75
scan off
quit
```

Informe o PIN configurado no módulo quando solicitado. `1234` e `0000` são
valores comuns, mas consulte a documentação da sua unidade. Parear sozinho
não testa a UART.

Descubra o canal do serviço serial:

```bash
sdptool search --bdaddr 00:23:04:00:33:75 SP
```

Procure **Serial Port**, **RFCOMM** e **Channel**. `sdptool browse` pode
mostrar apenas `Browse Group Descriptor`; isso não informa o canal. Use a busca
direta acima. Se o canal encontrado for 1:

```bash
sudo rfcomm bind 0 00:23:04:00:33:75 1
ls -l /dev/rfcomm0
```

A porta `/dev/rfcomm0` **não aparece automaticamente** com o módulo ligado,
pareado ou com `receiver.py` rodando. Ela é criada pelo vínculo RFCOMM.
Troque o último número se o serviço indicar outro canal. `bind` cria o
vínculo local; a conexão é feita quando o script abre `/dev/rfcomm0`.
Não é necessário obter sucesso em `bluetoothctl connect`: esse comando pode
falhar por falta de um perfil local mesmo quando a conexão serial por RFCOMM
funciona. Se houver um vínculo antigo em `rfcomm0`, libere-o antes de refazer:

```bash
sudo rfcomm release 0
```

Se a porta pertencer ao grupo `dialout` e houver erro de permissão:

```bash
sudo usermod -aG dialout "$USER"
```

Saia da sessão e entre novamente para aplicar o grupo. O grupo também pode
ser necessário para acessar a porta USB do Zumo. Não precisa executar o
script Python como administrador. A disponibilidade de `rfcomm` e `sdptool`
depende do pacote BlueZ da distribuição; estas instruções usam essas ferramentas.

## 6. Testar a UART e enviar o código

No terminal 2, na raiz do repositório:

```bash
source .venv/bin/activate
python examples/bluetooth_uart/send_static.py --port /dev/rfcomm0 --baud 115200 --ping
```

Esperado: `[robo] PONG` e `UART confirmada.` Isso verifica o caminho completo
de ida e volta **laptop → Bluetooth → HC-06 → UART → receptor do Zumo**.

Agora envie o código fixo:

```bash
python examples/bluetooth_uart/send_static.py --port /dev/rfcomm0 --baud 115200
```

Esperado:

```text
Enviando .../static_blink.py (... bytes)
[robo] PONG
[robo] READY
[robo] RUNNING
[robo] DONE
Codigo recebido e executado; teste concluido.
```

O LED amarelo deve piscar cinco vezes, durante aproximadamente 2,5 segundos.
O arquivo é enviado de verdade: o receptor não contém a rotina de piscadas.
Altere o número de repetições em `static_blink.py` e envie novamente para
comprovar. Não aperte o botão A durante a observação, pois ele compartilha
o pino do LED amarelo.

### Movimento imediato por 5 segundos

Coloque o robô no chão, com espaço livre e folga no cabo USB, e ligue a
alimentação das pilhas. O programa **não espera botão A nem outra confirmação**:
começa assim que é recebido e executado.

```bash
python examples/bluetooth_uart/send_static.py --port /dev/rfcomm0 --baud 115200 --file examples/bluetooth_uart/static_forward.py
```

São enviados `motors.set_speeds(1500, 1500)` e uma espera de 5000 ms.
O bloco `finally` desliga os motores ao terminar ou ocorrer uma exceção Python.
O usuário confirmou o funcionamento físico desse exemplo.

Também é possível escolher outro programa **finito**:

```bash
python examples/bluetooth_uart/send_static.py --port /dev/rfcomm0 --baud 115200 --file examples/bluetooth_uart/static_blink.py
```

`--baud` configura a porta local, mas **não altera a configuração UART interna
do HC-06**. Ela precisa coincidir com `BAUDRATE` do receptor. Para programas
mais demorados, ajuste `--timeout` (padrão: 30 segundos por resposta).

## Controle com interface gráfica

A interface usa **`control_receiver.py` no robô**, dedicado a comandos de
velocidade contínuos. Ela não funciona com `receiver.py`, que permanece destinado
à transferência dos arquivos estáticos. Não é necessário modificar o firmware.

Feche a GUI anterior e pare a sessão USB anterior. Na raiz do repositório,
com `.venv` ativa, inicie no terminal 1:

```bash
python -m mpremote connect /dev/ttyACM0 run examples/bluetooth_uart/control_receiver.py
```

Com o módulo pareado e a porta RFCOMM criada, abra a interface no terminal 2:

```bash
sudo apt install python3-tk
source .venv/bin/activate
python examples/bluetooth_uart/control_gui.py
```

Escolha `/dev/rfcomm0` e clique em **Conectar**. Os botões são habilitados após
identificar o receptor de controle. **Segure** Frente, Ré, Esquerda ou Direita
para mover continuamente; solte para enviar parada. Um clique breve move por
pouco tempo. O ajuste de velocidade vai de 500 a 3000. Parar, Espaço, Esc,
perda de foco e desconexão cancelam a direção atual.

A GUI usa comandos curtos de velocidade, sem reenviar código Python. O
protocolo **V2** continua enviando a cada aproximadamente 50 ms enquanto recebe
ACKs de forma independente. Assim, um atraso isolado na resposta não bloqueia
imediatamente a renovação de movimento.

**Reinicie o receptor e a GUI após a atualização.** A identificação V2 evita
usar silenciosamente o protocolo novo com o receptor V1 antigo ainda na RAM.

### Protocolo de controle contínuo V2

| Pedido | Resposta | Efeito |
|---|---|---|
| `HELLO` | `POLOLU_CONTROL_V2` | Para os motores, reinicia a sequência e habilita a sessão |
| `M <sequência> <esquerda> <direita>` | `ACK <sequência> OK` | Aplica velocidades de -3000 a 3000 e renova o prazo |
| `STOP` | `STOPPED` | Desliga os motores |

Cada linha termina em `\n`. A UART permanece em **115200 baud, 8N1, GP28/GP29**.
Sequências antigas não reaplicam movimentos nem renovam o prazo. O receptor
verifica **300 ms sem comando válido de movimento**, para os motores e exige
novo `HELLO` quando esse prazo vence. Mensagens inválidas ou incompletas também
provocam parada. O formato legado `M <esquerda> <direita>` é aceito para testes
locais, mas a GUI usa exclusivamente sequências V2.

A janela permite no máximo **oito comandos pendentes**. Um ACK mais novo supera
pendências anteriores no fluxo ordenado. O contador `superseded` registra essas
pendências; não é uma medição direta de pacotes perdidos pelo rádio. Após 1 s sem ACKs novos, o host cancela a direção e tenta `STOP`, fecha a
porta e inicia reconexão. Repete tentativas em intervalos de 1 s e encerra após
5 s sem comunicação confirmada. Uma resposta `HELLO` isolada não reinicia esse
prazo; é preciso receber ACK de controle. O primeiro movimento após reconexão
exige um novo pressionamento do botão. Desconectar ou fechar a janela cancela
as tentativas. A parada local dos motores permanece em 300 ms; os 5 s valem
para recuperar a conexão.
A janela limitada impede crescimento indefinido de comandos atrasados. A parada
local de 300 ms não depende de o laptop receber resposta.

Soltar o botão envia parada na próxima iteração, sem aguardar os ACKs pendentes.
Fechar/desconectar também tenta `STOP`. Se a janela não atualizar a intenção por
200 ms, o emissor passa a enviar parada. Comandos já em trânsito ainda podem
chegar: os tempos locais não são garantia de parada em tempo real a partir do
clique. Coloque o robô no chão com espaço livre e folga no cabo USB.

### Diagnóstico de latência e transmissão

Feche a GUI e mantenha o receptor de controle rodando. Este teste envia apenas
comandos que **mantêm os motores parados**, e reconhece receptores V1 e V2:

```bash
python examples/bluetooth_uart/diagnose_bluetooth.py --seconds 15 --output /tmp/pololu-bluetooth.json
```

O relatório informa latências mediana, p95 e máxima, confirmações e erros. No
V2, informa também envios pendentes e confirmações superadas. A GUI mostra o
p95 durante o uso; ele mede ida e volta pelo conjunto Linux/RFCOMM/HC-06/UART/
receptor, não apenas o tempo de rádio.

[Resultado real de 18/11/2026](diagnostics/2026-11-18-baseline.json), com receptor
V1 e motores parados: **66 respostas**, mediana **154,7 ms**, p95 **251,3 ms**,
máximo **287,7 ms**, sem resposta acima de 500 ms. O protocolo anterior aguardava
um ACK para renovar o movimento, aproximando-se do watchdog de 300 ms mesmo
nesse teste. Os registros Bluetooth consultados não identificaram uma causa
física específica. A descoberta mostrou RSSI de -38 dBm, mas isso é uma amostra
de descoberta, não uma medição do sinal durante a falha.

O tráfego desses comandos é da ordem de centenas de bytes por segundo, abaixo
da capacidade nominal da UART de 115200/8N1 (11520 bytes/s). Isso não elimina
atrasos de buffering, retransmissões ou interferência. Para separar causas:

1. Repita o teste parado, perto do laptop, após iniciar o receptor V2.
2. Observe o p95 da GUI durante movimento. Se a degradação aparecer só com os
   motores, investigue alimentação/contatos/ruído, não apenas timeout de software.
3. Confira quedas de tensão no VCC do módulo sob carga e GND comum. Um multímetro
   pode não capturar transientes rápidos; o teste não certifica a alimentação.
4. Compare distância/obstáculos e proximidade do módulo aos motores. Para
   registrar eventos no laptop, use `sudo btmon` em outro terminal; uma captura
   pode incluir outros dispositivos próximos.

Não há evidência suficiente para declarar o HC-06 defeituoso. A versão V2 foi
verificada por simulação com ACKs atrasados 600 ms, perda total de retorno,
sequências antigas e parada com janela cheia. A medição física após a atualização
e durante movimento ainda precisa ser realizada.

Não use `send_static.py` simultaneamente nem contra esse receptor. Para voltar
a enviar arquivos, pare o controle e inicie `receiver.py` novamente.

## 7. Se não funcionar

### HC-06 não responde a AT

Para separar um problema da UART de um problema no módulo/ligação, execute
[`test_uart_loopback.py`](test_uart_loopback.py):

1. Pare o programa anterior, desconecte USB e desligue a alimentação das pilhas
   e qualquer fonte externa do módulo.
2. Desconecte os fios TXD e RXD do HC-06 dos pinos do Zumo.
3. Coloque **somente um jumper entre GP28 e GP29**. Não conecte esses pinos a VCC.
4. Reconecte a USB do Zumo e execute:

```bash
python -m mpremote connect /dev/ttyACM0 run examples/bluetooth_uart/test_uart_loopback.py
```

O resultado esperado é **PASSOU** em 9600 e 115200, com RX igual a TX. Isso
confirma a comunicação local da UART, não o HC-06. Se falhar, confira o contato
do jumper e se são realmente os pontos **GP28/GP29**, não números físicos de
um conector. Falhar sozinho não prova defeito no Pololu.

Ao terminar, desligue novamente e **remova o jumper** antes de religar o módulo:
RXD do HC-06 em GP28, TXD em GP29 e GND comum. Depois de um loopback aprovado,
o próximo diagnóstico é conferir a tensão real entre VCC e GND do módulo,
comparando-a à especificação da placa, e identificar seu firmware/estado.
Não conclua que o módulo está defeituoso somente pela ausência de resposta AT.

| Sintoma | Verificar |
|---|---|
| HC-06 não aparece no scan | Alimentação, Bluetooth Classic, modo de dados e se já está conectado a outra máquina |
| `/dev/rfcomm0` não existe | Criar o vínculo com `rfcomm bind`; nada é enviado se a porta não abre |
| Porta RFCOMM não abre | Pareamento/PIN, endereço, canal SPP, vínculo antigo e permissões |
| Pareia, mas não recebe `PONG` | Receptor iniciado, TX/RX cruzados, GP28/GP29, GND comum e baud rate de dados |
| Caracteres inválidos | Velocidade/paridade, alimentação e níveis elétricos |
| `ERR HASH` | Os bytes recebidos não conferem; código não executado. Confira fios/alimentação e reinicie o receptor |
| `ERR SIZE` | Arquivo vazio ou maior que 4096 bytes |
| `ERR TIMEOUT` | Transmissão incompleta; o receptor encerra e precisa ser iniciado novamente |
| `ERR SYNTAX` | Código recebido não compila ou não é UTF-8; ajuste o arquivo |
| `ERR EXEC` | Código começou, mas falhou; veja a exceção no terminal USB |
| `RUNNING`, sem `DONE` | Programa pode estar bloqueado ou a resposta se perdeu; observe o robô e interrompa pela USB/reset antes de repetir |

Após erro de protocolo (`HEADER`, `HASH`, `SIZE`, `TIMEOUT`, etc.), o receptor
encerra para não interpretar restos da transmissão como outro programa.
Reinicie-o pelo comando `mpremote run`. Não há reenvio automático: a perda
de uma resposta não prova que o código deixou de executar.

## Protocolo e limites deste exemplo

`receiver.py` fica em um laço aguardando dados, até ser interrompido, ocorrer
erro de protocolo ou o robô reiniciar. Usa o MicroPython já instalado, sem
alterar o firmware. O MicroPython aloca os buffers de recepção e o programa
compilado na RAM, por meio do seu gerenciador de memória.

1. Host envia `PING\n`; Zumo responde `PONG\n`.
2. Host envia `S2P1 <quantidade_de_bytes> <sha256_em_hex>\n`.
3. Zumo valida o cabeçalho e responde `READY\n`.
4. Host envia exatamente os bytes do arquivo UTF-8, sem terminador adicional.
5. Zumo confere o SHA-256, compila e responde `RUNNING\n` antes de executar.
6. Ao terminar, responde `DONE\n`; em erro de execução, `ERR EXEC\n`.

O limite é 4096 bytes por programa e 15 segundos para receber cada cabeçalho
ou corpo. O receptor usa a [API UART do MicroPython](https://docs.micropython.org/en/latest/library/machine.UART.html).
Os `print()` do programa aparecem na USB, não no protocolo Bluetooth.

Após conferir os bytes, `compile()` transforma o texto em código executável
pelo interpretador e `exec()` o executa. Cada envio usa um novo dicionário de
variáveis globais; módulos importados e hardware continuam compartilhados.
Ao retornar, objetos sem referências ficam disponíveis para coleta de lixo.
Não é gravado um arquivo no robô, nem é configurado início automático.

É uma prova de conceito para **código conhecido em bancada**: `exec` executa
com todos os privilégios do MicroPython, sem isolamento nem os filtros de
`host/codegen.py`. O SHA-256 verifica integridade, não autentica o remetente.
Só envie programas que você revisou.

Enquanto o programa executa, o receptor não processa novos pedidos. Um laço
infinito impede novos envios e não existe parada remota por Bluetooth neste
exemplo. O timeout do emissor não interrompe o código no robô. Use Ctrl+C no
terminal USB ou reset para interromper. O exemplo de movimento incluído é
finito (5 segundos) e não possui comando remoto de parada. O tratamento de
interrupções Python não substitui um mecanismo independente de parada.

## Verificação sem hardware

```bash
python3 -m unittest discover -s examples/bluetooth_uart/tests -v
```

Os testes simulam a transmissão fragmentada e verificam integridade,
truncamento, respostas de erro e execução. Não substituem o teste físico de
alimentação, pareamento, UART ou compatibilidade do firmware MicroPython.
O teste físico confirmado é o do laptop Linux com o HC-06 e Zumo 2040
descritos neste guia. Outros hosts, módulos e firmwares requerem validação.
