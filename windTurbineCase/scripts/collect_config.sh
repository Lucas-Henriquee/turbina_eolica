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

get_first_number_from_vector() {
    echo "$1" | grep -oE "[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?" | head -1
}

get_vector_component() {
    local vector="$1"
    local index="$2"

    echo "$vector" \
        | grep -oE "[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?" \
        | awk -v idx="$index" 'NR==idx {print; exit}'
}

get_U_inf() {
    local U_vec
    U_vec="$(get_entry 0/U internalField)"

    local ux uy uz
    ux="$(get_vector_component "$U_vec" 1)"
    uy="$(get_vector_component "$U_vec" 2)"
    uz="$(get_vector_component "$U_vec" 3)"

    awk -v ux="${ux:-0}" -v uy="${uy:-0}" -v uz="${uz:-0}" \
        'BEGIN {printf "%.6f", sqrt(ux*ux + uy*uy + uz*uz)}'
}

get_nu() {
    local nu_entry
    nu_entry="$(get_entry constant/transportProperties nu)"
    get_first_number_from_vector "$nu_entry"
}

get_rho() {
    local rho_entry

    rho_entry="$(get_entry system/forces rhoInf)"
    if [ "$rho_entry" != "NA" ] && [ -n "$rho_entry" ]; then
        echo "$rho_entry"
        return
    fi

    rho_entry="$(get_entry system/forces rho)"
    if [ "$rho_entry" != "NA" ] && [ -n "$rho_entry" ]; then
        echo "$rho_entry"
        return
    fi

    echo "1.225"
}

run_surface_check() {
    local stl="constant/triSurface/propeller.stl"
    local log="log.surfaceCheck.propeller"

    if [ ! -f "$stl" ]; then
        return 1
    fi

    surfaceCheck "$stl" > "$log" 2>&1
}

