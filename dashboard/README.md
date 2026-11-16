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
3. Informe o nome do ensaio e clique em **Start recording**.
4. Clique em **Stop & save** para finalizar.
5. Consulte ou baixe o CSV pelo histórico lateral.

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

A energia usa timestamps do dispositivo e integra apenas amostras válidas e consecutivas. Lacunas acima de `max_energy_gap_s` interrompem a integração. `integrated_duration_s` informa o intervalo efetivamente integrado.

RPM é magnitude. Ausência de pulsos gera `no_pulse`, sem confirmar rotação zero. A potência elétrica é tensão × corrente.

Consulte as instruções do [firmware](../firmware/README.md).
