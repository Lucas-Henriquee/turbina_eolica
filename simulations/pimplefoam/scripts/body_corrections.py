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
    # O eixo corporal Y deve coincidir com o eixo fixo da restrição sixDoF.
    orientation = np.array(body["orientation"]).reshape(3, 3)
    tensor = orientation @ np.diag(body["momentOfInertia"]) @ orientation.T
    offset = np.array(body["centreOfMass"]) - geometry["rotation_centre"]
    tensor[1, 1] += inertia_delta - mass_delta * (offset[0]**2 + offset[2]**2)
    # Para 1DOF, despreza XY/YZ e diagonaliza somente o plano transversal XZ.
    transverse_moments, transverse_axes = np.linalg.eigh(tensor[np.ix_([0, 2], [0, 2])])
    x_axis = np.array([transverse_axes[0, 0], 0.0, transverse_axes[1, 0]])
    if np.dot(x_axis, orientation[:, 0]) < 0:
        x_axis *= -1
    y_axis = np.array([0.0, 1.0, 0.0])
    axes = np.column_stack([x_axis, y_axis, np.cross(x_axis, y_axis)])
    moments = np.array([transverse_moments[0], tensor[1, 1], transverse_moments[1]])
    if np.min(moments) <= 0:
        raise ValueError("Corrected inertia must be positive definite.")
    corrected.update(
        momentOfInertia=moments.tolist(),
        orientation=axes.ravel().tolist(),
        mass_model=("homogeneous_solid_with_effective_shaft_corrections"
                    if mass_delta != 0 or inertia_delta != 0 else "homogeneous_solid"),
        inertia_model="axis_y_constrained",
        neglected_products_xy_yz_kg_m2=[float(tensor[0, 1]), float(tensor[1, 2])],
    )
    return corrected
