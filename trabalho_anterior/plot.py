import numpy as np
import matplotlib.pyplot as plt
import glob
import os

base_dir = "postProcessing/monitoramento"
files = sorted(glob.glob(os.path.join(base_dir, "*", "coefficient*.dat")))

data_list = []
for f in files:
    try:
        d = np.loadtxt(f, comments="#")
        data_list.append(d)
        print(f"Lido: {f}, shape={d.shape}")
    except Exception as e:
        print(f"Pulando {f}: {e}")

data = np.vstack(data_list)

idx_time   = 0
idx_Cd     = 1
idx_Cl     = 4
idx_CmYaw  = 8

t      = data[:, idx_time]
Cd_raw = data[:, idx_Cd]
Cl_raw = data[:, idx_Cl]
Cm_raw = data[:, idx_CmYaw]

# ---------- filtro de sanidade ----------
# mantemos só pontos em que todos os coeficientes estão "normais"
mask_valid = (np.abs(Cd_raw) < 10) & (np.abs(Cl_raw) < 10) & (np.abs(Cm_raw) < 10)

t   = t[mask_valid]
Cd  = Cd_raw[mask_valid]
Cl  = Cl_raw[mask_valid]
CmYaw = Cm_raw[mask_valid]

print(f"N pontos totais: {len(Cd_raw)}")
print(f"N pontos válidos: {len(Cd)}")
print("Cd min/max (filtrado):", Cd.min(), Cd.max())
print("Cl min/max (filtrado):", Cl.min(), Cl.max())
print("CmYaw min/max (filtrado):", CmYaw.min(), CmYaw.max())

# Se quiser considerar só a metade final dos válidos como "regime"
t_steady_start = t.min() + 0.5*(t.max() - t.min())
mask_steady = t >= t_steady_start

print(f"Cd médio (regime)    = {Cd[mask_steady].mean():.4e}")
print(f"Cl médio (regime)    = {Cl[mask_steady].mean():.4e}")
print(f"CmYaw médio (regime) = {CmYaw[mask_steady].mean():.4e}")

# ---------- gráficos ----------
plt.figure()
plt.plot(t, Cd)
plt.xlabel("Tempo [s]")
plt.ylabel("Cd")
plt.grid(True)
plt.tight_layout()
plt.savefig("Cd_vs_t.png", dpi=300)

plt.figure()
plt.plot(t, Cl)
plt.xlabel("Tempo [s]")
plt.ylabel("Cl")
plt.grid(True)
plt.tight_layout()
plt.savefig("Cl_vs_t.png", dpi=300)

plt.figure()
plt.plot(t, CmYaw)
plt.xlabel("Tempo [s]")
plt.ylabel("CmYaw")
plt.grid(True)
plt.tight_layout()
plt.savefig("CmYaw_vs_t.png", dpi=300)

plt.show()
