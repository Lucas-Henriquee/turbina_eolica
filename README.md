# Wind Turbine

![OpenFOAM 2512](https://img.shields.io/badge/OpenFOAM-2512-536b7a?style=flat-square)
![Node.js 22+](https://img.shields.io/badge/Node.js-22%2B-688a70?style=flat-square)
![ESP32](https://img.shields.io/badge/Firmware-ESP32-687483?style=flat-square)
![Em desenvolvimento](https://img.shields.io/badge/Status-em_desenvolvimento-9a865e?style=flat-square)

Estudo de uma turbina eólica de bancada com simulações transientes e estacionárias em OpenFOAM. A aquisição experimental usa ESP32, sensor Hall e INA219 para acompanhar rotação, tensão, corrente e potência elétrica em uma dashboard local, com histórico de ensaios e exportação em CSV.

![Geometria da hélice em rotação ilustrativa](docs/assets/rotor-preview.gif)

## Estrutura

| Pasta | Conteúdo |
| --- | --- |
| [simulations/pimplefoam](simulations/pimplefoam/README.md) | Simulações transientes com rotação livre ou prescrita |
| [simulations/simplefoam](simulations/simplefoam/README.md) | Simulação estacionária com rotação prescrita — MRF |
| [dashboard](dashboard/README.md) | Gráficos, aquisição USB, histórico e exportação CSV |
| [firmware](firmware/README.md) | ESP32, INA219, sensor Hall e LED de status e gravação |
| [docs](docs/README.md) | Animação da hélice e script de geração |
| [archive](archive/README.md) | Arquivos do trabalho anterior |

## Requisitos

| Componente | Dependências |
| --- | --- |
| Dashboard | Node.js 22+ e npm |
| Firmware | Python e PlatformIO, ou extensão PlatformIO no VS Code |
| Simulações | Linux, OpenFOAM 2512, MPI e dependências Python |

Para usar as simulações ou o PlatformIO, instale as dependências Python a partir da raiz:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

<details>
<summary>Windows PowerShell</summary>

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

</details>

`requirements.txt` reúne as dependências Python. Node.js, OpenFOAM e MPI são instalados separadamente; os pacotes JavaScript são instalados pelo npm.

## Dashboard

Execute da raiz:

```bash
cd dashboard
npm ci
npm start
```

Abra **[localhost:8765](http://127.0.0.1:8765)**. Encerre o servidor com <kbd>Ctrl</kbd> + <kbd>C</kbd>.

> [!TIP]
> Instale com `npm ci` apenas na primeira execução ou quando as dependências mudarem. No uso diário, execute `npm start`.

Selecione **USB · ESP32** para medir ou **Demo** para visualizar dados gerados. Informe o nome do ensaio antes de gravar; os CSVs ficam em `dashboard/data/` e aparecem no histórico lateral.

## Firmware

Com o ambiente Python ativo, execute da raiz:

```bash
pio run -d firmware
pio device list
```

Para gravar, substitua a porta pelo dispositivo identificado:

```bash
pio run -d firmware -t upload --upload-port /dev/ttyUSB0
```

> [!IMPORTANT]
> Desconecte a dashboard da porta USB e feche o Monitor Serial antes de gravar. Apenas uma aplicação pode usar a porta por vez.

O firmware permanece no ESP32 após a gravação. GPIOs e sensores estão definidos em [hardware_config.h](firmware/include/hardware_config.h).

## Simulações

Execute da raiz:

```bash
cd simulations/pimplefoam
source /usr/lib/openfoam/openfoam2512/etc/bashrc
./run_mpi.sh 6
```

Para o caso estacionário, use `simulations/simplefoam/`. Edite o `config.yaml` do caso antes de executar. Cada caso preserva seu histórico em `runs/`; os detalhes das etapas ficam nos logs.

No transiente, `motion.prescribed_rpm: null` calcula a rotação livre, enquanto um valor diferente de zero impõe a rotação em RPM com sinal no eixo Y. A configuração atual começa do repouso e usa 1 s como teste inicial; ajuste a duração e o perfil de vento para o ensaio desejado. No estacionário, a rotação é imposta por `rotation.angular_velocity`, em rad/s, e a malha permanece fixa.

A simulação calcula potência aerodinâmica e, com o modelo de gerador habilitado, estima a potência elétrica na carga. A bancada mede tensão e corrente para calcular a potência elétrica. O pós-processamento também aceita um ajuste elétrico com dados da bancada, separado do balanço usado pelo solver. A comparação automática entre os ensaios e as simulações ainda não foi implementada.

## Compatibilidade

A dashboard e as ferramentas do firmware têm suporte a Linux, Windows e macOS. Este projeto foi validado no Linux; outros sistemas podem exigir driver USB e permissão para a porta. Consulte os READMEs de [dashboard](dashboard/README.md) e [firmware](firmware/README.md).
