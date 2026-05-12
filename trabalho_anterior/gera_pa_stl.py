#!/usr/bin/env python3
"""
gera_pa_stl.py — Gerador paramétrico de STL para pás de turbina eólica
=======================================================================
Sem dependências além de numpy.

Eixos compatíveis com OpenFOAM:
  • Pás se estendem radialmente no eixo +X  (de r=0 até SPAN)
  • Eixo de rotação da turbina: Y  (0 1 0)  passando pela ORIGEM
  • Hub centrado na origem → eixo de rotação passa pelo centro do hub ✓
  • Para N_BLADES > 1, as demais pás são rotacionadas em torno de Y

HUB_MODE = 'box':
  • Gera DOIS arquivos STL separados:
      helice.stl  — só as pás (de r=0, passando pelo interior do hub)
      hub.stl     — só o cubo subdividido
  • No snappyHexMeshDict ambos recebem patchInfo type=wall name=helice
    → snappy os une num único patch "helice"
  • No 6DOF, patches=(helice) → pás + hub giram juntos como corpo rígido ✓

HUB_MODE = 'none':
  • Gera só helice.stl, pás de SPAN_INNER até SPAN, sem hub

Perfis:  'flat_plate' | 'naca4'  (ex: '0012', '2412')
"""

import numpy as np
import struct
import os
import sys

# ╔══════════════════════════════════════════════════════════════╗
# ║              CONFIGURAÇÃO — AJUSTE AQUI                     ║
# ╚══════════════════════════════════════════════════════════════╝

N_BLADES    = 2

SPAN        = 1.0        # m — raio externo (ponta da pá)
SPAN_INNER  = 0.0        # m — raio interno (ignorado se HUB_MODE='box')
CHORD_ROOT  = 0.12       # m — corda na raiz
CHORD_TIP   = 0.06       # m — corda na ponta
TWIST_ROOT  = 30.0       # graus — ângulo de ataque (raiz / único se uniform)
TWIST_TIP   =  5.0       # graus — ângulo de ataque na ponta (só usado se linear)
TWIST_MODE  = 'uniform'  # 'uniform' = ângulo constante em toda a pá (PoC simples)
                         # 'linear'  = interpola TWIST_ROOT→TWIST_TIP após o hub

PROFILE         = 'flat_plate'  # 'flat_plate' | 'naca4'
THICKNESS_RATIO = 0.08          # espessura/corda  (só flat_plate)
NACA_CODE       = '0012'        # código 4 dígitos (só naca4)

HUB_MODE    = 'box'     # 'none' | 'box'
HUB_SIZE    = 0.06      # m — METADE do lado do cubo
                        #   lado total = 2*HUB_SIZE
                        #   sugestão: CHORD_ROOT * 0.5  →  0.06 para corda=0.12

#   Pás:   PoC→(10,8)  Padrão→(20,12)  Detalhado→(60,30)
N_SPAN  = 20
N_CHORD = 12

#   Hub:   mínimo→4  padrão→8  detalhado→16
#   tris_hub = 12 * N_HUB²   (4→192, 8→768, 16→3072)
N_HUB   = 8

OUTPUT_BLADES = 'helice.stl'   # pás
OUTPUT_HUB    = 'hub.stl'      # hub (só gerado se HUB_MODE='box')

# ╔══════════════════════════════════════════════════════════════╗
# ║              FIM DA CONFIGURAÇÃO                            ║
# ╚══════════════════════════════════════════════════════════════╝


# ── Perfis ────────────────────────────────────────────────────

def flat_plate_profile(n_chord):
    xc    = np.linspace(0.0, 1.0, n_chord)
    half  = THICKNESS_RATIO / 2.0
    upper = np.column_stack([xc,  np.full(n_chord,  half)])
    lower = np.column_stack([xc,  np.full(n_chord, -half)])
    return upper, lower


def naca4_profile(code, n_chord):
    if len(code) != 4 or not code.isdigit():
        raise ValueError(f"NACA inválido: '{code}'")
    m  = int(code[0]) / 100.0
    p  = int(code[1]) / 10.0
    t  = int(code[2:]) / 100.0
    beta = np.linspace(0, np.pi, n_chord)
    xc   = (1 - np.cos(beta)) / 2.0
    yt   = 5*t*(0.2969*np.sqrt(np.maximum(xc,0)) - 0.1260*xc
                - 0.3516*xc**2 + 0.2843*xc**3 - 0.1015*xc**4)
    if m == 0 or p == 0:
        yc = dyc = np.zeros_like(xc)
    else:
        yc  = np.where(xc<p, m/p**2*(2*p*xc-xc**2),
                       m/(1-p)**2*((1-2*p)+2*p*xc-xc**2))
        dyc = np.where(xc<p, 2*m/p**2*(p-xc),
                       2*m/(1-p)**2*(p-xc))
    th    = np.arctan(dyc)
    upper = np.column_stack([xc - yt*np.sin(th),  yc + yt*np.cos(th)])
    lower = np.column_stack([xc + yt*np.sin(th),  yc - yt*np.cos(th)])
    return upper, lower


