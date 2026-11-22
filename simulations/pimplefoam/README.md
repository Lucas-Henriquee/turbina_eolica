# PimpleFoam simulation

Caso transiente com `pimpleFoam`, `kOmegaSST` e rotação no eixo Y. Geometria em metros; entrada de ar na direção +Y.

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

### Partida livre

O `config.yaml` inicia com ar e rotor em repouso e roda por 9 s de tempo físico. A malha gerada no OpenFOAM 2512 tem 52.350 células. A entrada de 7,09 m/s produz 6,20 m/s no centro a 1 m no caso sem hélice. A partição `simple` com divisões `[2, 3, 1]` passou na checagem da AMI com seis processos.

O ensaio usa os parâmetros do piloto de 0,5 s no OpenFOAM 2412, com Courant máximo de 1,0, dois ciclos externos, duas correções de pressão e uma correção não ortogonal.

```bash
./run_mpi.sh 6
```

Para comparar com a bancada, consulte `motion.csv` e `free_torque_balance` no resumo da execução. No equilíbrio, a média de RPM permanece estável e o saldo de torque tende a zero. O `checkMesh` estendido ainda aponta problemas locais de qualidade.

### Rotação prescrita

Para o diagnóstico a 132 RPM, use `motion.prescribed_rpm: -132.0` e `motion.initial_rpm: 0.0`. Consulte `prescribed_torque_balance` em `results/summary.json`. O resumo usa até as três últimas voltas completas. Um saldo positivo indica que o modelo livre ainda aceleraria nesse ponto.

### Duração e escoamento inicial

Use um caso SimpleFoam concluído, com a mesma hélice, vento e rotação próxima. O PimpleFoam começa em `t = 0` com os campos do último tempo salvo no SimpleFoam e a rotação definida em `motion`.

```bash
./run_mpi.sh 6 --initial-case /caminho/para/o/caso-simplefoam
```

Para testar a partida livre, configure `motion.prescribed_rpm: null` e `motion.initial_rpm: 0.0`. Se o vento já estiver estabelecido antes de liberar o rotor, use `--initial-case` com um SimpleFoam executado com `rotation.angular_velocity: 0.0`. Para ligar o ventilador com ar e rotor em repouso, use `initial.velocity: [0, 0, 0]` e execute `./run_mpi.sh 6`. Use em `wind.profile` a subida medida do vento, quando disponível.

No prescrito a 132 RPM, 2 s permitem comparar três voltas completas após a primeira volta. No livre, use os 9 s configurados para acompanhar as médias de RPM e de saldo de torque nas últimas voltas.

Estenda o último ponto de `wind.profile` até `time.endTime`. Para o ensaio de 9 s, use `[[0.0, 7.09], [9.0, 7.09]]`.

## Scripts

Auxiliares em `scripts/`: `case_helpers.sh` prepara o caso e a malha; `terminal_helpers.sh` registra status e duração; `run_helpers.sh` controla o solver e o arquivamento; `run_state.py` consulta os metadados.

A geração separa os pontos da AMI com `mergeOrSplitBaffles -split -overwrite`, após `createBaffles`. Sem essa separação, a região fixa compartilha pontos com a rotativa e pode gerar volumes negativos durante a rotação.

Antes do solver, `check_mesh_motion.py` testa aproximadamente uma volta em cada sentido numa cópia temporária, a 16 rad/s, sem resolver o fluido. A execução MPI repete o teste com a mesma decomposição usada pelo solver. Erros de geometria, execução incompleta ou cobertura AMI insuficiente interrompem a execução. Consulte `log.meshMotion*` e `metadata/mesh_motion_check*.json`.

Na AMI, `motion.ami_min_cos_angle` e `motion.ami_max_normal_distance` limitam as faces candidatas por orientação e distância normal. O referencial de inércia mantém o eixo corporal Y alinhado ao eixo fixo. A convecção de `k` e `omega` usa `upwind` para reduzir valores negativos, com maior difusão numérica.

`mesh.cylinder_surface_level` refina só a superfície da AMI. Se omitido, usa `mesh.cylinder_level`, que também define o refinamento do interior do cilindro.

## Configurar

Edite [config.yaml](config.yaml). Os dicionários em `0/`, `constant/` e `system/` cobertos por `config/templates/` são regenerados automaticamente.

| Seção | Parâmetros |
| --- | --- |
| `geometry` | STL, densidade do material e folgas do cilindro |
| `bench` | Ventilador, distância até o rotor e altura do eixo |
| `wind` | Perfil de velocidade e referência nominal |
| `mesh` | Domínio, células-base e refinamentos |
| `motion` | Integração do movimento, AMI e amortecimento |
| `generator` | Motor de referência e resistências da carga elétrica |
| `time` | Duração, passo e intervalo de escrita |
| `parallel` | Processos e decomposição |
| `numerics` / `schemes` | Solvers e discretização |

Para trocar a hélice, coloque o STL em `constant/triSurface/` e ajuste `geometry.rotor_stl`. `surfaceInertia` calcula massa e inércia como sólido homogêneo; o preenchimento da impressão não é modelado.

