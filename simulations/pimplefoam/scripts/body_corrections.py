"""Aplica correções efetivas para rotação restrita ao eixo Y."""

import numpy as np


def apply_body_corrections(body, geometry):
    mass_delta = float(geometry.get("mass_correction_kg", 0.0))
    inertia_delta = float(geometry.get("shaft_inertia_correction_kg_m2", 0.0))
    geometry_mass = body["mass"]
    mass = geometry_mass + mass_delta
    if not np.isfinite([mass_delta, inertia_delta, mass]).all() or mass <= 0:
        raise ValueError("Body corrections require finite values and positive total mass.")

    corrected = dict(body)
    corrected.update(
        geometry_mass=geometry_mass,
        mass=mass,
        mass_correction_kg=mass_delta,
        shaft_inertia_correction_kg_m2=inertia_delta,
        mass_model="homogeneous_solid",
    )
    if mass_delta == 0 and inertia_delta == 0:
        return corrected

    # Mantém o centro de massa; corrige somente a inércia efetiva no eixo fixo.
    orientation = np.array(body["orientation"]).reshape(3, 3)
    tensor = orientation @ np.diag(body["momentOfInertia"]) @ orientation.T
    offset = np.array(body["centreOfMass"]) - geometry["rotation_centre"]
    tensor[1, 1] += inertia_delta - mass_delta * (offset[0]**2 + offset[2]**2)
    moments, axes = np.linalg.eigh(tensor)
    if np.min(moments) <= 0:
        raise ValueError("Corrected inertia must be positive definite.")
    # Preserva o referencial anterior quando os eixos só mudam de sinal.
    for column in range(3):
        if np.dot(axes[:, column], orientation[:, column]) < 0:
            axes[:, column] *= -1
    if np.linalg.det(axes) < 0:
        axes[:, 0] *= -1
    corrected.update(
        momentOfInertia=moments.tolist(),
        orientation=axes.ravel().tolist(),
        mass_model="homogeneous_solid_with_effective_shaft_corrections",
    )
    return corrected
