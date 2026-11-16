"""Gera a animação ilustrativa da hélice para o README."""

from pathlib import Path
import sys
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "simulations/simplefoam/scripts"))
from geometry import read_stl_vertices

vertices = read_stl_vertices(
    root / "simulations/pimplefoam/constant/triSurface/propeller_test.stl"
).reshape(-1, 3, 3)
vertices[:, :, 1] -= 0.015
fig = plt.figure(figsize=(8, 3), dpi=100, facecolor="#111315")
fig.text(0.055, 0.61, "Wind Turbine", fontsize=26, color="#e4e7e8", weight="medium")
fig.text(
    0.058, 0.48, "OPENFOAM  /  ESP32", fontsize=9, color="#9aaa9f", family="monospace"
)
fig.text(
    0.058, 0.20, "STL geometry · illustrative airflow", fontsize=8, color="#7e8b93"
)
# Traços decorativos indicam o movimento do vento.
wind_lines = []
for row in range(9):
    for column in range(3):
        line = Line2D(
            [],
            [],
            transform=fig.transFigure,
            color="#648390",
            alpha=0.35,
            linewidth=0.8,
            zorder=0.2,
        )
        fig.add_artist(line)
        wind_lines.append((line, row, column))
ax = fig.add_axes([0.48, -0.12, 0.55, 1.2], projection="3d", facecolor="none")
ax.set(xlim=(-0.25, 0.25), ylim=(-0.25, 0.25), zlim=(-0.25, 0.25))
ax.set_box_aspect((1, 1, 1))
ax.set_proj_type("ortho")
ax.view_init(elev=15, azim=-70)
ax.set_axis_off()
mesh = Poly3DCollection(
    vertices, linewidths=0.12, edgecolors="#719282", facecolors="#a5c9b2"
)
ax.add_collection3d(mesh)


def frame(i):
    for line, row, column in wind_lines:
        phase = (column / 3 + i / 30 + row * 0.11) % 1
        x = 0.48 + phase * 0.48
        y = 0.18 + row * 0.079
        length = 0.025 + 0.012 * ((row + column) % 3)
        line.set_data([x, min(0.98, x + length)], [y, y])
    angle = i * 2 * np.pi / 30
    rotation = np.array(
        [
            [np.cos(angle), 0, np.sin(angle)],
            [0, 1, 0],
            [-np.sin(angle), 0, np.cos(angle)],
        ]
    )
    rotated = vertices @ rotation.T
    mesh.set_verts(rotated)
    normals = np.cross(rotated[:, 1] - rotated[:, 0], rotated[:, 2] - rotated[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    intensity = 0.55 + 0.45 * np.abs(normals @ np.array([0.3, -0.8, 0.5]))
    mesh.set_facecolors(
        np.clip(np.array([0.65, 0.79, 0.70])[None, :] * intensity[:, None], 0, 1)
    )
    return (mesh,)


FuncAnimation(fig, frame, frames=30, interval=80, blit=False).save(
    root / "docs/assets/rotor-preview.gif", writer=PillowWriter(fps=12)
)
plt.close(fig)
print("Created docs/assets/rotor-preview.gif")