def get_profile():
    if PROFILE == 'flat_plate':
        return flat_plate_profile(N_CHORD)
    elif PROFILE == 'naca4':
        return naca4_profile(NACA_CODE, N_CHORD)
    raise ValueError(f"PROFILE desconhecido: '{PROFILE}'")


# ── Pás ───────────────────────────────────────────────────────

def build_blade_verts(r_inner):
    upper, lower = get_profile()
    contour = np.vstack([upper, lower[::-1][1:-1]])
    nc  = contour.shape[0]
    rs  = np.linspace(r_inner, SPAN, N_SPAN + 1)
    L   = SPAN - r_inner
    out = np.zeros((N_SPAN + 1, nc, 3))
    # Twist começa DEPOIS do hub:
    #   r < hub_r  → twist = 0   (seção reta, encaixa limpa na face do cubo)
    #   r = hub_r  → twist = TWIST_ROOT  (início da região aerodinâmica)
    #   r = SPAN   → twist = TWIST_TIP
    hub_r = HUB_SIZE if HUB_MODE == 'box' else r_inner

    for i, r in enumerate(rs):
        t     = (r - r_inner) / L if L > 1e-12 else 0.0
        chord = CHORD_ROOT + t*(CHORD_TIP - CHORD_ROOT)

        # TWIST_MODE controla o comportamento ao longo do span:
        #   'uniform'  — ângulo constante = TWIST_ROOT em toda a pá (padrão/PoC)
        #   'linear'   — interpola TWIST_ROOT → TWIST_TIP a partir do hub
        if TWIST_MODE == 'uniform':
            twist = np.radians(TWIST_ROOT)
        else:  # 'linear'
            if r <= hub_r:
                twist = np.radians(TWIST_ROOT)
            else:
                twist_range = SPAN - hub_r
                t_twist = (r - hub_r) / twist_range if twist_range > 1e-12 else 1.0
                twist = np.radians(TWIST_ROOT + t_twist*(TWIST_TIP - TWIST_ROOT))

        # Dimensionaliza o perfil
        xc = contour[:,0] * chord
        yc = contour[:,1] * chord

        # Centraliza o centroide na origem ANTES do twist.
        xc -= xc.mean()
        yc -= yc.mean()

        # Aplica twist (rotação em torno do eixo radial X)
        ct, st = np.cos(twist), np.sin(twist)
        out[i,:,0] = r
        out[i,:,1] = xc*st + yc*ct
        out[i,:,2] = xc*ct - yc*st
    return out


def verts_to_tris(verts):
    ns, nc, _ = verts.shape
    tris = []
    for i in range(ns-1):
        for j in range(nc):
            j1 = (j+1) % nc
            p00,p10 = verts[i,j],  verts[i+1,j]
            p01,p11 = verts[i,j1], verts[i+1,j1]
            tris += [np.array([p00,p10,p11]), np.array([p00,p11,p01])]
    c0 = verts[0].mean(0)
    for j in range(nc):
        tris.append(np.array([c0, verts[0,(j+1)%nc], verts[0,j]]))
    c1 = verts[-1].mean(0)
    for j in range(nc):
        tris.append(np.array([c1, verts[-1,j], verts[-1,(j+1)%nc]]))
    return tris


def rot_y(pts, a):
    c, s = np.cos(a), np.sin(a)
    R = np.array([[c,0,s],[0,1,0],[-s,0,c]])
    return pts @ R.T


def build_blade_tris(r_inner):
    """Retorna todos os triângulos das N_BLADES pás."""
    blade_tris = verts_to_tris(build_blade_verts(r_inner))
    tris = []
    for b in range(N_BLADES):
        angle = b * 2*np.pi / N_BLADES
        for tri in blade_tris:
            tris.append(rot_y(tri, angle))
    return tris


# ── Hub subdividido ───────────────────────────────────────────

def build_hub_tris():
    """
    Cubo centrado em (0,0,0), lado = 2*HUB_SIZE.
    Cada face subdividida em N_HUB×N_HUB quads → 12*N_HUB² triângulos total.
    STL separado → snappy trata como superfície independente mas mesmo patch.
    """
    s, n = HUB_SIZE, N_HUB
    tris = []
    # (eixo_normal, sinal, eixo_u, eixo_v)
    face_defs = [
        (0, -1, 2, 1),   # -X
        (0, +1, 1, 2),   # +X
        (1, -1, 0, 2),   # -Y
        (1, +1, 2, 0),   # +Y
        (2, -1, 1, 0),   # -Z
        (2, +1, 0, 1),   # +Z
    ]
    us = np.linspace(-s, s, n+1)
    vs = np.linspace(-s, s, n+1)
    for ni, ns_sign, ui, vi in face_defs:
        for i in range(n):
            for j in range(n):
                corners = []
                for (u, v) in [(us[i],vs[j]),(us[i+1],vs[j]),
                               (us[i+1],vs[j+1]),(us[i],vs[j+1])]:
                    p = np.zeros(3)
                    p[ni] = ns_sign * s
                    p[ui] = u
                    p[vi] = v
                    corners.append(p)
                p00,p10,p11,p01 = corners
                tris.append(np.array([p00, p10, p11]))
                tris.append(np.array([p00, p11, p01]))
    return tris


