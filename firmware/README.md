# ESP32 firmware

Aquisição do INA219 e do Hall, transmissão USB e controle do LED de gravação.

## Compilar e gravar

Use PlatformIO pelo ambiente Python da raiz ou pela extensão do VS Code. Os comandos abaixo partem desta pasta:

```bash
pio run
pio device list
```

Na primeira compilação, o PlatformIO baixa as ferramentas definidas em `platformio.ini`. Para gravar, feche a conexão USB da dashboard e o Monitor Serial. Substitua a porta pelo dispositivo identificado:

```bash
pio run -t upload --upload-port /dev/ttyUSB0
```

Para acompanhar as amostras:

```bash
pio device monitor --port /dev/ttyUSB0 --baud 115200
```

A porta varia por sistema: `/dev/ttyUSB0` no Linux, `COM3` no Windows ou `/dev/cu.usbserial-*` no macOS, por exemplo. A validação do projeto foi feita no Linux.

O firmware permanece no ESP32 após a gravação. Outra placa exige conferir o modelo em `platformio.ini` e os GPIOs.

## Configuração

Parâmetros em [include/hardware_config.h](include/hardware_config.h).

| Sinal | GPIO |
| --- | --- |
| Hall, após conversor de nível | 27 |
| INA219 SDA | 21 |
| INA219 SCL | 22 |
| LED de gravação | 2 |

O INA219 usa endereço `0x40` e shunt de `0,1 Ω`. As flags dos sensores estão habilitadas. Confira a montagem antes de gravar; o sinal do Hall deve ser compatível com 3,3 V. A configuração atual usa um pulso por volta.

## Leitura do Hall

O firmware usa a mediana dos três últimos períodos aceitos. A primeira RPM requer quatro passagens do ímã; a mediana acompanha mudanças com atraso de cerca de um pulso. Após 3 s sem pulso aceito, envia `no_pulse` e RPM `null`. A retomada começa uma janela nova, sem usar o intervalo da parada.

Pulsos separados por menos de `MIN_PULSE_INTERVAL_US` (1 ms) são rejeitados. Com a janela preenchida, também são rejeitadas passagens antes de `MIN_PERIOD_RATIO` (0,25) do período mediano. O instante rejeitado não muda a referência da próxima volta. Esse limiar é uma hipótese de continuidade do movimento, não um limite de RPM calibrado: acelerações maiores que quatro vezes a velocidade em uma volta podem ser rejeitadas até a recuperação por timeout. Com o timeout atual, períodos acima de 3 s não produzem RPM válida.

`rpm` contém o resultado filtrado; `rpm_raw` usa o último intervalo entre bordas, antes dos filtros. `hall_accepted_pulses` e `hall_rejected_pulses` são contadores desde a inicialização do ESP32. `hall_filter` identifica o algoritmo e seus parâmetros. Esses diagnósticos seguem para a dashboard e não alteram tensão ou corrente.

O filtro reduz pulsos extras isolados. Não identifica dois ímãs, acionamentos extras regulares, falhas de contato ou montagem incorreta. Valide em bancada com uma passagem por volta e compare RPM bruta e filtrada.

Para testar o filtro no computador, sem ESP32, a partir da raiz:

```bash
g++ -std=c++11 -Wall -Wextra -Werror -Ifirmware/include firmware/tests/hall_pulse_filter_test.cpp -o /tmp/hall-pulse-filter-test
/tmp/hall-pulse-filter-test
node --test dashboard/tests/measurements.test.js
```

O LED azul acende durante gravação USB e apaga ao parar ou após 3 segundos sem comandos de controle. O LED de alimentação é independente.

Para buscar dispositivos I²C, envie `SCAN_I2C` seguido de LF, com a gravação parada. O INA219 deve responder com `I2C found 0x40`.

Consulte as instruções da [dashboard](../dashboard/README.md).
