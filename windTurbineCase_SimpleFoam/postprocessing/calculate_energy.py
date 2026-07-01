import numpy as np
import os

# Parâmetros físicos
rho = 1.225      # kg/m³
U_inf = 3.3     # m/s
R = 0.35         # m
omega = 20.0      # rad/s

arquivo = "postProcessing/forcesRotor/0/moment.dat"
data = np.loadtxt(arquivo, comments="#")

time = data[:, 0]
My = data[:, 2]  # torque em torno do eixo Y

# Ignora metade inicial da simulação
inicio = int(0.5 * len(time))

My_medio = np.mean(My[inicio:])
torque_abs = abs(My_medio)

P_turbina = torque_abs * omega

A = np.pi * R**2
P_vento = 0.5 * rho * A * U_inf**3

Cp = P_turbina / P_vento

os.makedirs("results", exist_ok=True)
with open("results/energia.txt", "w") as f:
    f.write("RESULTADOS \n")
    f.write(f"Torque médio My: {My_medio:.6e} N.m\n")
    f.write(f"Torque médio absoluto: {torque_abs:.6e} N.m\n")
    f.write(f"Potência mecânica: {P_turbina:.6e} W\n")
    f.write(f"Potência disponível no vento: {P_vento:.6e} W\n")
    f.write(f"Coeficiente de potência Cp: {Cp:.6e}\n")