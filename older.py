import streamlit as st

st.set_page_config(page_title="Powder XRD and (P)RDF Calculator for Crystal Structures (CIF, POSCAR, XYZ, ...)")

import numpy as np
import matplotlib.pyplot as plt
from ase.io import read, write
from matminer.featurizers.structure import PartialRadialDistributionFunction
from pymatgen.io.ase import AseAtomsAdaptor
from pymatgen.analysis.diffraction.xrd import XRDCalculator
from collections import defaultdict
from itertools import combinations
import streamlit.components.v1 as components
import py3Dmol
from io import StringIO

# Inject custom CSS for buttons.
st.markdown(
    """
    <style>
    div.stButton > button {
        background-color: #0099ff;
        color: white;
        font-size: 16px;
        font-weight: bold;
        padding: 0.5em 1em;
        border: none;
        border-radius: 5px;
        height: 3em;
        width: 100%;
    }
    /* Override active and focus states to keep the text white */
    div.stButton > button:active,
    div.stButton > button:focus {
        background-color: #0099ff !important;
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

components.html(
    """
    <head>
        <meta name="description" content="Online calculator of Powder XRD Pattern, Partial Radial Distribution Function (PRDF), and Global RDF for Crystal Structures (CIF, POSCAR, XYZ, ...)">
    </head>
    """,
    height=0,
)

st.title(
    "Powder XRD Pattern, Partial Radial Distribution Function (PRDF), and Global RDF Calculator for Crystal Structures (CIF, POSCAR, XYZ, ...)")
st.divider()

# --- File Upload ---
uploaded_files = st.file_uploader(
    "Upload Structure Files (CIF, POSCAR, XYZ, etc.)",
    type=None,
    accept_multiple_files=True
)
if uploaded_files:
    st.write(f"📄 **{len(uploaded_files)} file(s) uploaded.**")
else:
    st.warning("📌 Please upload at least one structure file. [📺 Quick tutorial here](https://youtu.be/-zjuqwXT2-k)")
st.warning(
    "💡 You can find crystal structures in CIF format at: [📖 Crystallography Open Database (COD)](https://www.crystallography.net/cod/)")
st.info(
    "ℹ️ Upload structure files (e.g., CIF, POSCAR, XYZ format), and this tool will calculate either the "
    "Partial Radial Distribution Function (PRDF) for each element combination, as well as the Global RDF, or the XRD powder diffraction pattern. "
    "If multiple files are uploaded, the PRDF will be averaged for corresponding element combinations across the structures. For XRD patterns, diffraction data from multiple structures can be combined into a single figure. "
    "Below, you can change the settings for XRD calculation or PRDF."
)

# --- Detect Atomic Species ---
if uploaded_files:
    species_set = set()
    for file in uploaded_files:
        with open(file.name, "wb") as f:
            f.write(file.getbuffer())
        structure = read(file.name)
        for atom in structure:
            species_set.add(atom.symbol)
    species_list = sorted(species_set)
    st.subheader("📊 Detected Atomic Species")
    st.write(", ".join(species_list))
else:
    species_list = []


def add_box(view, cell, color='black', linewidth=2):
    a, b, c = np.array(cell[0]), np.array(cell[1]), np.array(cell[2])
    corners = []
    for i in [0, 1]:
        for j in [0, 1]:
            for k in [0, 1]:
                corner = i * a + j * b + k * c
                corners.append(corner)

    # Draw box edges
    edges = []
    for idx in range(8):
        i = idx & 1
        j = (idx >> 1) & 1
        k = (idx >> 2) & 1
        if i == 0:
            edges.append((corners[idx], corners[idx + 1]))
        if j == 0:
            edges.append((corners[idx], corners[idx + 2]))
        if k == 0:
            edges.append((corners[idx], corners[idx + 4]))

    for start, end in edges:
        view.addLine({
            'start': {'x': float(start[0]), 'y': float(start[1]), 'z': float(start[2])},
            'end': {'x': float(end[0]), 'y': float(end[1]), 'z': float(end[2])},
            'color': color,
            'linewidth': linewidth
        })

    # Add arrows for a, b, c directions
    arrow_radius = 0.04  # thinner
    arrow_color = '#000000'  # semi-transparent red
    for vec in [a, b, c]:
        view.addArrow({
            'start': {'x': 0, 'y': 0, 'z': 0},
            'end': {'x': float(vec[0]), 'y': float(vec[1]), 'z': float(vec[2])},
            'color': arrow_color,
            'radius': arrow_radius
        })

    # Add value labels at end of vectors
    offset = 0.3

    def add_axis_label(vec, label_val):
        norm = np.linalg.norm(vec)
        end = vec + offset * vec / (norm + 1e-6)
        view.addLabel(label_val, {
            'position': {'x': float(end[0]), 'y': float(end[1]), 'z': float(end[2])},
            'fontSize': 14,
            'fontColor': color,
            'showBackground': False
        })

    a_len = np.linalg.norm(a)
    b_len = np.linalg.norm(b)
    c_len = np.linalg.norm(c)

    add_axis_label(a, f"a = {a_len:.2f} Å")
    add_axis_label(b, f"b = {b_len:.2f} Å")
    add_axis_label(c, f"c = {c_len:.2f} Å")


# --- Structure Visualization ---
jmol_colors = {
    'H': '#FFFFFF',
    'He': '#D9FFFF',
    'Li': '#CC80FF',
    'Be': '#C2FF00',
    'B': '#FFB5B5',
    'C': '#909090',
    'N': '#3050F8',
    'O': '#FF0D0D',
    'F': '#90FF90',
    'Ne': '#B4E4F5',
    'Na': '#AB5CF2',
    'Mg': '#3DFF00',
    'Al': '#BFA6A6',
    'Si': '#FFC86E',
    'P': '#FF8000',
    'S': '#FFFF30',
    'Cl': '#1FF01F',
    'Ar': '#80D1E2',
    'K': '#8F40D4',
    'Ca': '#3DFFFF'
}

if uploaded_files:
    file_options = [file.name for file in uploaded_files]
    selected_file = st.selectbox("Select structure for interactive visualization", file_options)
    structure = read(selected_file)

    xyz_io = StringIO()
    write(xyz_io, structure, format="xyz")
    xyz_str = xyz_io.getvalue()
    st.subheader("Interactive Structure Visualization")

    view = py3Dmol.view(width=600, height=400)
    view.addModel(xyz_str, "xyz")
    view.setStyle({'model': 0}, {"sphere": {"radius": 0.3, "colorscheme": "Jmol"}})

    cell = structure.get_cell()
    add_box(view, cell, color='black', linewidth=2)

    view.zoomTo()
    view.zoom(1.2)

    html_str = view._make_html()
    centered_html = f"<div style='display: flex; justify-content: center;'>{html_str}</div>"
    st.components.v1.html(centered_html, height=420)

    unique_elements = sorted(set(structure.get_chemical_symbols()))
    legend_html = "<div style='display: flex; flex-wrap: wrap; align-items: center;'>"
    for elem in unique_elements:
        color = jmol_colors.get(elem, "#CCCCCC")
        legend_html += (
            f"<div style='margin-right: 15px; display: flex; align-items: center;'>"
            f"<div style='width: 20px; height: 20px; background-color: {color}; margin-right: 5px; border: 1px solid black;'></div>"
            f"<span>{elem}</span></div>"
        )
    legend_html += "</div>"

    left_col, right_col = st.columns(2)

    cell_params = structure.get_cell_lengths_and_angles()  # (a, b, c, α, β, γ)
    lattice_str = (
        f"a = {cell_params[0]:.4f} Å<br>"
        f"b = {cell_params[1]:.4f} Å<br>"
        f"c = {cell_params[2]:.4f} Å<br>"
        f"α = {cell_params[3]:.2f}°<br>"
        f"β = {cell_params[4]:.2f}°<br>"
        f"γ = {cell_params[5]:.2f}°"
    )
    left_col.markdown("**Lattice Parameters:**<br>" + lattice_str, unsafe_allow_html=True)

    right_col.markdown("**Legend:**")
    right_col.markdown(legend_html, unsafe_allow_html=True)
    right_col.markdown("**Number of Atoms:** " + str(len(structure)))
    try:
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

        mg_structure = AseAtomsAdaptor.get_structure(structure)
        sg_analyzer = SpacegroupAnalyzer(mg_structure)
        spg_symbol = sg_analyzer.get_space_group_symbol()
        spg_number = sg_analyzer.get_space_group_number()
        right_col.markdown(f"**Space Group:** {spg_symbol} ({spg_number})")
    except Exception as e:
        right_col.markdown("**Space Group:** Not available")


# --- XRD Settings and Calculation ---
st.divider()
st.subheader(
    "⚙️ XRD Settings",
    help=(
        "Calculates the XRD pattern using Bragg-Brentano geometry. First, the reciprocal lattice is computed "
        "and all points within a sphere of radius 2/λ are identified. For each (hkl) plane, the Bragg condition "
        "(sinθ = λ/(2dₕₖₗ)) is applied. The structure factor, Fₕₖₗ, is computed as the sum of the atomic scattering "
        "factors. The atomic scattering factor is given by:\n\n"
        "  f(s) = Z − 41.78214·s²·Σᵢ aᵢ exp(−bᵢ s²)  with s = sinθ/λ\n\n"
        "Here:\n"
        " • f(s) is the atomic scattering factor.\n"
        " • Z is the atomic number.\n"
        " • aᵢ and bᵢ are tabulated fitted parameters that describe the decay of f(s) with increasing s.\n\n"
        "The intensity is then computed as Iₕₖₗ = |Fₕₖₗ|², and a Lorentz-polarization correction P(θ) = "
        "(1+cos²(2θ))/(sin²θ cosθ) is applied."
    )
)

st.info(
    "🔬 The following XRD patterns are for **powder samples** using **Bragg-Brentano (θ-2θ) geometry**, assuming **randomly oriented crystallites**. "
    "The calculator applies the **Lorentz-polarization correction**: `P(θ) = (1 + cos²(2θ)) / (sin²θ cosθ)`. It does not **not** account for other corrections, such as preferred orientation, "
    "instrumental broadening, or temperature effects (Debye-Waller factors). ")

import matplotlib.pyplot as plt
from ase.io import read
from pymatgen.io.ase import AseAtomsAdaptor
from pymatgen.analysis.diffraction.xrd import XRDCalculator


def format_index(index):
    s = str(index)
    if len(s) == 2:
        return s + " "
    return s


def twotheta_to_metric(twotheta_deg, metric, wavelength_A, wavelength_nm):
    twotheta_deg = np.asarray(twotheta_deg)
    theta = np.deg2rad(twotheta_deg / 2)
    if metric == "2θ (°)":
        result = twotheta_deg
    elif metric == "2θ (rad)":
        result = np.deg2rad(twotheta_deg)
    elif metric == "q (1/Å)":
        result = (4 * np.pi / wavelength_A) * np.sin(theta)
    elif metric == "q (1/nm)":
        result = (4 * np.pi / wavelength_nm) * np.sin(theta)
    elif metric == "d (Å)":
        result = np.where(np.sin(theta) == 0, np.inf, wavelength_A / (2 * np.sin(theta)))
    elif metric == "d (nm)":
        result = np.where(np.sin(theta) == 0, np.inf, wavelength_nm / (2 * np.sin(theta)))
    elif metric == "energy (keV)":
        result = (24.796 * np.sin(theta)) / wavelength_A
    elif metric == "frequency (PHz)":
        f_Hz = (24.796 * np.sin(theta)) / wavelength_A * 2.418e17
        result = f_Hz / 1e15
    else:
        result = twotheta_deg
    if np.ndim(twotheta_deg) == 0:
        return float(result)
    return result


def metric_to_twotheta(metric_value, metric, wavelength_A, wavelength_nm):
    if metric == "2θ (°)":
        return metric_value
    elif metric == "2θ (rad)":
        return np.rad2deg(metric_value)
    elif metric == "q (1/Å)":
        theta = np.arcsin(np.clip(metric_value * wavelength_A / (4 * np.pi), 0, 1))
        return np.rad2deg(2 * theta)
    elif metric == "q (1/nm)":
        theta = np.arcsin(np.clip(metric_value * wavelength_nm / (4 * np.pi), 0, 1))
        return np.rad2deg(2 * theta)
    elif metric == "d (Å)":
        sin_theta = np.clip(wavelength_A / (2 * metric_value), 0, 1)
        theta = np.arcsin(sin_theta)
        return np.rad2deg(2 * theta)
    elif metric == "d (nm)":
        sin_theta = np.clip(wavelength_nm / (2 * metric_value), 0, 1)
        theta = np.arcsin(sin_theta)
        return np.rad2deg(2 * theta)
    elif metric == "energy (keV)":
        theta = np.arcsin(np.clip(metric_value * wavelength_A / 24.796, 0, 1))
        return np.rad2deg(2 * theta)
    elif metric == "frequency (PHz)":
        f_Hz = metric_value * 1e15
        E_keV = f_Hz / 2.418e17
        theta = np.arcsin(np.clip(E_keV * wavelength_A / 24.796, 0, 1))
        return np.rad2deg(2 * theta)
    else:
        return metric_value


conversion_info = {
    "2θ (°)": "Identity: 2θ in degrees.",
    "2θ (rad)": "Conversion: radians = degrees * (π/180).",
    "q (1/Å)": "q = (4π/λ) * sin(θ), with λ in Å.",
    "q (1/nm)": "q = (4π/λ) * sin(θ), with λ in nm.",
    "d (Å)": "d = λ / (2 sin(θ)), with λ in Å.",
    "d (nm)": "d = λ / (2 sin(θ)), with λ in nm.",
    "energy (keV)": "E = (24.796 * sin(θ)) / λ, with λ in Å.",
    "frequency (PHz)": "f = [(24.796 * sin(θ))/λ * 2.418e17] / 1e15, with λ in Å."
}

# --- Wavelength Selection ---
preset_options = [
    'CoKa1', 'CoKa2', 'Co(Ka1+Ka2)', 'Co(Ka1+Ka2+Kb1)', 'CoKb1',
    'MoKa1', 'MoKa2', 'Mo(Ka1+Ka2)', 'Mo(Ka1+Ka2+Kb1)', 'MoKb1',
    'CuKa1', 'CuKa2', 'Cu(Ka1+Ka2)', 'Cu(Ka1+Ka2+Kb1)', 'CuKb1',
    'CrKa1', 'CrKa2', 'Cr(Ka1+Ka2)', 'Cr(Ka1+Ka2+Kb1)', 'CrKb1',
    'FeKa1', 'FeKa2', 'Fe(Ka1+Ka2)', 'Fe(Ka1+Ka2+Kb1)', 'FeKb1',
    'AgKa1', 'AgKa2', 'Ag(Ka1+Ka2)', 'Ag(Ka1+Ka2+Kb1)', 'AgKb1'
]
preset_wavelengths = {
    'Cu(Ka1+Ka2)': 0.154,
    'CuKa2': 0.15444,
    'CuKa1': 0.15406,
    'Cu(Ka1+Ka2+Kb1)': 0.153339,
    'CuKb1': 0.13922,
    'Mo(Ka1+Ka2)': 0.071,
    'MoKa2': 0.0711,
    'MoKa1': 0.07093,
    'Mo(Ka1+Ka2+Kb1)': 0.07059119,
    'MoKb1': 0.064,
    'Cr(Ka1+Ka2)': 0.229,
    'CrKa2': 0.22888,
    'CrKa1': 0.22897,
    'Cr(Ka1+Ka2+Kb1)': 0.22775471,
    'CrKb1': 0.208,
    'Fe(Ka1+Ka2)': 0.194,
    'FeKa2': 0.194,
    'FeKa1': 0.19360,
    'Fe(Ka1+Ka2+Kb1)': 0.1927295,
    'FeKb1': 0.176,
    'Co(Ka1+Ka2)': 0.179,
    'CoKa2': 0.17927,
    'CoKa1': 0.17889,
    'Co(Ka1+Ka2+Kb1)': 0.1781100,
    'CoKb1': 0.163,
    'Ag(Ka1+Ka2)': 0.0561,
    'AgKa2': 0.0560,
    'AgKa1': 0.0561,
    'AgKb1': 0.0496,
    'Ag(Ka1+Ka2+Kb1)': 0.0557006
}
preset_choice = st.selectbox("⚙️ Preset Wavelength", options=preset_options, index=0, help=(
    "Factors for weighted average of wavelengths are: I1 = 2 (ka1), I2 = 1 (ka2), I3 = 0.18 (kb1)"))
wavelength_value = st.number_input("⚙️ Wavelength (nm)",
                                   value=preset_wavelengths[preset_choice],
                                   min_value=0.001,
                                   step=0.001, format="%.5f")
st.write(f"**Using wavelength = {wavelength_value} nm**")
wavelength_A = wavelength_value * 10  # Convert nm to Å
wavelength_nm = wavelength_value

# --- X-axis Metric Selection ---
x_axis_options = [
    "2θ (°)", "2θ (rad)",
    "q (1/Å)", "q (1/nm)",
    "d (Å)", "d (nm)",
    "energy (keV)", "frequency (PHz)"
]
if "x_axis_metric" not in st.session_state:
    st.session_state.x_axis_metric = x_axis_options[0]

x_axis_metric = st.selectbox(
    "⚙️ XRD x-axis Metric",
    x_axis_options,
    index=x_axis_options.index(st.session_state.x_axis_metric),
    key="x_axis_metric",
    help=conversion_info[st.session_state.x_axis_metric]
)

# --- Initialize canonical two_theta_range in session_state (always in degrees) ---
if "two_theta_min" not in st.session_state:
    if x_axis_metric in ["energy (keV)", "frequency (PHz)"]:
        st.session_state.two_theta_min = 2.0
    elif x_axis_metric in ["d (Å)", "d (nm)"]:
        st.session_state.two_theta_min = 20.0
    else:
        st.session_state.two_theta_min = 2.0
if "two_theta_max" not in st.session_state:
    st.session_state.two_theta_max = 165.0

# --- Compute display values by converting canonical two_theta values to current unit ---
display_metric_min = twotheta_to_metric(st.session_state.two_theta_min, x_axis_metric, wavelength_A, wavelength_nm)
display_metric_max = twotheta_to_metric(st.session_state.two_theta_max, x_axis_metric, wavelength_A, wavelength_nm)

if x_axis_metric == "2θ (°)":
    step_val = 1.0
elif x_axis_metric == "2θ (rad)":
    step_val = 0.0174533
else:
    step_val = 0.1

col1, col2 = st.columns(2)
min_val = col1.number_input(f"⚙️ Minimum {x_axis_metric}", value=display_metric_min, step=step_val,
                            key=f"min_val_{x_axis_metric}")
max_val = col2.number_input(f"⚙️ Maximum {x_axis_metric}", value=display_metric_max, step=step_val,
                            key=f"max_val_{x_axis_metric}")

# --- Update the canonical two_theta values based on current inputs ---
st.session_state.two_theta_min = metric_to_twotheta(min_val, x_axis_metric, wavelength_A, wavelength_nm)
st.session_state.two_theta_max = metric_to_twotheta(max_val, x_axis_metric, wavelength_A, wavelength_nm)
two_theta_range = (st.session_state.two_theta_min, st.session_state.two_theta_max)

sigma = st.number_input("⚙️ Gaussian sigma (°) for peak sharpness (smaller = sharper peaks)",
                        min_value=0.01, max_value=1.0, value=0.1, step=0.01)
num_annotate = st.number_input("⚙️ Annotate top how many peaks (by intensity):",
                               min_value=0, max_value=30, value=5, step=1)

# NEW: Option to select between normalized or absolute intensity scales.
intensity_scale_option = st.radio(
    "Select intensity scale",
    options=["Normalized", "Absolute"],
    index=0,
    help="Normalized scale sets maximum peak to 100; Absolute scale shows raw calculated intensities."
)

if "calc_xrd" not in st.session_state:
    st.session_state.calc_xrd = False
if st.button("Calculate XRD"):
    st.session_state.calc_xrd = True

# --- XRD Calculation ---
if st.session_state.calc_xrd and uploaded_files:
    st.subheader("📊 OUTPUT → XRD Patterns")
    st.markdown("### Exclude Structures from the XRD Plot")
    include_in_combined = {}
    for file in uploaded_files:
        include_in_combined[file.name] = st.checkbox(f"Include {file.name} in combined XRD plot", value=True)
    xrd_calc = XRDCalculator(wavelength=wavelength_A)
    fig_combined, ax_combined = plt.subplots()
    colors = plt.cm.tab10.colors
    pattern_details = {}

    # Assign local two_theta boundaries from session_state for later use
    two_theta_min = st.session_state.two_theta_min
    two_theta_max = st.session_state.two_theta_max

    for idx, file in enumerate(uploaded_files):
        structure = read(file.name)
        mg_structure = AseAtomsAdaptor.get_structure(structure)
        # Get pattern with absolute intensities (we will scale manually if needed)
        xrd_pattern = xrd_calc.get_pattern(mg_structure, two_theta_range=(two_theta_min, two_theta_max), scaled=False)

        filtered_x = []
        filtered_y = []
        filtered_hkls = []

        for x_val, y_val, hkl_group in zip(xrd_pattern.x, xrd_pattern.y, xrd_pattern.hkls):
            if any(len(h['hkl']) == 3 and tuple(h['hkl'][:3]) == (0, 0, 0) for h in hkl_group):
                continue
            if any(len(h['hkl']) == 4 and tuple(h['hkl'][:4]) == (0, 0, 0, 0) for h in hkl_group):
                continue
            filtered_x.append(x_val)
            filtered_y.append(y_val)
            filtered_hkls.append(hkl_group)

        x_dense = np.linspace(two_theta_min, two_theta_max, 2000)
        x_dense_plot = twotheta_to_metric(x_dense, x_axis_metric, wavelength_A, wavelength_nm)
        y_dense = np.zeros_like(x_dense)

        # Build continuous intensity curve via Gaussian broadening
        # Build continuous intensity curve via Gaussian broadening
        for peak, intensity in zip(filtered_x, filtered_y):
            y_dense += intensity * np.exp(-((x_dense - peak) ** 2) / (2 * sigma ** 2))

        # Compute normalization factors
        norm_factor_raw = np.max(filtered_y) if np.max(filtered_y) > 0 else 1.0
        norm_factor_curve = np.max(y_dense) if np.max(y_dense) > 0 else 1.0

        # Adjust the continuous curve so that its maximum equals the raw maximum
        scaling_factor = norm_factor_raw / norm_factor_curve
        y_dense = y_dense * scaling_factor

        # Now use the raw maximum as the normalization factor for both arrays
        if intensity_scale_option == "Normalized":
            y_dense = (y_dense / norm_factor_raw) * 100
            displayed_intensity_array = (np.array(filtered_y) / norm_factor_raw) * 100
        else:
            displayed_intensity_array = np.array(filtered_y)

        peak_vals = twotheta_to_metric(np.array(filtered_x), x_axis_metric, wavelength_A, wavelength_nm)
        if len(displayed_intensity_array) > 0:
            annotate_indices = set(np.argsort(displayed_intensity_array)[-num_annotate:])
        else:
            annotate_indices = set()

        pattern_details[file.name] = {
            "peak_vals": peak_vals,
            "intensities": displayed_intensity_array,
            "hkls": filtered_hkls,
            "annotate_indices": annotate_indices,
            "x_dense_plot": x_dense_plot,
            "y_dense": y_dense
        }

        if include_in_combined[file.name]:
            color = colors[idx % len(colors)]
            ax_combined.plot(x_dense_plot, y_dense, label=f"{file.name}", color=color)
            for i, (peak, hkl_group) in enumerate(zip(peak_vals, filtered_hkls)):
                # Find the actual plotted intensity for this peak in y_dense
                closest_index = np.abs(x_dense_plot - peak).argmin()  # Find the nearest x value
                actual_intensity = y_dense[closest_index]  # Get corresponding y value
                if i in annotate_indices:
                    if len(hkl_group[0]['hkl']) == 3:
                        hkl_str = ", ".join(
                            [f"({format_index(h['hkl'][0])}{format_index(h['hkl'][1])}{format_index(h['hkl'][2])})"
                             for h in hkl_group])
                    if len(hkl_group[0]['hkl']) == 4:
                        hkl_str = ", ".join(
                            [f"({format_index(h['hkl'][0])}{format_index(h['hkl'][1])}{format_index(h['hkl'][3])})"
                             for h in hkl_group])
                    ax_combined.annotate(hkl_str, xy=(peak, actual_intensity), xytext=(0, 5),
                                         textcoords='offset points', fontsize=8, rotation=90,
                                         ha='center', va='bottom')

    ax_combined.set_xlabel(x_axis_metric)
    if intensity_scale_option == "Normalized":
        ax_combined.set_ylabel("Intensity (Normalized, a.u.)")
    else:
        ax_combined.set_ylabel("Intensity (Absolute, a.u.)")
    ax_combined.set_title("Powder XRD Patterns")
    if ax_combined.get_lines():
        max_intensity = max([np.max(line.get_ydata()) for line in ax_combined.get_lines()])
        ax_combined.set_ylim(0, max_intensity * 1.2)
    ax_combined.legend()
    st.pyplot(fig_combined)

    for file in uploaded_files:
        details = pattern_details[file.name]
        peak_vals = details["peak_vals"]
        intensities = details["intensities"]
        hkls = details["hkls"]
        annotate_indices = details["annotate_indices"]
        x_dense_plot = details["x_dense_plot"]
        y_dense = details["y_dense"]

        with st.expander(f"View Peak Data for XRD Pattern: {file.name}"):
            table_str = "#X-axis    Intensity    hkl\n"
            for theta, intensity, hkl_group in zip(peak_vals, intensities, hkls):
                if len(hkl_group[0]['hkl']) == 3:
                    hkl_str = ", ".join(
                        [f"({format_index(h['hkl'][0])}{format_index(h['hkl'][1])}{format_index(h['hkl'][2])})"
                         for h in hkl_group])
                if len(hkl_group[0]['hkl']) == 4:
                    hkl_str = ", ".join(
                        [f"({format_index(h['hkl'][0])}{format_index(h['hkl'][1])}{format_index(h['hkl'][3])})"
                         for h in hkl_group])
                table_str += f"{theta:<12.3f} {intensity:<12.3f} {hkl_str}\n"
            st.code(table_str, language="text")

        with st.expander(f"View Highest Intensity Peaks for XRD Pattern: {file.name}", expanded=True):
            table_str2 = "#X-axis    Intensity    hkl\n"
            for i, (theta, intensity, hkl_group) in enumerate(zip(peak_vals, intensities, hkls)):
                if i in annotate_indices:
                    if len(hkl_group[0]['hkl']) == 3:
                        hkl_str = ", ".join(
                            [f"({format_index(h['hkl'][0])}{format_index(h['hkl'][1])}{format_index(h['hkl'][2])})"
                             for h in hkl_group])
                    if len(hkl_group[0]['hkl']) == 4:
                        hkl_str = ", ".join(
                            [f"({format_index(h['hkl'][0])}{format_index(h['hkl'][1])}{format_index(h['hkl'][3])})"
                             for h in hkl_group])
                    table_str2 += f"{theta:<12.3f} {intensity:<12.3f} {hkl_str}\n"
            st.code(table_str2, language="text")

        with st.expander(f"View Continuous Curve Data for XRD Pattern: {file.name}"):
            table_str3 = "#X-axis    Y-value\n"
            for x_val, y_val in zip(x_dense_plot, y_dense):
                table_str3 += f"{x_val:<12.5f} {y_val:<12.5f}\n"
            st.code(table_str3, language="text")

        st.divider()
    import pandas as pd

    # Dictionary to store combined data
    combined_data = {}

    # First, populate the combined_data dictionary
    for file in uploaded_files:
        file_name = file.name
        details = pattern_details[file_name]  # Ensure we are using the right source

        combined_data[file_name] = {
            "Peak Vals": details["peak_vals"],
            "Intensities": details["intensities"],
            "HKLs": details["hkls"]
        }

    # --- NEW EXPANDER: COMBINED DATA TABLE ---
    selected_metric = st.session_state.x_axis_metric
    with st.expander("📊 View Combined Peak Data Across All Structures", expanded=True):
        combined_df = pd.DataFrame()
        data_list = []
        for file in uploaded_files:
            file_name = file.name
            if file_name in combined_data:
                peak_vals = combined_data[file_name]["Peak Vals"]
                intensities = combined_data[file_name]["Intensities"]
                hkls = combined_data[file_name]["HKLs"]
                for i in range(len(peak_vals)):
                    for group in hkls:
                        for item in group:
                            hkl = item['hkl']
                            if len(hkl) == 3 and tuple(hkl[:3]) == (0, 0, 0):
                                continue
                            if len(hkl) == 4 and tuple(hkl[:4]) == (0, 0, 0, 0):
                                continue
                    if len(hkl) == 3:
                        hkl_str = ", ".join([f"({h['hkl'][0]}{h['hkl'][1]}{h['hkl'][2]})" for h in hkls[i]])
                    if len(hkl) == 4:
                        hkl_str = ", ".join([f"({h['hkl'][0]}{h['hkl'][1]}{h['hkl'][3]})" for h in hkls[i]])
                    data_list.append([peak_vals[i], intensities[i], hkl_str, file_name])
        combined_df = pd.DataFrame(data_list, columns=["{}".format(selected_metric), "Intensity", "(hkl)", "Phase"])
        st.dataframe(combined_df)







# --- RDF (PRDF) Settings and Calculation --
st.divider()
st.subheader("⚙️ (P)RDF Settings")
st.info(
    "🔬 **PRDF** describes the atomic element pair distances distribution within a structure, providing insight into **local environments** and **structural disorder**. "
    "It is commonly used in **diffusion studies** to track atomic movement and ion transport, as well as in **phase transition analysis**, revealing changes in atomic ordering during melting or crystallization. "
    "Additionally, PRDF/RDF are employed as one of the **structural descriptors in machine learning**.")

cutoff = st.number_input("⚙️ Cutoff (Å)", min_value=1.0, max_value=50.0, value=10.0, step=1.0, format="%.1f")
bin_size = st.number_input("⚙️ Bin Size (Å)", min_value=0.05, max_value=5.0, value=0.1, step=0.05, format="%.2f")

if "calc_rdf" not in st.session_state:
    st.session_state.calc_rdf = False
if st.button("Calculate RDF"):
    st.session_state.calc_rdf = True

if st.session_state.calc_rdf and uploaded_files:
    st.subheader("📊 OUTPUT → RDF (PRDF & Global RDF)")
    species_combinations = list(combinations(species_list, 2)) + [(s, s) for s in species_list]
    all_prdf_dict = defaultdict(list)
    all_distance_dict = {}
    global_rdf_list = []
    for file in uploaded_files:
        structure = read(file.name)
        mg_structure = AseAtomsAdaptor.get_structure(structure)
        prdf_featurizer = PartialRadialDistributionFunction(cutoff=cutoff, bin_size=bin_size)
        prdf_featurizer.fit([mg_structure])
        prdf_data = prdf_featurizer.featurize(mg_structure)
        feature_labels = prdf_featurizer.feature_labels()
        prdf_dict = defaultdict(list)
        distance_dict = {}
        global_dict = {}
        for i, label in enumerate(feature_labels):
            parts = label.split(" PRDF r=")
            element_pair = tuple(parts[0].split("-"))
            distance_range = parts[1].split("-")
            bin_center = (float(distance_range[0]) + float(distance_range[1])) / 2
            prdf_dict[element_pair].append(prdf_data[i])
            if element_pair not in distance_dict:
                distance_dict[element_pair] = []
            distance_dict[element_pair].append(bin_center)
            global_dict[bin_center] = global_dict.get(bin_center, 0) + prdf_data[i]
        for pair, values in prdf_dict.items():
            if pair not in all_distance_dict:
                all_distance_dict[pair] = distance_dict[pair]
            if isinstance(values, float):
                values = [values]
            all_prdf_dict[pair].append(values)
        global_rdf_list.append(global_dict)
    multi_structures = len(uploaded_files) > 1
    colors = plt.cm.tab10.colors
    st.divider()
    st.subheader("PRDF Plots:")
    for idx, (comb, prdf_list) in enumerate(all_prdf_dict.items()):
        valid_prdf = [np.array(p) for p in prdf_list if isinstance(p, list)]
        if valid_prdf:
            prdf_array = np.vstack(valid_prdf)
            prdf_avg = np.mean(prdf_array, axis=0) if multi_structures else prdf_array[0]
        else:
            prdf_avg = np.zeros_like(all_distance_dict[comb])
        title_str = f"Averaged PRDF: {comb[0]}-{comb[1]}" if multi_structures else f"PRDF: {comb[0]}-{comb[1]}"
        fig, ax = plt.subplots()
        color = colors[idx % len(colors)]
        ax.plot(all_distance_dict[comb], prdf_avg, label=f"{comb[0]}-{comb[1]}", color=color)
        ax.set_xlabel("Distance (Å)")
        ax.set_ylabel("PRDF Intensity")
        ax.set_title(title_str)
        ax.legend()
        ax.set_ylim(bottom=0)
        st.pyplot(fig)
        with st.expander(f"View Data for {comb[0]}-{comb[1]}"):
            table_str = "#Distance (Å)    PRDF\n"
            for x, y in zip(all_distance_dict[comb], prdf_avg):
                table_str += f"{x:<12.3f} {y:<12.3f}\n"
            st.code(table_str, language="text")
    st.subheader("Global RDF Plot:")
    global_bins_set = set()
    for gd in global_rdf_list:
        global_bins_set.update(gd.keys())
    global_bins = sorted(list(global_bins_set))
    global_rdf_avg = []
    for b in global_bins:
        vals = []
        for gd in global_rdf_list:
            vals.append(gd.get(b, 0))
        global_rdf_avg.append(np.mean(vals))
    fig_global, ax_global = plt.subplots()
    title_global = "Averaged Global RDF" if multi_structures else "Global RDF"
    global_color = colors[len(all_prdf_dict) % len(colors)]
    ax_global.plot(global_bins, global_rdf_avg, label="Global RDF", color=global_color)
    ax_global.set_xlabel("Distance (Å)")
    ax_global.set_ylabel("Global RDF Intensity")
    ax_global.set_title(title_global)
    ax_global.legend()
    ax_global.set_ylim(bottom=0)
    st.pyplot(fig_global)
    with st.expander("View Data for Global RDF"):
        table_str = "#Distance (Å)    Global RDF\n"
        for x, y in zip(global_bins, global_rdf_avg):
            table_str += f"{x:<12.3f} {y:<12.3f}\n"
        st.code(table_str, language="text")
