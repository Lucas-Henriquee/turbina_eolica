"""Leitura de STL e geração do cilindro."""

import re
import struct

import numpy as np

NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"


def format_foam_value(value):
    if isinstance(value, (list, tuple, np.ndarray)):
        return "(" + " ".join(format_foam_value(v) for v in value) + ")"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, np.number)):
        return f"{value:.12g}"
    return str(value)


def read_stl_vertices(path):
    data = path.read_bytes()
    if len(data) >= 84 and len(data) == 84 + 50 * struct.unpack_from("<I", data, 80)[0]:
        count = struct.unpack_from("<I", data, 80)[0]
        dtype = np.dtype(
            [("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")]
        )
        return (
            np.frombuffer(data, dtype=dtype, offset=84, count=count)["vertices"]
            .reshape(-1, 3)
            .astype(float)
        )
    values = re.findall(
        r"\bvertex\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s+(" + NUMBER + r")",
        data.decode("ascii"),
    )
    if not values:
        raise ValueError(f"STL has no vertices: {path}")
    return np.array(values, dtype=float)


def build_cylinder_mesh(radius, ymin, ymax, centre, segments):
    triangles = []
    angles = np.linspace(0, 2 * np.pi, segments + 1)
    bottom = np.array(
        [
            [centre[0] + radius * np.cos(a), ymin, centre[2] + radius * np.sin(a)]
            for a in angles
        ]
    )
    top = bottom.copy()
    top[:, 1] = ymax
    b = np.array([centre[0], ymin, centre[2]])
    t = np.array([centre[0], ymax, centre[2]])
    for i in range(segments):
        triangles.extend(
            [
                [bottom[i], top[i], top[i + 1]],
                [bottom[i], top[i + 1], bottom[i + 1]],
                [b, bottom[i], bottom[i + 1]],
                [t, top[i + 1], top[i]],
            ]
        )
    data = bytearray(
        b"Generated cylinder".ljust(80, b"\0") + struct.pack("<I", len(triangles))
    )
    for triangle in np.array(triangles):
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        normal /= np.linalg.norm(normal)
        data.extend(struct.pack("<12fH", *normal, *triangle.flatten(), 0))
    return bytes(data)
