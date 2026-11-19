# Dashboard

Interface local para aquisição USB, gráficos e gravação de ensaios em CSV.

## Executar

Requer Node.js 22 ou superior e npm. Nesta pasta:

```bash
npm ci
npm start
```

Abra [localhost:8765](http://127.0.0.1:8765) e mantenha o terminal aberto. Para encerrar, use `Ctrl+C`.

Nas próximas execuções, basta `npm start`. No Linux/macOS, `./start.sh` também funciona. Python não é necessário para executar esta dashboard.

O projeto foi testado no Linux. Windows e macOS são suportados pela biblioteca serial, mas podem precisar de driver USB e permissão para a porta. Instale as dependências no próprio computador; não copie `node_modules/` de outra máquina.

1. Selecione **USB** ou **Demo** e conecte.
2. Aguarde a primeira amostra.
3. Informe o nome, a distância do ventilador em metros e a velocidade de referência do vento. Selecione se a velocidade é estimada ou medida com anemômetro.
4. Clique em **Start recording**. Os parâmetros ficam bloqueados durante a gravação.
5. Clique em **Stop & save** para finalizar.
6. Consulte ou baixe o CSV pelo histórico lateral.

**Demo** usa dados gerados. Feche outros monitores seriais antes de conectar a USB. Fechar o navegador não encerra a gravação; finalize o ensaio antes de sair.

## Visualização

O painel mostra RPM, tensão, corrente, potência e energia, com tendências individuais. No gráfico, selecione a grandeza e o intervalo; passe o cursor para consultar uma amostra. Mínimo, média e máximo consideram as amostras válidas do intervalo exibido.

Busque ensaios pelo nome no histórico. O cronômetro acompanha a gravação atual. Dados Demo e USB ficam identificados.

## Configuração

Edite [config.json](config.json) para definir aquisição, limites de integração e metadados. `output_directory` é relativo a esta pasta. A amostragem USB é definida no firmware; `sample_interval_ms` afeta apenas o modo Demo. A velocidade do vento é informada pelo usuário.

| Variável de ambiente | Padrão |
| --- | --- |
| `BENCH_PORT` | `8765` |
| `BENCH_DATA_DIR` | `data/` nesta pasta |
| `BENCH_LOG_DIR` | `logs/` nesta pasta |

O terminal mostra o endereço local e o caminho do log. Conexões, gravações e erros ficam em `logs/server.log`, com data UTC e nível `INFO`, `WARN` ou `ERROR`.

## Ensaios

Cada pasta em `data/` contém:

| Arquivo | Conteúdo |
| --- | --- |
| `samples.csv` | Amostras, potência elétrica e energia integrada |
| `metadata.json` | Nome, origem, parâmetros, status e perdas de pacotes |

`fan_distance_m` é a distância da grade frontal do ventilador até o plano de rotação da hélice. O ensaio salva essa referência, a velocidade do vento, sua origem (`manual` ou `anemometer`), rotor, material e observações. A velocidade é informada manualmente, inclusive quando medida com anemômetro; não há aquisição automática desse instrumento. Os parâmetros aparecem ao abrir um ensaio no histórico. Ensaios antigos continuam disponíveis, sem atribuir uma distância que não foi registrada.

Em **Wind reference profile**, adicione opcionalmente pontos de tempo e velocidade, começando em 0 s e com tempos crescentes. Exemplo: 0 s → 5,1 m/s; 10 s → 5,8 m/s; 20 s → 6 m/s. Os tempos são relativos ao início da gravação. A interpretação mantém o valor anterior até o próximo ponto e o último até o fim. O perfil fica em `wind_speed_profile`, no `metadata.json`; ele não altera as amostras elétricas nem o cálculo de energia. Medições feitas em outro teste são referências, não medições sincronizadas do ensaio atual.

O botão **Setup** no histórico baixa os parâmetros em JSON. **CSV** baixa as amostras.

Para comparar patamares de velocidade, grave um ensaio por condição, após estabilizar o escoamento. Use as observações para registrar a regulagem do ventilador, a posição do anemômetro e a repetição.

A energia usa timestamps do dispositivo e integra apenas amostras válidas e consecutivas. Lacunas acima de `max_energy_gap_s` interrompem a integração. `integrated_duration_s` informa o intervalo efetivamente integrado.

RPM é magnitude. Ausência de pulsos gera `no_pulse`, sem confirmar rotação zero. A potência elétrica é tensão × corrente.

Com o firmware atualizado, o gráfico permite selecionar **RPM · raw diagnostic** para comparar o último intervalo bruto com a RPM filtrada. O CSV inclui `rpm_raw`, `hall_accepted_pulses` e `hall_rejected_pulses`. Os contadores acumulam desde a inicialização do ESP32; a diferença entre início e fim indica os eventos do ensaio. O `metadata.json` registra o algoritmo e os parâmetros em `hall_filter`. Pacotes de firmware antigo e modo Demo continuam aceitos, sem preencher diagnósticos ausentes.

Consulte as instruções do [firmware](../firmware/README.md).
