# PimpleFoam simulation

Caso transiente para OpenFOAM 2512: `pimpleFoam`, `kOmegaSST` e rotação livre no eixo Y. Geometria em metros; entrada de ar na direção +Y.

## Preparação

Os comandos partem desta pasta. Ative o ambiente Python da raiz e carregue o OpenFOAM:

```bash
source ../../.venv/bin/activate
source /usr/lib/openfoam/openfoam2512/etc/bashrc
python3 -m pip install -r ../../requirements.txt
```

MPI é necessário para execução paralela. Em uma execução exportada, use um ambiente Python próprio e instale com `python3 -m pip install -r requirements.txt`.

## Executar

| Comando | Ação |
| --- | --- |
| `./create_mesh.sh` | Gera e verifica a malha |
| `./run_serial.sh` | Gera a malha e executa em série |
| `./run_mpi.sh 6` | Gera a malha e executa com 6 processos |

Os scripts recusam uma nova execução se houver malha ou resultados na raiz. Para preservá-los e liberar a pasta:

```bash
python3 scripts/archive_case.py --status interrupted
```

`Ctrl+C` interrompe o solver e arquiva os resultados parciais. Não execute dois scripts ao mesmo tempo nesta pasta.

## Scripts

Auxiliares em `scripts/`: `case_helpers.sh` prepara o caso e a malha; `terminal_helpers.sh` registra status e duração; `run_helpers.sh` controla o solver e o arquivamento; `run_state.py` consulta os metadados.

## Configurar

Edite [config.yaml](config.yaml). Os dicionários em `0/`, `constant/` e `system/` cobertos por `config/templates/` são regenerados automaticamente.

| Seção | Parâmetros |
| --- | --- |
| `geometry` | STL, densidade do material e folgas do cilindro |
| `bench` | Ventilador, distância até o rotor e altura do eixo |
| `wind` | Perfil de velocidade e referência nominal |
| `mesh` | Domínio, células-base e refinamentos |
| `motion` | Integração do movimento, AMI e amortecimento |
| `time` | Duração, passo e intervalo de escrita |
| `parallel` | Processos e decomposição |
| `numerics` / `schemes` | Solvers e discretização |

Para trocar a hélice, coloque o STL em `constant/triSurface/` e ajuste `geometry.rotor_stl`. `surfaceInertia` calcula massa e inércia como sólido homogêneo; o preenchimento da impressão não é modelado.

Para validar a configuração e gerar os dicionários sem criar a malha:

```bash
python3 scripts/prepare_case.py
```

## Monitorar com watch

```bash
watch -n 2 python3 scripts/monitor_run.py
```

A barra usa o tempo simulado até `endTime`. O monitor mostra ETA aproximada, passo de tempo, Courant, RPM e resíduos finais de pressão e velocidade. Lê apenas o trecho recente do log, sem alterar o caso.

`ACTIVE` indica saída recente no log; `NO RECENT OUTPUT` indica ausência de atualização há 120 segundos. O monitor também distingue falha, interrupção e finalização. Ao arquivar, acompanha a execução mais recente em `runs/`.

Para outra pasta, acrescente `--case /path/to/case`. O limiar de atualização pode ser alterado com `--stale-seconds 300`.

A ETA cobre somente o solver. A barra não mede convergência nem inclui malha e pós-processamento.

## Terminal e logs

O terminal mostra status, duração das etapas, tempo total real (`HH:MM:SS`) e caminhos de saída. O total inclui preparação, malha, solver e pós-processamento. Durante a execução:

```bash
tail -f log.pimpleFoam
```

| Log | Conteúdo |
| --- | --- |
| `log.prepareCase` | Configuração, geometria e inércia |
| `log.surfaceCheck` / `log.surfaceInertia` | Integridade do STL e propriedades do sólido |
| `log.parallelSettings` / `log.mpiTest` | Configuração e inicialização MPI |
| `log.snappyHexMesh` | Refinamento e ajuste à superfície |
| `log.checkMesh` | Verificação padrão da malha |
| `log.pimpleFoam` | Passos, resíduos, Courant e movimento |

Ao arquivar, os logs passam para `runs/<run>/logs/`. O pós-processamento gera `log.calculate_energy`, `log.plot_results` e `log.summary` nessa pasta. Falhas mostram o caminho do log correspondente, sem despejar seu conteúdo no terminal.

## Inspecionar a malha

Após `./create_mesh.sh`:

```bash
checkMesh -constant -allGeometry -allTopology > log.checkMeshDetailed 2>&1
paraFoam -builtin
```

No ParaView, clique em **Apply**, selecione `propeller` em **Mesh Regions** e use **Surface With Edges**. Para ver o volume refinado, selecione `internalMesh` e aplique **Slice**.

Verifique células côncavas e pesos AMI na checagem ampliada. Um `Mesh OK` na checagem padrão não garante a qualidade dos resultados físicos.

## Resultados

Execuções concluídas ficam em `runs/testNNN_<data>/`; interrupções e falhas ficam em `runs/failedNNN_<data>/`. Cada execução preserva entradas, scripts e parâmetros próprios.

| Arquivo | Conteúdo |
| --- | --- |
| `results/timeseries.csv` | RPM, torque, potência, energia e coeficientes |
| `results/motion.csv` | Movimento do rotor |
| `results/summary.json` | Métricas numéricas |
| `results/energy_summary.txt` | Resumo da análise |
| `results/*_vs_time.png` | Gráficos |
| `config.txt` | Configuração efetiva, propriedades e resultados |
| `metadata/` | Geometria e parâmetros resolvidos |
| `<run>.foam` | Campos e malha para ParaView |

Resumo da última execução concluída:

```bash
python3 scripts/show_results.py
```

Para reprocessar uma execução, substitua `<run>` pelo nome da pasta:

```bash
python3 postprocessing/calculate_energy.py --case "runs/<run>"
python3 postprocessing/plot_results.py --case "runs/<run>"
```

## Limites do modelo

A entrada é um disco uniforme simplificado; velocidade e turbulência ainda precisam de medições. `Cp`, `Cq` e `TSR` usam a velocidade nominal da entrada, não uma medição local no rotor. O gerador é representado apenas por amortecimento viscoso.

Potência aerodinâmica: `My × omega_y`. RPM e torque têm sinal no eixo Y. O campo `omega` do OpenFOAM é turbulência; a rotação está nos CSVs. Energia é integrada por trapézios, incluindo a partida.

`clean_runs.sh` apaga todo o histórico de `runs/`.
