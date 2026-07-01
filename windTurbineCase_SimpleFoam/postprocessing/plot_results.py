import numpy as np
import matplotlib.pyplot as plt
import os

rho = 1.225
U_inf = 3.3
R = 0.35
omega = 20.0

moment_file = "postProcessing/forcesRotor/0/moment.dat"
force_file = "postProcessing/forcesRotor/0/force.dat"

moment = np.loadtxt(moment_file, comments="#")
force = np.loadtxt(force_file, comments="#")

t = moment[:, 0]
My = moment[:, 2]
Fy = force[:, 2]

torque = np.abs(My)
P_turbina = torque * omega

A = np.pi * R**2
P_vento = 0.5 * rho * A * U_inf**3
Cp = P_turbina / P_vento

os.makedirs("results", exist_ok=True)

plt.figure()
plt.plot(t, My)
plt.xlabel("Tempo (s)")
plt.ylabel("Torque My (N.m)")
plt.title("Torque no eixo da turbina")
plt.grid(True)
plt.savefig("results/torque_tempo.png", dpi=300)

plt.figure()
plt.plot(t, P_turbina)
plt.xlabel("Tempo (s)")
plt.ylabel("Potência mecânica (W)")
plt.title("Potência mecânica estimada")
plt.grid(True)
plt.savefig("results/potencia_tempo.png", dpi=300)

plt.figure()
plt.plot(t, Cp)
plt.xlabel("Tempo (s)")
plt.ylabel("Cp")
plt.title("Coeficiente de potência")
plt.grid(True)
plt.savefig("results/cp_tempo.png", dpi=300)

plt.figure()
plt.plot(t, Fy)
plt.xlabel("Tempo (s)")
plt.ylabel("Força axial Fy (N)")
plt.title("Força axial na hélice")
plt.grid(True)
plt.savefig("results/forca_axial_tempo.png", dpi=300)

print("Gráficos gerados:")
print("results/torque_tempo.png")
print("results/potencia_tempo.png")
print("results/cp_tempo.png")
print("results/forca_axial_tempo.png")
