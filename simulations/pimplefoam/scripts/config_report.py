#!/usr/bin/env python3
"""Gera o relatório da execução."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]


def write_report(case, output=None):
    case = Path(case).resolve()
    output = Path(output) if output else case / "config.txt"
    if not output.is_absolute():
        output = case / output
    resolved = case / "metadata/resolved_config.json"
    metadata = json.loads(resolved.read_text()) if resolved.exists() else None
    status_file = case / "run_status.json"
    status = (
        json.loads(status_file.read_text())
        if status_file.exists()
        else {"simulation": "prepared", "postprocessing": "not_run"}
    )
    lines = [
        "Configuração e resultados da turbina",
        f'Gerado em: {datetime.now().astimezone().isoformat(timespec="seconds")}',
        f"Caso: {case}",
        f'Simulação: {status["simulation"]}',
        f'Pós-processamento: {status["postprocessing"]}',
        "",
    ]
    if metadata:
        config, body = metadata["config"], metadata["body"]
        lines += [
            "Propriedades da hélice",
            f'OpenFOAM: {metadata.get("openfoam_version","não registrado")}',
            f'Processos efetivos: {metadata["processes"]}',
            f'Hélice: {config["geometry"]["rotor_stl"]}',
            f'Densidade do material: {body["density"]:.12g} kg/m³',
            f'Massa: {body["mass"]:.12g} kg',
            f'Correção de massa: {body.get("mass_correction_kg", 0):.12g} kg',
            f'Correção de inércia no eixo Y: {body.get("shaft_inertia_correction_kg_m2", 0):.12g} kg.m²',
            f'Volume sólido: {body["volume"]:.12g} m³',
            f'Área superficial: {body["surface_area"]:.12g} m²',
            f'Raio máximo: {body["radius"]:.12g} m',
            f'Área varrida: {body["swept_area"]:.12g} m²',
            f'Centro de massa: {body["centreOfMass"]} m',
            f'Momentos principais: {body["momentOfInertia"]} kg.m²',
            f'Orientação principal: {body["orientation"]}',
            f'SHA256 da hélice: {body["rotor_sha256"]}',
            f'SHA256 do YAML usado: {metadata.get("config_sha256","não registrado")}',
            "",
        ]
        bench = config.get("bench")
        generator = metadata.get("generator", {})
        if generator.get("enabled"):
            lines += [
                "Gerador aproximado",
                f'Referência: {generator["reference_model"]}',
                f'Fonte: {generator["source_url"]}',
                f'Constante ke = kt (SI): {generator["back_emf_constant_V_s_rad"]:.8g}',
                f'Resistência interna estimada: {generator["internal_resistance_ohm"]:.8g} ohm',
                f'Amortecimento elétrico: {generator["electrical_damping_N_m_s_rad"]:.8g} N.m.s/rad',
                f'Amortecimento do gerador sem carga: {generator.get("mechanical_damping_N_m_s_rad", 0):.8g} N.m.s/rad',
                f'Amortecimento mecânico separado: {config["motion"]["shaft_damping"]:.8g} N.m.s/rad',
                "Modelo não calibrado; perdas em baixa rotação e inércia do gerador não caracterizadas.",
                "",
            ]
        if bench:
            lo, hi = config["mesh"]["bounds"]
            lines += [
                "Bancada e hipóteses",
                f'PETG: {body["density"]:.8g} kg/m³; sólido homogêneo maciço.',
                f'Massa calculada: {body["mass"]*1000:.6g} g; conferir com a peça impressa.',
                f'Diâmetro varrido: {2*body["radius"]:.8g} m',
                f'Altura do eixo: {bench["axis_height"]:.8g} m',
                f'Folga mínima rotor/chão: {bench["axis_height"]-body["radius"]:.8g} m',
                f'Disco simplificado do ventilador: {bench["fan_diameter"]:.8g} m de diâmetro',
                f'Distância entrada/eixo: {bench["fan_distance"]:.8g} m',
                f"Caixa X/Y/Z: {[round(b-a, 8) for a,b in zip(lo,hi)]} m",
                f'Limites do cilindro: {body.get("cylinder_bounds", "consultar STL")} m',
                "Velocidade prescrita no disco; confirmar experimentalmente o perfil no rotor.",
                "Cp/Cq/TSR usam a velocidade nominal do disco e a área varrida do rotor.",
                "Carga do eixo: modelo elétrico resistivo e perdas mecânicas separadas."
                if generator.get("enabled") else
                "Carga do eixo: amortecimento equivalente; gerador elétrico não modelado.",
                "O modelo não resolve o ventilador, a grade nem o suporte da bancada.",
                "",
            ]
        original = case / "config.yaml"
        if (
            original.exists()
            and metadata.get("config_sha256")
            and hashlib.sha256(original.read_bytes()).hexdigest()
            != metadata["config_sha256"]
        ):
            lines += [
                "AVISO: config.yaml foi alterado após a preparação; os valores abaixo são da configuração usada.",
                "",
            ]
        lines += [
            "Parâmetros usados",
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True).rstrip(),
            "",
        ]
    else:
        lines += ["Configuração de execução ausente; propriedades não disponíveis.", ""]
        if (case / "config.yaml").exists():
            lines += [
                "YAML DISPONÍVEL (não confirmado como executado)",
                (case / "config.yaml").read_text().rstrip(),
                "",
            ]
    log_dir = case / "logs" if (case / "logs").is_dir() else case
    check = log_dir / "log.checkMesh"
    if check.exists():
        lines += ["Qualidade da malha"]
        lines += [
            line.strip()
            for line in check.read_text(errors="replace").splitlines()
            if re.search(
                r"points:|faces:|cells:|non-orthogonality|Max skewness|Mesh OK|Failed",
                line,
            )
        ]
        lines += [""]
    summary = case / "results/summary.json"
    if summary.exists():
        lines += [
            "Resultados",
            json.dumps(json.loads(summary.read_text()), indent=2, ensure_ascii=False),
            "",
        ]
    lines += ["Arquivos OpenFOAM (SHA256)"]
    paths = sorted((case / "system").glob("*")) + sorted((case / "0").glob("*"))
    paths += [
        case / "constant" / name
        for name in [
            "dynamicMeshDict",
            "transportProperties",
            "turbulenceProperties",
            "inletVelocityProfile.dat",
        ]
    ]
    for path in paths:
        if path.is_file():
            lines.append(
                f"{path.relative_to(case)}: {hashlib.sha256(path.read_bytes()).hexdigest()}"
            )
    lines += [
        "",
        "Arquivos de saída",
        "results/motion.csv: velocidade linear e angular por passo; results/timeseries.csv: RPM, torque, potência e energia.",
        "results/*.png: gráficos; logs/: logs; arquivo .foam: ParaView.",
        "A rotação vem do log sixDoF ou do RPM prescrito; o campo omega é turbulência.",
        "Potência aerodinâmica não é potência elétrica.",
    ]
    temp = output.with_name(output.name + ".tmp")
    temp.write_text("\n".join(lines) + "\n")
    temp.replace(output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write the case configuration report.")
    parser.add_argument("output", nargs="?", default="config.txt")
    parser.add_argument("--case", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        write_report(args.case, args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"[FAIL] Configuration report: {error}\n")