`geometry.mass_correction_kg` e `geometry.shaft_inertia_correction_kg_m2` acrescentam correções efetivas à massa e à inércia sobre o eixo Y. A configuração atual estima três ímãs de neodímio Ø5 × 2 mm, furo Ø5 × 6 mm em PETG e distância de 7,5 mm ao eixo: +0,734 g e +4,13 × 10⁻⁸ kg·m². A inércia própria dos ímãs foi desprezada. O modelo mantém o centro de massa e não representa o desbalanceamento; é uma aproximação para o centro fixo e rotação restrita a Y deste caso. A inércia interna do gerador não está incluída. Zere as duas correções ao remover os ímãs ou trocar a geometria. `metadata/body_properties.json` registra massa geométrica, correções e propriedades efetivas; o volume continua sendo o do STL.

### Gerador

O caso usa o [Mabuchi RS-775VC-9013](https://product-en-origin.mabuchi-motor.co.jp/detail.html?id=220) como referência aproximada para o RS-775SF da bancada. Dados de catálogo: 18 V, 21.900 RPM e 2,74 A sem carga; 147 A em bloqueio. Não são medições do motor instalado.

O preparador estima `Rint = V / Istall` e `ke = (V - Rint × I0) / omega0`, adotando `kt = ke` em SI. Com carga de 10 Ω e shunt de 0,1 Ω, resulta `Rint ≈ 0,12245 Ω`, `ke = kt ≈ 0,00770244` e `be ≈ 5,80366e-6 N·m·s/rad`.

O modelo quase estacionário aplica `I = ke × omega / (Rint + Rcarga + Rshunt)` e `Tgerador = -kt × I`, equivalentes a um amortecimento `be = kt × ke / Rtotal`. A carga elétrica é uma restrição `generatorElectricalLoad`, separada de `shaftViscousDamping`. Não requer biblioteca C++ adicional. Os parâmetros derivados e a fonte ficam em `metadata/resolved_config.json`.

O coeficiente equivalente anterior de `1e-4` foi retirado. `generator.mechanical_loss_model: viscous_from_no_load` estima as perdas sem carga por `T0 = kt × I0` e `bm = T0 / omega0`. Isso representa atrito e outras perdas internas como um único amortecimento viscoso, aplicado em `generatorMechanicalLoss`. O modelo reproduz somente o ponto sem carga de 21.900 RPM; sua extrapolação para cerca de 115 RPM não foi validada e não representa atrito estático ou cogging. `none` desativa essa estimativa. Configurações antigas sem essa chave mantêm as perdas omitidas.

`motion.shaft_damping: 0` indica que não há outra perda adicional atribuída ao eixo. Não some novamente o mesmo atrito nesse campo. O caso não inclui indutância, queda não linear nas escovas ou inércia interna do gerador. É uma referência idealizada, não uma calibração; a RPM pode aumentar em relação ao caso anterior. Não use o torque de bloqueio como torque constante na turbina.

O pós-processamento separa potência aerodinâmica, potência elétrica estimada no resistor (`generator_load_power_W`), perdas internas, perdas no shunt e perdas mecânicas. `generator_no_load_loss_W` registra a parcela estimada do catálogo; `mechanical_loss_W` inclui essa parcela e a perda adicional do eixo. `shaft_dissipation_W` representa a soma das potências resistentes. Corrente e tensão estimadas seguem o sinal do eixo Y; compare seus módulos com a bancada. `generator_load_energy_J` integra apenas a potência entregue ao resistor. `generator.enabled: false` remove o modelo inteiro do gerador, incluindo as perdas estimadas; o amortecimento adicional do eixo permanece independente.

Testes: `python3 -m unittest discover -s tests -v`, a partir desta pasta. Incluem sinal do torque, balanço de potência, correções do rotor e compatibilidade com configurações antigas.

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
| `log.checkMeshMotion` / `log.meshMotion*` | Rotação de teste da malha e cobertura AMI |
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

## Visualizar o escoamento

Com o ParaView instalado, gere uma cena a partir do arquivo `.foam` da execução:

```bash
pvpython scripts/create_flow_view.py --case "runs/<run>/<run>.foam" --time 1.8
```

Abra `results/paraview/rotor_flow.pvsm` em **File → Load State** no ParaView. A cena inclui a hélice, linhas de corrente por velocidade e o tempo simulado. Use **Play** para percorrer os instantes salvos. `--output` permite escolher outra pasta de saída.

Para reproduzir sem recalcular as linhas a cada quadro, acrescente `--bake --output results/paraview_light`. A exportação usa um a cada dois instantes salvos; `--frame-stride 1` mantém todos. Os arquivos PVD/VTP ficam junto do estado e devem permanecer nessa pasta. `--quality detailed` aumenta a densidade das linhas e mantém todos os instantes salvos.

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

A entrada é um disco uniforme simplificado; velocidade e turbulência ainda precisam de medições. `Cp`, `Cq` e `TSR` usam a velocidade nominal da entrada, não uma medição local no rotor. O gerador usa parâmetros de motor semelhante; as perdas sem carga são aproximadas como viscosas e não foram caracterizadas na bancada.

Potência aerodinâmica: `My × omega_y`. RPM e torque têm sinal no eixo Y. O campo `omega` do OpenFOAM é turbulência; a rotação está nos CSVs. Energia é integrada por trapézios, incluindo a partida.

`clean_runs.sh` apaga todo o histórico de `runs/`.
