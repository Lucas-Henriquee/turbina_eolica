#!/usr/bin/env pvpython
"""Gera uma cena ParaView com hélice e linhas de corrente."""

import argparse
import time as clock
import xml.etree.ElementTree as ET
from pathlib import Path

from paraview.simple import (
    AnnotateTimeFilter,
    ColorBy,
    CreateLayout,
    CreateView,
    GetAnimationScene,
    GetColorTransferFunction,
    GetScalarBar,
    ExtractSurface,
    PVDReader,
    ResetSession,
    SaveData,
    Hide,
    MergeBlocks,
    OpenFOAMReader,
    Plane,
    Render,
    SaveScreenshot,
    SaveState,
    Show,
    StreamTracerWithCustomSource,
    Text,
)


def bake_geometry(output, times, scene, streamlines, rotor, frame_stride):
    geometry = output / "geometry"
    geometry.mkdir(parents=True, exist_ok=True)
    surface = ExtractSurface(Input=MergeBlocks(Input=rotor))
    selected = times[::frame_stride]
    if selected[-1] != times[-1]:
        selected.append(times[-1])
    manifests = {}
    for name in ["flow", "rotor"]:
        tree = ET.Element(
            "VTKFile", type="Collection", version="0.1", byte_order="LittleEndian"
        )
        manifests[name] = (tree, ET.SubElement(tree, "Collection"))
    started = clock.perf_counter()
    for index, time in enumerate(selected):
        scene.AnimationTime = time
        for name, source in [("flow", streamlines), ("rotor", surface)]:
            source.UpdatePipeline(time)
            filename = f"{name}_{index:04d}.vtp"
            SaveData(
                str(geometry / filename), proxy=source,
                DataMode="Binary", CompressorType="ZLib",
            )
            ET.SubElement(
                manifests[name][1], "DataSet", timestep=str(time),
                group="", part="0", file=f"geometry/{filename}",
            )
        if index % 10 == 0 or index == len(selected) - 1:
            print(f"[RUN] Geometry {index + 1}/{len(selected)}", flush=True)
    for name, (tree, _) in manifests.items():
        ET.ElementTree(tree).write(output / f"{name}.pvd", encoding="utf-8", xml_declaration=True)
    print(f"[OK] Geometry cached in {clock.perf_counter() - started:.1f} s", flush=True)


