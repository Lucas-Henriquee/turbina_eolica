#!/usr/bin/env bash

OUT="${1:-config.txt}"

get_entry() {
    local file="$1"
    local entry="$2"

    if [ -f "$file" ]; then
        foamDictionary "$file" -entry "$entry" -value 2>/dev/null || echo "NA"
    else
        echo "NA"
    fi
}

{
    echo "========================================"
    echo "EXECUTION CONFIGURATION"
    echo "========================================"
    echo "Date/time: $(date)"
    echo "Directory: $(pwd)"
    echo ""

    echo "========================================"
    echo "OPENFOAM"
    echo "========================================"
    echo "WM_PROJECT_VERSION=${WM_PROJECT_VERSION:-NA}"
    echo "WM_PROJECT_DIR=${WM_PROJECT_DIR:-NA}"
    echo ""

    echo "========================================"
    echo "system/controlDict"
    echo "========================================"
    echo "application     = $(get_entry system/controlDict application)"
    echo "startFrom       = $(get_entry system/controlDict startFrom)"
    echo "startTime       = $(get_entry system/controlDict startTime)"
    echo "stopAt          = $(get_entry system/controlDict stopAt)"
    echo "endTime         = $(get_entry system/controlDict endTime)"
    echo "deltaT          = $(get_entry system/controlDict deltaT)"
    echo "writeControl    = $(get_entry system/controlDict writeControl)"
    echo "writeInterval   = $(get_entry system/controlDict writeInterval)"
    echo "purgeWrite      = $(get_entry system/controlDict purgeWrite)"
    echo "adjustTimeStep  = $(get_entry system/controlDict adjustTimeStep)"
    echo "maxCo           = $(get_entry system/controlDict maxCo)"
    echo "maxDeltaT       = $(get_entry system/controlDict maxDeltaT)"
    echo "writeFormat     = $(get_entry system/controlDict writeFormat)"
    echo "writePrecision  = $(get_entry system/controlDict writePrecision)"
    echo "writeCompression= $(get_entry system/controlDict writeCompression)"
    echo "timeFormat      = $(get_entry system/controlDict timeFormat)"
    echo "timePrecision   = $(get_entry system/controlDict timePrecision)"
    echo "runTimeModifiable = $(get_entry system/controlDict runTimeModifiable)"
    echo ""

    echo "========================================"
    echo "constant/dynamicMeshDict"
    echo "========================================"
    echo "dynamicFvMesh = $(get_entry constant/dynamicMeshDict dynamicFvMesh)"
    echo "solver        = $(get_entry constant/dynamicMeshDict solver)"
    echo "cellZone      = $(get_entry constant/dynamicMeshDict solidBodyCoeffs.cellZone)"
    echo "motion        = $(get_entry constant/dynamicMeshDict solidBodyCoeffs.solidBodyMotionFunction)"
    echo "origin        = $(get_entry constant/dynamicMeshDict solidBodyCoeffs.rotatingMotionCoeffs.origin)"
    echo "axis          = $(get_entry constant/dynamicMeshDict solidBodyCoeffs.rotatingMotionCoeffs.axis)"
    echo "omega         = $(get_entry constant/dynamicMeshDict solidBodyCoeffs.rotatingMotionCoeffs.omega)"
    echo ""

    echo "========================================"
    echo "constant/turbulenceProperties"
    echo "========================================"
    echo "simulationType = $(get_entry constant/turbulenceProperties simulationType)"
    echo "RASModel       = $(get_entry constant/turbulenceProperties RAS.RASModel)"
    echo "turbulence     = $(get_entry constant/turbulenceProperties RAS.turbulence)"
    echo ""

    echo "========================================"
    echo "constant/transportProperties"
    echo "========================================"
    echo "nu = $(get_entry constant/transportProperties nu)"
    echo ""

    echo "========================================"
    echo "system/decomposeParDict"
    echo "========================================"
    echo "numberOfSubdomains = $(get_entry system/decomposeParDict numberOfSubdomains)"
    echo "method             = $(get_entry system/decomposeParDict method)"
    echo ""

    echo "========================================"
    echo "system/snappyHexMeshDict"
    echo "========================================"
    echo "castellatedMesh = $(get_entry system/snappyHexMeshDict castellatedMesh)"
    echo "snap            = $(get_entry system/snappyHexMeshDict snap)"
    echo "addLayers       = $(get_entry system/snappyHexMeshDict addLayers)"
    echo "maxLocalCells   = $(get_entry system/snappyHexMeshDict castellatedMeshControls.maxLocalCells)"
    echo "maxGlobalCells  = $(get_entry system/snappyHexMeshDict castellatedMeshControls.maxGlobalCells)"
    echo "locationInMesh  = $(get_entry system/snappyHexMeshDict castellatedMeshControls.locationInMesh)"
    echo ""

    echo "========================================"
    echo "Initial Fields"
    echo "========================================"
    echo "U internalField     = $(get_entry 0/U internalField)"
    echo "p internalField     = $(get_entry 0/p internalField)"
    echo "k internalField     = $(get_entry 0/k internalField)"
    echo "omega internalField = $(get_entry 0/omega internalField)"
    echo "nut internalField   = $(get_entry 0/nut internalField)"
    echo ""

    echo ""
    echo "========================================"
    echo "COMPLETE FILES USED IN THE EXECUTION"
    echo "========================================"

    for file in \
        system/controlDict \
        system/blockMeshDict \
        system/snappyHexMeshDict \
        system/createBafflesDict \
        system/decomposeParDict \
        system/fvSchemes \
        system/fvSolution \
        system/forces \
        constant/dynamicMeshDict \
        constant/transportProperties \
        constant/turbulenceProperties \
        0/U \
        0/p \
        0/k \
        0/omega \
        0/nut \
        0/pointDisplacement
    do
        echo ""
        echo "----------------------------------------"
        echo "$file"
        echo "----------------------------------------"
        if [ -f "$file" ]; then
            cat "$file"
        else
            echo "File not found."
        fi
    done

} > "$OUT"
