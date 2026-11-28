# Documentação do projeto

## Animação da hélice

`assets/rotor-preview.gif` usa a geometria de `propeller_test.stl`, com rotação e vento ilustrativos. Para regenerar, execute da raiz:

```bash
python3 docs/generate_rotor_preview.py
```

## Consolidação para revisão

A branch `feature/project-consolidation` reúne as alterações locais que estavam sobre `feature/prescribed-rotor-speed` e incorpora a referência local de `origin/main` em `e4a9ff3`. A seleção foi feita pelo conteúdo dos arquivos, sem juntar automaticamente todas as branches de testes.

| Incluído | Uso |
| --- | --- |
| Dashboard em mW e mJ | Facilita a leitura de potência e energia; os CSVs continuam em W e J |
| LED do ESP32 | Sinais de inicialização, Hall, gravação e perda dos comandos |
| Material padrão PETG | Identificação dos novos ensaios; os metadados antigos são preservados |
| Rotação livre e prescrita | Configuração da partida, balanço de torques e verificação do movimento da malha |
| Bancada comum aos casos PIMPLE e SIMPLE | Geometria, entrada circular, chão e parâmetros de malha compartilhados |
| Ajuste elétrico opcional | Estimativas no pós-processamento, sem mudar o torque resistente do solver |
| Visualização no ParaView | Estado e exportação de geometria para acompanhar o escoamento |
| Testes e entradas geradas | Verificações do código e dicionários correspondentes aos templates e YAML |

As configurações de testes longos de 12 ou 25 s e o diagnóstico antigo a 115 RPM não substituem automaticamente o caso padrão. O PIMPLE atual é um teste inicial de 1 s com rotação livre; a documentação explica como mudar duração e rotação. O amortecimento adicional de teste `2.75e-4` permanece fora da configuração padrão, pois não foi calibrado em bancada.

Execuções interrompidas, execuções com falha, malhas geradas, resultados, medições locais, caches e arquivos de compilação continuam fora dos commits, conforme o `.gitignore`. Os arquivos locais e as branches de origem são preservados.

No merge com `origin/main`, foi mantido o `snappyHexMeshDict` gerado pelos templates e pelo YAML atuais. A geometria `propeller_simple.stl`, adicionada no trabalho anterior, foi guardada em `archive/previous_work/constant/triSurface/old/`, sem substituir a hélice `propeller_test.stl` dos casos atuais. A atualização de `propeller_new.stl` vinda de `main` também foi preservada.

As alterações de malha e os parâmetros numéricos são entradas de desenvolvimento, não novos resultados validados para o relatório. Na revisão, ainda é necessário identificar as execuções finais, conferir a convergência do MRF, a qualidade da malha e os dados usados no ajuste elétrico. A referência de 52.350 células não deve ser atribuída a uma nova execução sem conferir seu log.

### Verificações do código

Da raiz do repositório:

```bash
python3 -m unittest discover -s simulations/pimplefoam/tests -v
node --test dashboard/tests/measurements.test.js
g++ -std=c++11 -Wall -Wextra -Werror -Ifirmware/include firmware/tests/hall_pulse_filter_test.cpp -o /tmp/hall-pulse-filter-test
/tmp/hall-pulse-filter-test
```

Os testes verificam o código; as verificações físicas dependem das execuções e dos ensaios escolhidos para comparação.

Na consolidação, passaram os 15 testes Python, o teste da dashboard e o teste C++ do filtro Hall. O firmware também compilou para `esp32dev`. Em uma cópia temporária, os dois preparadores OpenFOAM geraram os mesmos dicionários versionados. Foram conferidas a sintaxe dos scripts e a abertura da ajuda do utilitário ParaView. Essas verificações não incluíram novas simulações completas nem gravação na placa.