def create_view(
    case_file, output, requested_time, seed_resolution, bake, frame_stride, quality
):
    output.mkdir(parents=True, exist_ok=True)
    fluid = OpenFOAMReader(registrationName="Fluid velocity", FileName=str(case_file))
    fluid.MeshRegions = ["internalMesh"]
    fluid.CellArrays = ["U"]
    fluid.Createcelltopointfiltereddata = 1
    fluid.SkipZeroTime = 1
    times = list(fluid.TimestepValues)
    if not times:
        raise ValueError("No saved time steps found")
    time = min(times, key=lambda value: abs(value - requested_time))
    scene = GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()
    scene.AnimationTime = time
    fluid.UpdatePipeline(time)

    rotor = OpenFOAMReader(registrationName="Propeller surface", FileName=str(case_file))
    rotor.MeshRegions = ["patch/propeller"]
    rotor.CellArrays = ["U"]
    rotor.Createcelltopointfiltereddata = 1
    rotor.UpdatePipeline(time)

    volume = MergeBlocks(registrationName="Fluid volume", Input=fluid)
    volume.UpdatePipeline(time)
    # Distribui as sementes antes do rotor, no plano XZ.
    seeds = Plane(registrationName="Upstream seeds")
    seeds.Origin = [-0.30, -0.35, -0.30]
    seeds.Point1 = [0.30, -0.35, -0.30]
    seeds.Point2 = [-0.30, -0.35, 0.30]
    seeds.XResolution = seed_resolution
    seeds.YResolution = seed_resolution
    streamlines = StreamTracerWithCustomSource(
        registrationName="Velocity streamlines", Input=volume, SeedSource=seeds
    )
    streamlines.Vectors = ["POINTS", "U"]
    streamlines.IntegrationDirection = "BOTH"
    streamlines.MaximumStreamlineLength = 1.8 if quality == "detailed" else 1.4
    streamlines.InitialStepLength = 0.15
    streamlines.MaximumSteps = 3000 if quality == "detailed" else 1500
    streamlines.ComputeVorticity = 0
    streamlines.TerminalSpeed = 1e-5
    streamlines.UpdatePipeline(time)
    info = streamlines.GetDataInformation()
    if info.GetNumberOfPoints() == 0:
        raise ValueError("No streamlines generated; check velocity and seed positions")

    if bake:
        bake_geometry(output, times, scene, streamlines, rotor, frame_stride)
        ResetSession()
        fluid = None
        volume = None
        seeds = None
        streamlines = PVDReader(
            registrationName="Cached streamlines", FileName=str(output / "flow.pvd")
        )
        rotor = PVDReader(
            registrationName="Cached propeller", FileName=str(output / "rotor.pvd")
        )
        scene = GetAnimationScene()
        scene.UpdateAnimationUsingDataTimeSteps()
        time = min(
            list(streamlines.TimestepValues),
            key=lambda value: abs(value - requested_time),
        )
        scene.AnimationTime = time
        streamlines.UpdatePipeline(time)
        rotor.UpdatePipeline(time)
        if streamlines.GetDataInformation().GetNumberOfPoints() == 0:
            raise ValueError("Cached streamlines could not be loaded")

    view = CreateView("RenderView")
    layout = CreateLayout(name="Rotor flow")
    layout.AssignView(0, view)
    layout.SetSize(1280, 820)
    view.ViewTime = time
    view.Background = [0.22, 0.24, 0.27] if quality == "detailed" else [0.10, 0.12, 0.15]
    view.UseColorPaletteForBackground = 0
    view.OrientationAxesVisibility = 1
    view.CameraPosition = [0.20, -1.6, 0.14]
    view.CameraFocalPoint = [0, 0, 0]
    view.CameraViewUp = [0, 0, 1]
    view.CameraParallelProjection = 1
    view.CameraParallelScale = 0.35

    rotor_display = Show(rotor, view)
    rotor_display.Representation = "Surface"
    rotor_display.ColorArrayName = ["POINTS", ""]
    rotor_display.DiffuseColor = [0.15, 0.65, 0.64]
    rotor_display.AmbientColor = [0.15, 0.65, 0.64]
    rotor_display.Specular = 0.35
    rotor_display.SpecularPower = 35

    flow_display = Show(streamlines, view)
    flow_display.Representation = "Surface"
    flow_display.LineWidth = 1.2 if quality == "detailed" else 1.3
    flow_display.Opacity = 0.55 if quality == "detailed" else 1.0
    flow_display.Ambient = 1.0
    flow_display.Diffuse = 0.0
    ColorBy(flow_display, ("POINTS", "U", "Magnitude"))
    lookup = GetColorTransferFunction("U")
    lookup.ApplyPreset("Blue to Red Rainbow", True)
    lookup.RescaleTransferFunction(0, 8)
    flow_display.SetScalarBarVisibility(view, True)
    legend = GetScalarBar(lookup, view)
    legend.Title = "Velocity"
    legend.ComponentTitle = "m/s"
    legend.TitleFontSize = 13
    legend.LabelFontSize = 12
    legend.WindowLocation = "Lower Right Corner"
    legend.ScalarBarLength = 0.32
    legend.ScalarBarThickness = 12

    annotation = AnnotateTimeFilter(registrationName="Simulation time", Input=streamlines)
    annotation.Format = "Time: {time:.3f} s"
    time_display = Show(annotation, view)
    time_display.WindowLocation = "Upper Left Corner"
    time_display.FontSize = 20
    time_display.Color = [0.90, 0.93, 0.95]

    caption = Text(registrationName="Diagnostic caption")
    caption.Text = "DIAGNOSTIC VIEW | reconstructed CFD results"
    caption_display = Show(caption, view)
    caption_display.WindowLocation = "Lower Left Corner"
    caption_display.FontSize = 10
    caption_display.Color = [0.63, 0.69, 0.74]

    for source in [fluid, volume, seeds]:
        if source is not None:
            Hide(source, view)
    image = output / "flow_preview.png"
    state = output / "rotor_flow.pvsm"
    Render(view)
    # Reaplica a câmera após o enquadramento automático inicial.
    view.CameraPosition = [0.20, -1.6, 0.14]
    view.CameraFocalPoint = [0, 0, 0]
    view.CameraViewUp = [0, 0, 1]
    view.CameraParallelScale = 0.35
    Render(view)
    SaveState(str(state))
    SaveScreenshot(str(image), view, ImageResolution=[1280, 820])
    point_count = streamlines.GetDataInformation().GetNumberOfPoints()
    print(f"[OK] Time: {time:.6f} s; streamline points: {point_count}")
    print(f"[OK] Preview: {image}")
    print(f"[OK] ParaView state: {state}")


def main():
    parser = argparse.ArgumentParser(description="Build a ParaView rotor flow scene.")
    parser.add_argument("--case", type=Path, required=True, help="OpenFOAM .foam file")
    parser.add_argument("--time", type=float, default=1.8)
    parser.add_argument("--seed-resolution", type=int)
    parser.add_argument("--quality", choices=["preview", "detailed"], default="preview")
    parser.add_argument("--bake", action="store_true", help="Precompute geometry for lightweight playback")
    parser.add_argument("--frame-stride", type=int, help="Keep every Nth saved time when caching")
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] / "results/paraview",
    )
    args = parser.parse_args()
    if not args.case.is_file():
        parser.error("Case file not found")
    if args.seed_resolution is None:
        args.seed_resolution = 28 if args.quality == "detailed" else 12
    if args.frame_stride is None:
        args.frame_stride = 1 if args.quality == "detailed" else 2
    if args.seed_resolution < 2 or args.seed_resolution > 80:
        parser.error("Seed resolution must be between 2 and 80")
    if args.frame_stride < 1:
        parser.error("Frame stride must be positive")
    create_view(
        args.case.resolve(), args.output.resolve(), args.time,
        args.seed_resolution, args.bake, args.frame_stride, args.quality,
    )


if __name__ == "__main__":
    main()
