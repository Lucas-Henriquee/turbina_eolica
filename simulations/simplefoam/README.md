# SimpleFoam simulation

Caso estacionário para OpenFOAM 2512, `simpleFoam`, `kOmegaSST` e zona rotativa MRF. A malha fica fixa e a velocidade angular é prescrita no eixo Y.

## Preparação

Requer OpenFOAM 2512 e o ambiente Python da raiz. MPI é necessário para execução paralela. Os comandos partem desta pasta.

```bash
source ../../.venv/bin/activate
source /usr/lib/openfoam/openfoam2512/etc/bashrc
python3 -m pip install -r ../../requirements.txt
```

Em uma execução exportada, use um ambiente Python próprio e instale com `python3 -m pip install -r requirements.txt`.

## Executar

| Comando | Ação |
| --- | --- |
| `./create_mesh.sh` | Prepara o caso, gera a malha e executa `checkMesh` |
| `./run_serial.sh` | Gera a malha, executa e analisa em série |
| `./run_mpi.sh 6` | Executa o fluxo completo com 6 processos |

Se houver malha ou resultados na raiz, preserve-os antes de iniciar:

```bash
python3 scripts/archive_case.py --status interrupted
```

`Ctrl+C` interrompe o solver e arquiva os campos parciais. O terminal mostra status, duração e caminhos de saída; resíduos e detalhes ficam nos logs.

## Configurar

Edite [config.yaml](config.yaml). Cada parâmetro tem uma descrição curta e sua unidade. As entradas OpenFOAM são geradas a partir de `config/templates/`.

| Seção | Conteúdo |
| --- | --- |
| `geometry` | Hélice, centro e folgas do cilindro MRF |
| `bench` | Diâmetro e velocidade do ventilador, distância e altura do eixo |
| `fluid` / `initial` | Propriedades do ar e estado inicial |
| `turbulence` | Modelo e valores de k e omega |
| `rotation` | Velocidade angular prescrita |
| `iterations` | Limite de iterações e gravação de campos |
| `mesh` | Domínio, células e refinamentos |
| `numerics` | Solvers, relaxação e critérios SIMPLE |
| `output` | Amostragem, médias e gráficos |
| `parallel` | Decomposição e processos MPI |

A geometria usa `propeller_test.stl`. O cilindro é gerado pelas folgas, e raio, diâmetro e área varrida são calculados do STL. A malha usa nível 6 na hélice, nível 2 na superfície do cilindro e até duas camadas junto às pás.

A malha de referência tem 51.830 células no OpenFOAM 2512, com a hélice na posição do STL. A entrada circular de 40 cm fica a 1 m do rotor, com eixo a 40 cm do chão. O caso usa 6,86 m/s na entrada, valor obtido na calibração da bancada do PimpleFoam para cerca de 6,20 m/s no centro sem a hélice.

O MRF calcula o torque a −132 RPM com as pás em uma posição fixa. O caso serve para estudar a faixa de equilíbrio e a sensibilidade do torque à malha e à posição das pás.

Para preparar sem gerar a malha:

```bash
python3 scripts/prepare_case.py
```

## Monitorar com watch

```bash
watch -n 2 python3 scripts/monitor_run.py
```

O monitor mostra iteração, orçamento utilizado, ETA até o limite e resíduos iniciais de `p`, `U`, `k` e `omega`. O estado `CONVERGED` vem da mensagem do próprio SIMPLE.

A barra representa o limite de iterações, não tempo físico nem percentual de convergência. O solver pode convergir antes de atingir 100%. A ETA é aproximada e exclui malha e análise.

Use `--case /path/to/case` para outra pasta e `--stale-seconds 300` para alterar o aviso de ausência de atualização. O monitor apenas lê os arquivos e acompanha o último caso arquivado quando o log sai da raiz.

## Resultados e logs

Execuções concluídas ficam em `runs/testNNN_<data>/`; falhas e interrupções, em `runs/failedNNN_<data>/`. Cada pasta guarda entradas, configuração e scripts próprios.

| Arquivo | Conteúdo |
| --- | --- |
| `results/iterations.csv` | RPM imposto, torque, força, potência, Cp e TSR por iteração |
| `results/summary.json` | Médias e indicação de convergência |
| `results/summary.txt` | Resumo da análise |
| `results/*_vs_iteration.png` | Gráficos por iteração |
| `metadata/resolved_config.json` | Configuração efetiva e geometria |
| `config.txt` | Relatório e entradas OpenFOAM |
| `logs/log.simpleFoam` | Resíduos, iterações e convergência |
| `logs/log.checkMesh` | Qualidade da malha |
| `postProcessing/yPlusRotor/` | Mínimo, máximo e média de y+ por parede |
| `logs/log.analyze_results` / `logs/log.plot_results` | Análise e gráficos |
| `<run>.foam` | Campos e malha para ParaView |

Durante a execução, os logs ficam na raiz. Para acompanhar diretamente:

```bash
tail -f log.simpleFoam
```

Resumo da última execução concluída:

```bash
python3 scripts/show_results.py
```

## Análise estacionária

A potência aerodinâmica usa `torque_y × omega_y`, preservando o sinal. As médias usam a fração final das amostras definida por `output.average_start_fraction`; TSR usa a magnitude da rotação. Não se integra energia usando o contador de iterações.

Para comparar com o PimpleFoam prescrito, use `mean_aero_drive_torque_N_m` no resumo. As parcelas de pressão e viscosidade também são projetadas no sentido da rotação. Use o resultado para comparação depois de conferir os resíduos e o torque no final da execução.

Em testes de malha, compare o torque de pressão, o torque viscoso e o `yPlusRotor`. Ao usar camadas, confira também quantas foram realmente geradas em `log.snappyHexMesh`. O número de células e o resultado de `checkMesh` são checagens geométricas.

Concluir o fluxo não significa convergir: consulte `converged` no resumo e os resíduos. Mesmo a convergência numérica não comprova independência de malha ou acordo experimental.

Os arquivos antigos de pós-processamento e deslocamento foram preservados em `config/reference/`; não fazem parte da execução MRF.

## Scripts

`run_serial.sh` e `run_mpi.sh` controlam o fluxo. `scripts/terminal_helpers.sh` cuida do terminal; `case_helpers.sh`, da preparação e malha; `run_helpers.sh`, do solver e resultados. `clean_runs.sh` apaga todo o histórico local de `runs/`.