get_rotor_radius_from_surfaceCheck() {
    local log="log.surfaceCheck.propeller"

    if [ ! -f "$log" ]; then
        run_surface_check || {
            echo "NA"
            return
        }
    fi

    awk '
    /Bounding Box/ {
        getline;
        gsub(/[()]/, "", $0);
        xmin=$1; ymin=$2; zmin=$3;

        getline;
        gsub(/[()]/, "", $0);
        xmax=$1; ymax=$2; zmax=$3;

        rx1=sqrt(xmin*xmin + zmin*zmin);
        rx2=sqrt(xmin*xmin + zmax*zmax);
        rx3=sqrt(xmax*xmax + zmin*zmin);
        rx4=sqrt(xmax*xmax + zmax*zmax);

        r=rx1;
        if (rx2>r) r=rx2;
        if (rx3>r) r=rx3;
        if (rx4>r) r=rx4;

        printf "%.6f", r;
        found=1;
        exit;
    }
    END {
        if (!found) print "NA";
    }' "$log"
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

    echo "========================================"
    echo "PHYSICAL SUMMARY"
    echo "========================================"

    rho="$(get_rho)"
    U_inf="$(get_U_inf)"
    nu_value="$(get_nu)"
    R_rotor="$(get_rotor_radius_from_surfaceCheck)"
    omega_value="$(get_entry constant/dynamicMeshDict solidBodyCoeffs.rotatingMotionCoeffs.omega)"

    if [ "$R_rotor" = "NA" ] || [ -z "$R_rotor" ]; then
        A_rotor="NA"
        RPM="NA"
        TSR="NA"
        Pwind="NA"
        Re_D="NA"
    else
        A_rotor=$(awk -v R="$R_rotor" 'BEGIN {printf "%.6f", 3.141592653589793*R*R}')
        RPM=$(awk -v w="$omega_value" 'BEGIN {printf "%.6f", w*60/(2*3.141592653589793)}')
        TSR=$(awk -v w="$omega_value" -v R="$R_rotor" -v U="$U_inf" 'BEGIN {if (U != 0) printf "%.6f", (w*R)/U; else print "NA"}')
        Pwind=$(awk -v rho="$rho" -v A="$A_rotor" -v U="$U_inf" 'BEGIN {printf "%.6f", 0.5*rho*A*U^3}')
        Re_D=$(awk -v U="$U_inf" -v R="$R_rotor" -v nu="$nu_value" 'BEGIN {if (nu != 0) printf "%.6f", U*(2*R)/nu; else print "NA"}')
    fi

    echo "rho                     = ${rho} kg/m3"
    echo "nu                      = ${nu_value} m2/s"
    echo "U_inf                   = ${U_inf} m/s"
    echo "Rotor radius from STL   = ${R_rotor} m"
    echo "Rotor diameter          = $(awk -v R="$R_rotor" 'BEGIN {if (R != "NA") printf "%.6f", 2*R; else print "NA"}') m"
    echo "Rotor area              = ${A_rotor} m2"
    echo "omega                   = ${omega_value} rad/s"
    echo "RPM                     = ${RPM}"
    echo "TSR                     = ${TSR}"
    echo "Re_D                    = ${Re_D}"
    echo "Available wind power    = ${Pwind} W"
    echo ""
    echo "Notes:"
    echo "- U_inf is computed from the magnitude of 0/U internalField."
    echo "- Rotor radius is estimated from propeller.stl assuming rotation around Y."
    echo "- TSR = omega * R / U_inf."
    echo "- Re_D = U_inf * D / nu, with D = 2R."
    echo "- Pwind = 0.5 * rho * A * U_inf^3."
    echo ""

    echo "========================================"
    echo "SURFACE CHECK - PROPELLER STL"
    echo "========================================"

    if [ -f log.surfaceCheck.propeller ]; then
        echo "surfaceCheck log: log.surfaceCheck.propeller"
        echo ""

        grep -E "Bounding Box|points|triangles|closed|connected|Number of regions|Surface" log.surfaceCheck.propeller || true
        echo ""

        echo "Complete surfaceCheck output:"
        cat log.surfaceCheck.propeller
        echo ""
    else
        echo "log.surfaceCheck.propeller not found."
        echo ""
    fi

    echo "========================================"
    echo "MESH SUMMARY"
    echo "========================================"

    if [ -f log.checkMesh ]; then
        echo "checkMesh log: log.checkMesh"
        echo ""

        echo "Mesh statistics:"
        awk '
            /points:/ {print}
            /faces:/ {print}
            /internal faces:/ {print}
            /cells:/ {print}
            /faces per cell:/ {print}
            /boundary patches:/ {print}
            /point zones:/ {print}
            /face zones:/ {print}
            /cell zones:/ {print}
        ' log.checkMesh
        echo ""

        echo "Cell types:"
        awk '
            /Overall number of cells of each type:/ {flag=1; print; next}
            /Checking topology/ {flag=0}
            flag {print}
        ' log.checkMesh
        echo ""

        echo "Geometry and quality:"
        grep -E "Overall domain bounding box|Max aspect ratio|Minimum face area|Maximum face area|Min volume|Max volume|Total volume|Mesh non-orthogonality|Max skewness|Mesh OK|Failed" log.checkMesh || true
        echo ""

        echo "Problem checks:"
        grep -E "non-orthogonality|skewness|concavity|tet quality|volume ratio|face twist|determinant|faces in error" log.checkMesh || true
        echo ""
    else
        echo "log.checkMesh not found."
        echo ""
    fi

    echo "========================================"
    echo "SNAPPY MESH SUMMARY"
    echo "========================================"

    if [ -f log.snappyHexMesh ]; then
        echo "snappyHexMesh log: log.snappyHexMesh"
        echo ""

        grep -E "Snapped mesh|cells:|faces:|points:|Cells per refinement level|Finished meshing|Finished meshing without any errors" log.snappyHexMesh || true
        echo ""
    else
        echo "log.snappyHexMesh not found."
        echo ""
    fi

    echo "========================================"
    echo "AMI / PATCH SUMMARY"
    echo "========================================"

    if [ -f constant/polyMesh/boundary ]; then
        echo "Boundary patches:"
        grep -E "^[[:space:]]*[A-Za-z0-9_]+$|type[[:space:]]" constant/polyMesh/boundary || true
        echo ""

        echo "AMI1:"
        grep -A12 "AMI1" constant/polyMesh/boundary || true
        echo ""

        echo "AMI2:"
        grep -A12 "AMI2" constant/polyMesh/boundary || true
        echo ""
    else
        echo "constant/polyMesh/boundary not found."
        echo ""
    fi
   
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