# ── STL binário ───────────────────────────────────────────────

def normal(tri):
    v1, v2 = tri[1]-tri[0], tri[2]-tri[0]
    n = np.cross(v1, v2)
    d = np.linalg.norm(n)
    return n/d if d > 1e-14 else np.zeros(3)


def write_stl(tris, path):
    with open(path, 'wb') as f:
        f.write(b'\x00'*80)
        f.write(struct.pack('<I', len(tris)))
        for tri in tris:
            f.write(struct.pack('<3f', *normal(tri)))
            for v in tri:
                f.write(struct.pack('<3f', *v.astype(float)))
            f.write(struct.pack('<H', 0))
    return len(tris)


# ── Relatório ─────────────────────────────────────────────────

def report(n_blades, n_hub, r_inner):
    rho  = 1240.0
    cavg = (CHORD_ROOT+CHORD_TIP)/2
    L    = SPAN - r_inner
    A    = cavg**2*THICKNESS_RATIO if PROFILE=='flat_plate' else 0.6*cavg**2*(int(NACA_CODE[2:])/100)
    m1   = rho*A*L
    mall = m1*N_BLADES
    Ro,Ri = SPAN, r_inner
    Iy1  = m1*(Ro**3-Ri**3)/(3*(Ro-Ri)) if Ro>Ri else 0.0
    Iyb  = Iy1*N_BLADES

    if HUB_MODE == 'box':
        mh   = rho*(2*HUB_SIZE)**3
        Iyh  = mh*2*(2*HUB_SIZE)**2/12
        mall += mh
        Iy   = Iyb+Iyh
        hub_str = (f"\n  {OUTPUT_HUB:<18}: {n_hub} tris  "
                   f"(cubo lado={2*HUB_SIZE:.3f}m, N_HUB={N_HUB})")
        dyn_hub = f" + hub {mh:.4f} kg"
        dyn_ihu = f" + hub {Iyh:.5f}"
    else:
        Iy=Iyb; hub_str=""; dyn_hub=""; dyn_ihu=""

    print("\n" + "="*62)
    print(f"  Arquivos gerados:")
    print(f"  {OUTPUT_BLADES:<18}: {n_blades} tris  "
          f"({N_BLADES} pás, {PROFILE}, {N_SPAN}×{N_CHORD})" + hub_str)
    print(f"\n  Geometria:")
    print(f"  Raio       : {r_inner:.3f} → {SPAN:.3f} m")
    print(f"  Corda      : {CHORD_ROOT:.3f} (raiz) → {CHORD_TIP:.3f} (ponta) m")
    print(f"  Twist      : {TWIST_ROOT:.1f}° → {TWIST_TIP:.1f}°")
    print(f"\n  ── dynamicMeshDict ──")
    print(f"  patches         (helice);   ← pás + hub, mesmo patch")
    print(f"  origin          (0 0 0);    ← centro do hub = eixo de rotação ✓")
    print(f"  axis            (0 1 0);")
    print(f"\n  ── Inércia estimada (PLA ρ=1240 kg/m³) ──")
    print(f"  mass              ≈ {mall:.4f} kg  ({N_BLADES}×{m1:.4f}{dyn_hub})")
    com = f"({(r_inner+SPAN)/2:.3f} 0 0)" if N_BLADES==1 else "(0 0 0)"
    print(f"  centreOfMass      ≈ {com}")
    print(f"  momentOfInertia Y ≈ {Iy:.5f} kg·m²  (pás {Iyb:.5f}{dyn_ihu})")
    print(f"\n  ⚠  Estimativas analíticas — refine no FreeCAD se necessário.")
    print("="*62 + "\n")


# ── Main ──────────────────────────────────────────────────────

def main():
    r_inner = 0.0 if HUB_MODE == 'box' else SPAN_INNER

    print(f"Gerando pás → {OUTPUT_BLADES} ...")
    try:
        blade_tris = build_blade_tris(r_inner)
    except ValueError as e:
        print(f"ERRO: {e}"); sys.exit(1)
    n_b = write_stl(blade_tris, OUTPUT_BLADES)
    print(f"  {n_b} triângulos  ({os.path.getsize(OUTPUT_BLADES)/1024:.1f} kB)")

    n_h = 0
    if HUB_MODE == 'box':
        print(f"Gerando hub  → {OUTPUT_HUB} ...")
        hub_tris = build_hub_tris()
        n_h = write_stl(hub_tris, OUTPUT_HUB)
        print(f"  {n_h} triângulos  ({os.path.getsize(OUTPUT_HUB)/1024:.1f} kB)")

    report(n_b, n_h, r_inner)


if __name__ == '__main__':
    main()