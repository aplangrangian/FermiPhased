#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov  9 22:52:40 2025

@author: alexlange
"""
# =============================================================================
# Dependencies
# =============================================================================

import sys
import json
import os
import time
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QTextEdit, QHBoxLayout, QFrame, QCheckBox, QGridLayout,
    QComboBox
)
from PyQt5.QtCore import Qt
import numpy as np
import yaml
import paramiko
from scp import SCPClient
from tqdm import tqdm
import glob
import pandas as pd
from astropy.io import fits

# =============================================================================
# If there is a problem with setting up FermiPhased with your cluster, it will
# be located somewhere here
# =============================================================================

def create_ssh_client(hostname, username, key_filename):
    """Creates and returns an SSH client connection using key authentication."""
    ssh = paramiko.SSHClient()
    # Accept new host keys automatically
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname, username=username, key_filename=os.path.expanduser(
        key_filename))
    return ssh

def scp_transfer(LOCAL_PATH, REMOTE_PATH,config):
    """Transfers scripts to the remote server with a progress bar."""
    ssh = None
    scp = None
    SSH_HOST = config["ssh"]["host"]
    SSH_USERNAME = config["ssh"]["username"]
    SSH_KEY_PATH = config["ssh"]["key_path"]
    try:
        ssh = create_ssh_client(SSH_HOST, SSH_USERNAME, SSH_KEY_PATH)
        ssh.get_transport().set_keepalive(30)
        scp = SCPClient(ssh.get_transport())
        print("trying...")
        clean_cmd = f'find {REMOTE_PATH} -maxdepth 1 -type f -name "*.sh" -delete'
        ssh.exec_command(clean_cmd)
        print("-------- Old shell scripts deleted --------")
        flag_cmd = f'find {REMOTE_PATH} -maxdepth 1 -type f -name "done*" -delete'
        ssh.exec_command(flag_cmd)
        print("-------- Old flags  deleted --------")
        files_to_transfer = [
            f for f in os.listdir(LOCAL_PATH)
            if f.endswith(".sh") or f.endswith(".yaml") or f == "analyze_phases.py"
        ]

        if not files_to_transfer:
            print("No scripts found to transfer.")
            return

        print(f"Uploading {len(files_to_transfer)} files → {REMOTE_PATH}\n")

        with tqdm(total=len(files_to_transfer), unit="file") as pbar:
            for file in files_to_transfer:
                scp.put(
                    os.path.join(LOCAL_PATH, file),
                    os.path.join(REMOTE_PATH, file),
                )
                pbar.set_postfix_str(f"Uploading: {file}")
                pbar.update(1)
        scp.close()
        print("-------- Upload complete --------")
        mv_cmd = f'cd {REMOTE_PATH}'
        ssh.exec_command(mv_cmd)
        cmd = f'''bash -l -c "
        cd {REMOTE_PATH} || exit 1

        shopt -s nullglob
        for f in phase_batch_*.sh; do
            echo Submitting \$f
            sbatch \"\$f\"
        done
        "'''

        stdin, stdout, stderr = ssh.exec_command(cmd)

        # wait for completion and print output
        stdout.channel.recv_exit_status()
        # print(stdout.read().decode())
        # print(stderr.read().decode())

        print("-------- SBATCHs Submitted --------")
    except Exception as e:
        print(f"SCP Upload Error: {e}")

# =============================================================================
# Below loads the setup parameters...
# These shouldn't change much such as the pathing for catalog directories,
# conda environments or RSA keys and login-info for clusters
# =============================================================================



def prompt(msg, default=None):
    """Helper for user input with optional default."""
    if default:
        val = input(f"{msg} [{default}]: ").strip()
        return val if val else default
    return input(f"{msg}: ").strip()


def create_config(config_path):
    print("\n⚙️ No setup.yaml found — creating one...\n")

    config = {
        "ssh": {
            "host": prompt("SSH host (gwu.cluster.edu)"),
            "username": prompt("SSH username (alexlange)"),
            "key_path": os.path.expanduser(prompt("SSH key path (~/.ssh/id_rsa)")),
        },

        "paths": {
            "cluster_fermi_make_dir": prompt("Cluster Fermi dir (./4FGL_Make)"),
            "local_fermi_make_dir": prompt("Local Fermi dir (./4FGL_Make)"),

            "galdiff_local": prompt("Local GALDIFF path (./gll_iem_v07.fits)"),
            "isodiff_local": prompt("Local ISODIFF path (./iso_P8R3_SOURCE_V3_v1.txt)"),

            "galdiff_cluster": prompt("Cluster GALDIFF path (./gll_iem_v07.fits)"),
            "isodiff_cluster": prompt("Cluster ISODIFF path (./iso_P8R3_SOURCE_V3_v1.txt)"),

            "catalog_cluster": prompt("Cluster catalog path (./gll_psc_v35.fit)"),
            "ext_catalog_cluster": prompt("Cluster extended catalog path"),

            "catalog_local": prompt("Local catalog path (./gll_psc_v35.fit)"),
            "ext_catalog_local": prompt("Local extended catalog path (./Extended_12years)"),
        },

        "env": {
            "conda_script": prompt("Conda init script path (/c1/apps/anaconda/2021.05/etc/profile.d/conda.sh)"),
            "environment": prompt("Conda environment name (fermipy)"),
        },

        "email": prompt("Email address (alexlange@gwu.edu)"),
    }

    # Save file
    with open(config_path, "w") as f:
        yaml.dump(config, f, sort_keys=False)

    print(f"\nConfig saved → {config_path}\n")

    return config


def load_config(config_path="setup.yaml"):
    config_path = os.path.expanduser(config_path)

    if not os.path.exists(config_path):
        return create_config(config_path)

    with open(config_path, "r") as f:
        return yaml.safe_load(f)

# =============================================================================
# Beyond this point is all Fermi analysis and scripting
# =============================================================================

class FermiScriptGenerator(QWidget):



    CONFIG = load_config()

    def __init__(self,config):
        super().__init__()
        self.config = config

        self.SSH_HOST = self.config["ssh"]["host"]
        self.SSH_USERNAME = self.config["ssh"]["username"]
        self.SSH_KEY_PATH = self.config["ssh"]["key_path"]

        self.CLUSTER_FERMI_MAKE_DIR = self.config["paths"]["cluster_fermi_make_dir"]
        self.LOCAL_FERMI_MAKE_DIR = self.config["paths"]["local_fermi_make_dir"]

        self.LOCAL_GALDIFF_PATH = self.config["paths"]["galdiff_local"]
        self.CLUSTER_GALDIFF_PATH = self.config["paths"]["galdiff_cluster"]

        self.LOCAL_ISODIFF_PATH = self.config["paths"]["isodiff_local"]
        self.CLUSTER_ISODIFF_PATH = self.config["paths"]["isodiff_cluster"]

        self.CLUSTER_CAT_PATH = self.config["paths"]["catalog_cluster"]
        self.CLUSTER_EXT_CAT_PATH = self.config["paths"]["ext_catalog_cluster"]

        self.LOCAL_CAT_PATH = self.config["paths"]["catalog_local"]
        self.LOCAL_EXT_CAT_PATH = self.config["paths"]["ext_catalog_local"]

        self.CLUSTER_SCRIPT_PATH = self.config["env"]["conda_script"]
        self.FermiPyFermiTools_Installation = self.config["env"]["environment"]

        self.email = self.config["email"]
        self.FERMI_MAKE_DIR = self.LOCAL_FERMI_MAKE_DIR

        self.settings_file = "settings.json"  # Default settings file
        self.setWindowTitle("Phase-resolved analysis with Fermi-Lat data")
        self.setGeometry(100, 100, 900, 800) # Change to full screen? Needs long enough for paths
        self.setStyleSheet("background-color: #0b0d1b; color: white; font-family: Arial;")

        # PtQt5 layout  for GUI
        layout = QVBoxLayout()

        # Fermi Logo
        self.logo_label = QLabel(self)
        self.logo_label.setPixmap(QPixmap("fermi_logo.png").scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.logo_label.setAlignment(Qt.AlignCenter)  # Correct alignment
        layout.addWidget(self.logo_label)


        self.input_grid = QGridLayout()
        layout.addLayout(self.input_grid)
        self.input_row = 0
        self.input_col = 0
        self.phase_bins_coords = None
        self.counts_coords = None

        # Title
        title_label = QLabel("Fermi Script Generator")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.logo_label.setAlignment(Qt.AlignCenter)  # Correct alignment
        layout.addWidget(title_label)

        # Divider Line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # Label to display the currently loaded settings file
        self.settings_label = QLabel(f"Settings File: {self.settings_file}")
        self.settings_label.setStyleSheet("color: #FFD700;")  # Yellow text
        layout.addWidget(self.settings_label)

        self.mode_switch = QComboBox()
        self.mode_switch.addItems(["Basic", "Adaptive (Fixed Counts) Binning - NOTE: Wait times may vary", "Joint Epoch Fitting"])
        self.mode_switch.currentIndexChanged.connect(self.update_mode_fields)
        layout.addWidget(QLabel("Mode: (Please select one of the following)"))
        self.mode_switch.setFont(QFont("Arial", 14))
        layout.addWidget(self.mode_switch)
        self.mode_switch.setStyleSheet("background-color: #f5deb3; color: black")

        # Input fields
        self.fields = {}
        self.counts_input_layout = None
        self.phase_bins_layout = None
        self.main_layout = layout
        # LS 5039 parameters are set as default
        self.create_input(layout, "Source", "LS 5039")
        self.create_input(layout, "Radius (Deg)", "10")

        self.create_input(layout, "RA (J2000 Deg)", "276.5637")
        self.create_input(layout, "DEC (J2000 Deg)", "-14.8496")

        self.create_input(layout, "T0 (MJD)", "55016.58")
        self.create_input(layout, "Period (Days)", "3.90608")

        self.create_input(layout, "Min Time (MET)", "239557417")
        self.create_input(layout, "Max Time (MET)", "668413063")
        self.create_input(layout, "Min Energy (MeV)", "100")
        self.create_input(layout, "Max Energy (MeV)", "100000")
        self.create_input(layout, "Number of Energy Bins", "14")

        self.create_input(layout, "Partition", "large-gpu")
        self.create_input(layout, "Cores", "8")
        self.create_input(layout, "Runtime", "8:00:00")



        # File paths
        self.create_file_input(layout, "Remote Directory",is_directory=True)
        self.create_file_input(layout, "Local Directory", is_directory=True)
        self.create_file_input(layout, "Spacecraft File", is_directory=False)
        self.create_file_input(layout, "Event File", is_directory=False)



        # Buttons Layout
        buttons_layout = QHBoxLayout()

        self.save_button = QPushButton("Save Settings")
        self.save_button.setStyleSheet("background-color: #005AB5; color: white;")
        self.save_button.clicked.connect(self.save_settings)
        buttons_layout.addWidget(self.save_button)

        # Button to browse and select a settings file
        self.select_settings_button = QPushButton("Select Settings File")
        self.select_settings_button.setStyleSheet("background-color: #34b338; color: white")
        self.select_settings_button.clicked.connect(self.select_settings_file)
        buttons_layout.addWidget(self.select_settings_button)

        self.reset_button = QPushButton("Reset")
        self.reset_button.setStyleSheet("background-color: #B22222; color: white;")
        self.reset_button.clicked.connect(self.reset_settings)
        buttons_layout.addWidget(self.reset_button)

        layout.addLayout(buttons_layout)
        self.upload_toggle = QCheckBox("Send Scripts to Cluster after Generation")
        self.upload_toggle.setStyleSheet("color: #FFD700;")  # Yellow text
        layout.addWidget(self.upload_toggle)
        self.generate_button = QPushButton("Generate Scripts")
        self.generate_button.setStyleSheet("background-color: #FF8C00; color: white;")
        self.generate_button.clicked.connect(self.generate_scripts)
        layout.addWidget(self.generate_button)

        # Status output
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setStyleSheet("background-color: #1A1C2D; color: white;")
        layout.addWidget(self.status_text)

        self.setLayout(layout)

        # Load previous settings in a .JSON format
        self.load_settings()

        self.update_mode_fields()  # Adds correct field depending on initial mode
        # No more problems between multiple switching?


    def create_input(self, layout, label, default_value=""):
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet("color: #00BFFF;")
        entry = QLineEdit()
        entry.setText(default_value)
        entry.setStyleSheet("background-color: #1E1E30; color: white; border: 1px solid #00BFFF;")
        self.fields[label] = entry

        col = self.input_col * 2
        self.input_grid.addWidget(lbl, self.input_row, col)
        self.input_grid.addWidget(entry, self.input_row, col + 1)

        self.input_col += 1
        if self.input_col >= 2:
            self.input_col = 0
            self.input_row += 1


    def create_custom_input(self, label, default_value=""):
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet("color: #00BFFF;")
        entry = QLineEdit()
        entry.setText(default_value)
        entry.setStyleSheet("background-color: #1E1E30; color: white; border: 1px solid #00BFFF;")
        self.fields[label] = entry

        col = self.input_col * 2
        self.input_grid.addWidget(lbl, self.input_row, col)
        self.input_grid.addWidget(entry, self.input_row, col + 1)

        self.input_col += 1
        if self.input_col >= 2:
            self.input_col = 0
            self.input_row += 1

        return None  # Layout added directly



    def create_file_input(self, layout, label, is_directory=False):
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet("color: #00BFFF;")
        entry = QLineEdit()
        entry.setStyleSheet("background-color: #1E1E30; color: white; border: 1px solid #00BFFF;")
        browse_button = QPushButton("Browse")
        browse_button.setStyleSheet("background-color: #3A3D66; color: white; padding: 3px;")
        browse_button.clicked.connect(lambda: self.browse_file(entry, is_directory))
        self.fields[label] = entry

        file_input_layout = QHBoxLayout()
        file_input_layout.addWidget(entry)
        file_input_layout.addWidget(browse_button)

        col = self.input_col * 2
        self.input_grid.addWidget(lbl, self.input_row, col)
        self.input_grid.addLayout(file_input_layout, self.input_row, col + 1)

        self.input_col += 1
        if self.input_col >= 2:
            self.input_col = 0
            self.input_row += 1


    def update_mode_fields(self):
        mode = self.mode_switch.currentText()
        # working_dir = self.fields["Remote Directory"].text().strip()
        # local_dir = self.fields["Local Directory"].text().strip()

        if self.phase_bins_coords:
            row, col = self.phase_bins_coords
            for offset in [0, 1]:
                item = self.input_grid.itemAtPosition(row, col + offset)
                if item and item.widget():
                    item.widget().deleteLater()
            if "Number of Phase Bins" in self.fields:
                del self.fields["Number of Phase Bins"]
            self.phase_bins_coords = None

        if self.counts_coords:
            row, col = self.counts_coords
            for offset in [0, 1]:
                item = self.input_grid.itemAtPosition(row, col + offset)
                if item and item.widget():
                    item.widget().deleteLater()
            if "Number of Counts" in self.fields:
                del self.fields["Number of Counts"]
            self.counts_coords = None

        # Constant Counts needs updating
        if mode == "Adaptive (Fixed Counts) Binning - NOTE: Wait times may vary":
            label = QLabel("Number of Counts:")
            label.setStyleSheet("color: #00BFFF;")
            entry = QLineEdit("10000")
            entry.setStyleSheet("background-color: #1E1E30; color: white; border: 1px solid #00BFFF;")
            self.fields["Number of Counts"] = entry

            col = self.input_col * 2
            self.input_grid.addWidget(label, self.input_row, col)
            self.input_grid.addWidget(entry, self.input_row, col + 1)
            self.counts_coords = (self.input_row, col)

            self.input_col += 1
            if self.input_col >= 2:
                self.input_col = 0
                self.input_row += 1




        else:
            label = QLabel("Number of Phase Bins:")
            label.setStyleSheet("color: #00BFFF;")
            entry = QLineEdit("14")
            entry.setStyleSheet("background-color: #1E1E30; color: white; border: 1px solid #00BFFF;")
            self.fields["Number of Phase Bins"] = entry

            col = self.input_col * 2
            self.input_grid.addWidget(label, self.input_row, col)
            self.input_grid.addWidget(entry, self.input_row, col + 1)
            self.phase_bins_coords = (self.input_row, col)

            self.input_col += 1
            if self.input_col >= 2:
                self.input_col = 0
                self.input_row += 1

        if mode == "Joint Epoch Fitting":
                self.fields["Min Time (MET)"].setPlaceholderText("Comma-separated start times")
                self.fields["Max Time (MET)"].setPlaceholderText("Comma-separated end times")
                self.fields["T0 (MJD)"].setPlaceholderText("Comma-separated T0s")
                self.fields["Period (Days)"].setPlaceholderText("Comma-separated Periods")
        else:
            self.fields["Min Time (MET)"].setPlaceholderText("")
            self.fields["Max Time (MET)"].setPlaceholderText("")
            self.fields["T0 (MJD)"].setPlaceholderText("")
            self.fields["Period (Days)"].setPlaceholderText("")



    def browse_file(self, entry, is_directory=False):
        """Opens a file or directory dialog."""
        if is_directory:
            path = QFileDialog.getExistingDirectory(self, "Select Directory")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "FITS Files (*.fits);;All Files (*.*)")
        if path:
            entry.setText(path)

    def select_settings_file(self):
        """Allows user to select a settings JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Settings File", "", "JSON Files (*.json)")
        if file_path:
            self.settings_file = file_path
            self.settings_label.setText(f"Settings File: {self.settings_file}")
            self.load_settings()

    def save_settings(self):
        """Saves the current settings to a JSON file."""
        settings = {key: self.fields[key].text() for key in self.fields}
        with open(self.settings_file, "w") as f:
            json.dump(settings, f)
        self.status_text.append(f"Settings saved to {self.settings_file}")

    def load_settings(self):
        """Loads settings from the selected JSON file."""
        if os.path.exists(self.settings_file):
            with open(self.settings_file, "r") as f:
                settings = json.load(f)
                for key, value in settings.items():
                    if key in self.fields:
                        self.fields[key].setText(value)
            self.status_text.append(f"Settings loaded from {self.settings_file}")

    def reset_settings(self):
        """Resets settings to default values."""
        for key in self.fields:
            self.fields[key].setText("")
        self.status_text.append("Settings reset.")

    def parse_float_list(self, field_name):
        raw = self.fields[field_name].text()
        print(f"DEBUG: Raw input for {field_name!r} → {repr(raw)}")
        return [float(x.strip()) for x in raw.split(',')]

    def generate_scripts(self):
        """Needs mode updates"""
        mode = self.mode_switch.currentText()
        print(mode)
        """Generates the scripts and saves them in the selected Remote Directory."""
        working_dir = self.fields["Remote Directory"].text().strip()
        local_dir = self.fields["Local Directory"].text().strip()
        # REMOTE_PATH = working_dir
        # LOCAL_PATH=local_dir
        CORES = int(self.fields["Cores"].text())
        SRCNAME = self.fields["Source"].text()
        PARTITION = self.fields["Partition"].text()

        if not working_dir:
            self.status_text.append("⚠️ Error: No remote directory selected!")
            return

        try:
            os.makedirs(local_dir, exist_ok=True)

            # Read user input values

            # period = float(self.fields["Period"].text())
            # t0 = float(self.fields["T0"].text())
            ra = float(self.fields["RA (J2000 Deg)"].text())
            dec = float(self.fields["DEC (J2000 Deg)"].text())
            rad = float(self.fields["Radius (Deg)"].text())

            emin = int(self.fields["Min Energy (MeV)"].text())
            emax = int(self.fields["Max Energy (MeV)"].text())
            ebins = int(self.fields["Number of Energy Bins"].text())
            event_file = self.fields["Event File"].text()
            sc_file = self.fields["Spacecraft File"].text()


            CORES = int(self.fields["Cores"].text())
            RUNTIME = self.fields["Runtime"].text()



            if mode == "Basic":
                period = float(self.fields["Period (Days)"].text())
                t0 = float(self.fields["T0 (MJD)"].text())
                phase_bins = int(self.fields["Number of Phase Bins"].text())
                tmin = float(self.fields["Min Time (MET)"].text())
                tmax = float(self.fields["Max Time (MET)"].text())

                for sh_file in glob.glob(os.path.join(local_dir, "*.sh")):
                    os.remove(sh_file)

                phases = list(range(1, phase_bins + 1))
                phase_chunks = [phases[i:i+CORES] for i in range(0, len(phases), CORES)]

                for chunk_id, phase_group in enumerate(phase_chunks):

                        script_blocks = []

                        i = chunk_id
                        block = "\n\n".join([
                            self.gen_header(i, working_dir, phase_bins,CORES,RUNTIME,self.FERMI_MAKE_DIR,PARTITION,self.CLUSTER_SCRIPT_PATH,self.FermiPyFermiTools_Installation),
                            self.gen_script(i, phase_bins, ra, dec, t0, period, event_file, sc_file),
                            self.gtselect_script(i, ra, dec, rad, tmin, tmax, emin, emax),
                            self.gtbin_script(i, sc_file, emin, emax, ebins, ra, dec),
                            self.gtltcube_script(i, sc_file, tmin, tmax),
                            self.gen_closer(phase_bins,working_dir, i,CORES,RUNTIME,PARTITION,self.FERMI_MAKE_DIR,self.email,self.CLUSTER_SCRIPT_PATH,self.FermiPyFermiTools_Installation)
                        ])

                        # run each phase in background
                        # block += " &\n"
                        script_blocks.append(block)

                        # still generate configs per phase
                        self.generate_config(
                            i, local_dir, event_file, sc_file,
                            ra, dec, rad, tmin, tmax, emin, emax, ebins,
                            self.CLUSTER_ISODIFF_PATH, self.CLUSTER_GALDIFF_PATH,
                            self.CLUSTER_CAT_PATH, self.CLUSTER_EXT_CAT_PATH
                        )

                        self.generate_analysis_script(i, local_dir, working_dir, phase_bins,SRCNAME,self.CLUSTER_EXT_CAT_PATH)

                        # wait for all background jobs in this chunk
                        script_blocks.append("wait\n")

                        script_content = "\n".join(script_blocks)

                        script_path = os.path.join(local_dir, f"phase_batch_{chunk_id}.sh")

                        with open(script_path, "w") as f:
                            f.write(script_content)



            if mode == "Adaptive (Fixed Counts) Binning - NOTE: Wait times may vary":
                try:
                    self.status_text.append("Starting adaptive (fixed-count) binning...")

                    num_counts = int(self.fields["Number of Counts"].text())
                    event_file = self.fields["Event File"].text().strip()
                    sc_file = self.fields["Spacecraft File"].text().strip()
                    emin = float(self.fields["Min Energy (MeV)"].text())
                    emax = float(self.fields["Max Energy (MeV)"].text())
                    ra = float(self.fields["RA (J2000 Deg)"].text())
                    dec = float(self.fields["DEC (J2000 Deg)"].text())
                    rad = float(self.fields["Radius (Deg)"].text())
                    tmin = float(self.fields["Min Time (MET)"].text())
                    tmax = float(self.fields["Max Time (MET)"].text())
                    ebins = int(self.fields["Number of Energy Bins"].text())
                    local_dir = self.fields["Local Directory"].text().strip()
                    working_dir = self.fields["Remote Directory"].text().strip()
                    filename = os.path.basename(event_file)
                    event_file_dir = os.path.join(working_dir,filename)

                    os.makedirs(local_dir, exist_ok=True)

                    # --- Load the FITS data ---
                    with fits.open(event_file) as hdul:
                        data = hdul[1].data
                        pulse_phase = data["PULSE_PHASE"][
                            (data["ENERGY"] > emin) & (data["ENERGY"] < emax)
                        ]

                    if len(pulse_phase) < num_counts:
                        self.status_text.append("⚠️ Warning: Not enough counts for requested bin size.")
                        return

                    # --- Compute adaptive bins ---
                    sorted_phases = np.sort(pulse_phase)
                    num_bins = len(sorted_phases) // num_counts
                    bin_edges = np.array(
                        [sorted_phases[i * num_counts] for i in range(num_bins)] + [1.0]
                    )
                    bin_widths = np.diff(bin_edges)
                    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

                    # --- Save bin info ---
                    bin_info = pd.DataFrame({
                        "Bin Start": bin_edges[:-1],
                        "Bin End": bin_edges[1:],
                        "Bin Width": bin_widths,
                        "Bin Center": bin_centers
                    })
                    bin_info_path = os.path.join(local_dir, "adaptive_bins.csv")
                    bin_info.to_csv(bin_info_path, index=False)
                    self.status_text.append(f"📊 Saved adaptive bin info → {bin_info_path}")
                    for sh_file in glob.glob(os.path.join(local_dir, "*.sh")):
                        os.remove(sh_file)
                    # --- Generate scripts per adaptive bin ---
                    for i, (pmin, pmax) in enumerate(zip(bin_edges[:-1], bin_edges[1:]), start=1):
                        script_content = "\n\n".join([
                            self.gen_header(i, working_dir, phase_bins,CORES,RUNTIME,self.FERMI_MAKE_DIR,PARTITION,self.CLUSTER_SCRIPT_PATH,self.FermiPyFermiTools_Installation),
                            self.gtselect_script_adaptive(i, event_file_dir, ra, dec, rad, tmin, tmax, emin, emax, pmin, pmax),

#                             f"""gtselect infile={event_file} outfile=./ft1_00.fits \
# ra={ra} dec={dec} rad={rad} \
# tmin={tmin} tmax={tmax} emin={emin} emax={emax} \
# phasemin={pmin:.6f} phasemax={pmax:.6f} \
# zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 \
# evtable="EVENTS" chatter=3 clobber=yes debug=no gui=no mode="ql" """,
                            self.gtbin_script(i, sc_file, emin, emax, ebins, ra, dec),
                            self.gtltcube_script(i, sc_file, tmin, tmax),
                            self.gen_closer(phase_bins,working_dir, i,CORES,RUNTIME,PARTITION,self.FERMI_MAKE_DIR,self.email,self.CLUSTER_SCRIPT_PATH,self.FermiPyFermiTools_Installation),
                        ])

                        script_path = os.path.join(local_dir, f"phase_{i}.sh")
                        # self.generate_config(
                        #     i,
                        #     local_dir,
                        #     event_file,
                        #     sc_file,
                        #     ra,
                        #     dec,
                        #     rad,
                        #     tmin,
                        #     tmax,
                        #     emin,
                        #     emax,
                        #     ebins
                        # )
                        # self.generate_analysis_script(i, local_dir,working_dir,phase_bins)

                        # phase_dir = os.path.join(local_dir, f"{i}")
                        # os.makedirs(phase_dir, exist_ok=True)
                        # script_path = os.path.join(phase_dir, f"phase_{i}.sh")
                        with open(script_path, "w") as f:
                            f.write(script_content)

                    self.status_text.append(
                        f"Generated {num_bins} adaptive phase scripts in {local_dir}"
                    )

                    # Optional: Upload if toggle enabled
                    if self.upload_toggle.isChecked():
                        self.status_text.append("Uploading adaptive scripts to cluster...")
                        scp_transfer(local_dir, working_dir,config)

                except Exception as e:
                    self.status_text.append(f"Adaptive binning error: {e}")




            if mode == "Joint Epoch Fitting":
                phase_bins = int(self.fields["Number of Phase Bins"].text())

                tmins   = list(map(float, self.fields["Min Time (MET)"].text().split(',')))
                tmaxs   = list(map(float, self.fields["Max Time (MET)"].text().split(',')))
                t0s     = list(map(float, self.fields["T0 (MJD)"].text().split(',')))
                periods = list(map(float, self.fields["Period (Days)"].text().split(',')))

                if not (len(tmins) == len(tmaxs) == len(t0s) == len(periods)):
                    self.status_text.append("⚠️ Error: T0s, Periods, Start times, and Stop times must have the same count.")
                    return

                # clean old scripts
                for sh_file in glob.glob(os.path.join(local_dir, "*.sh")):
                    os.remove(sh_file)

                phases = list(range(1, phase_bins + 1))
                phase_chunks = [phases[i:i+CORES] for i in range(0, len(phases), CORES)]

                for chunk_id, phase_group in enumerate(phase_chunks):

                        script_blocks = []


                        i = chunk_id
                        block = "\n\n".join([
                            self.gen_header(i, working_dir, phase_bins, CORES, RUNTIME,
                                            self.FERMI_MAKE_DIR, PARTITION,
                                            self.CLUSTER_SCRIPT_PATH,
                                            self.FermiPyFermiTools_Installation),

                            self.gen_script_multiple(i, phase_bins, ra, dec,
                                                     t0s, periods, event_file, sc_file,
                                                     tmins, tmaxs),

                            self.gtselect_script_multiple(i, ra, dec, rad,
                                                          tmins, tmaxs, emin, emax),

                            self.gtbin_script_multiple(i, sc_file, emin, emax, ebins, ra, dec),

                            self.gtltcube_script_multiple(i, sc_file, tmins, tmaxs),

                            self.gen_closer(phase_bins, working_dir, i, CORES, RUNTIME,
                                            PARTITION, self.FERMI_MAKE_DIR, self.email,
                                            self.CLUSTER_SCRIPT_PATH,
                                            self.FermiPyFermiTools_Installation)
                        ])

                        # run each phase in background
                        block += " &\n"
                        script_blocks.append(block)

                        # still generate configs per phase
                        self.generate_config(
                            i, local_dir, event_file, sc_file,
                            ra, dec, rad, tmins[0], tmaxs[0],  # (or pass full arrays if needed)
                            emin, emax, ebins,
                            self.CLUSTER_ISODIFF_PATH, self.CLUSTER_GALDIFF_PATH,
                            self.CLUSTER_CAT_PATH, self.CLUSTER_EXT_CAT_PATH
                        )

                        self.generate_analysis_script(i, local_dir, working_dir, phase_bins, SRCNAME,self.CLUSTER_EXT_CAT_PATH)

                        # wait for all jobs in chunk
                        script_blocks.append("wait\n")

                        script_content = "\n".join(script_blocks)

                        script_path = os.path.join(local_dir, f"phase_batch_{chunk_id}.sh")

                        with open(script_path, "w") as f:
                            f.write(script_content)

                self.status_text.append(f"Scripts successfully saved in: {local_dir}")

        except Exception as e:
            self.status_text.append(f"Error: {e}")
        if self.upload_toggle.isChecked():
            self.status_text.append("Uploading scripts to the cluster...")
            # scp_transfer()
            scp_transfer(local_dir, working_dir,config)

    def gen_script(self, phase, phase_bins, ra, dec, t0, period, event_file, sc_file):
        cos_value = np.cos(360 / (2 * phase_bins) / 180 * np.pi)  # Precompute cosine
        return f"""gtmktime apply_filter=yes evfile={event_file} scfile={sc_file} outfile=${{PHASE}}.fits filter="COS(2*3.14159265359*(START/(86400)+ 51910-{t0} - ${{SHIFT}}*{period}*{1/phase_bins})/{period})>{cos_value} && COS(2*3.14159265359*(STOP/(86400)+ 51910-{t0} - ${{SHIFT}}*{period}*{1/phase_bins})/{period})>{cos_value} && (DATA_QUAL>0) && (LAT_CONFIG==1)" roicut=no"""

    def gen_script_multiple(self, phase, phase_bins, ra, dec, t0s, periods, event_file, sc_file,tmins,tmaxs):
        cos_value = np.cos(360 / (2 * phase_bins) / 180 * np.pi)  # Precompute cosine
        return f"""gtmktime apply_filter=yes evfile={event_file} scfile={sc_file} outfile=./{phase}.fits filter="(START > {tmins[0]}) && (START < {tmaxs[0]}) && (STOP > {tmins[0]}) && (STOP < {tmaxs[0]}) && COS(2*3.14159265359*( (START) /(86400)+ 51910-{t0s[0]} - {phase-1}*{periods[0]}*{1/phase_bins})/{periods[0]})>{cos_value} && COS(2*3.14159265359*(( STOP  )/(86400)+ 51910-{t0s[0]} - {phase-1}*{periods[0]}*{1/phase_bins})/{periods[0]})>{cos_value} || (START > {tmins[1]}) && (START < {tmaxs[1]}) && (STOP > {tmins[1]}) && (STOP < {tmaxs[1]}) && COS(2*3.14159265359*( (START) /(86400)+ 51910-{t0s[1]} - {phase-1}*{periods[1]}*{1/phase_bins})/{periods[1]})>{cos_value} && COS(2*3.14159265359*((STOP)/(86400)+ 51910-{t0s[1]} - {phase-1}*{periods[1]}*{1/phase_bins})/{periods[1]})>{cos_value} && (DATA_QUAL>0) && (LAT_CONFIG==1)" roicut=no"""

    def gtselect_script(self, phase, ra, dec, radius, tmin, tmax, emin, emax):
        return f"""gtselect infile=./${{PHASE}}.fits outfile=./ft1_00.fits ra={ra} dec={dec} rad={radius} tmin={tmin} tmax={tmax} emin={emin} emax={emax} zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 evtable="EVENTS" chatter=3 clobber=yes debug=no gui=no mode="ql" """

    def gtselect_script_adaptive(self, phase, event_file_dir, ra, dec, radius, tmin, tmax, emin, emax,pmin,pmax):
        # retun f"""gtselect infile="+str(event_file)+" outfile=./ft1_00.fits ra="+str(ra)+" dec="+str(dec)+" rad=15 tmin="+str(tmin)+" tmax="+str(tmax)+" phasemin="+str(phases[int(phase),0])+" phasemax="+str(phases[int(phase),1]) + " emin="+str(emin)+" emax="+str(emax)+" zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 evtable=\"EVENTS\" chatter=3 clobber=yes debug=no gui=no mode=\"ql\" """
        return f"""gtselect infile={event_file_dir} outfile=./ft1_00.fits ra={ra} dec={dec} rad={radius} tmin={tmin} tmax={tmax} emin={emin} emax={emax} phasemin={pmin} phasemax={pmax} zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 evtable="EVENTS" chatter=3 clobber=yes debug=no gui=no mode="ql" """

    def gtselect_script_multiple(self, phase, ra, dec, radius, tmins, tmaxs, emin, emax):
        return f"""gtselect infile=./{phase}.fits outfile=./ft1_00.fits ra={ra} dec={dec} rad={radius} tmin={tmins[0]} tmax={tmaxs[1]} emin={emin} emax={emax} zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 evtable="EVENTS" chatter=3 clobber=yes debug=no gui=no mode="ql" """

    def gtbin_script(self, phase, sc_file, emin, emax, ebins, ra, dec):
        return f"""gtbin evfile=./ft1_00.fits scfile={sc_file} outfile=./ccube_00.fits algorithm="ccube" ebinalg="LOG" emin={emin} emax={emax} enumbins={ebins} ebinfile=NONE tbinalg="LIN" tbinfile=NONE nxpix=200 nypix=200 binsz=0.1 coordsys="CEL" xref={ra} yref={dec} axisrot=0.0 rafield="RA" decfield="DEC" proj="AIT" hpx_ordering_scheme="RING" hpx_order=3 hpx_ebin=yes hpx_region= evtable="EVENTS" sctable="SC_DATA" efield="ENERGY" tfield="TIME" chatter=3 clobber=yes debug=no gui=no mode="ql" """

    def gtbin_script_multiple(self, phase, sc_file, emin, emax, ebins, ra, dec):
        return f"""gtbin evfile=./ft1_00.fits scfile={sc_file} outfile=./ccube_00.fits algorithm="ccube" ebinalg="LOG" emin={emin} emax={emax} enumbins={ebins} ebinfile=NONE tbinalg="LIN" tbinfile=NONE nxpix=200 nypix=200 binsz=0.1 coordsys="CEL" xref={ra} yref={dec} axisrot=0.0 rafield="RA" decfield="DEC" proj="AIT" hpx_ordering_scheme="RING" hpx_order=3 hpx_ebin=yes hpx_region= evtable="EVENTS" sctable="SC_DATA" efield="ENERGY" tfield="TIME" chatter=3 clobber=yes debug=no gui=no mode="ql" """

    def gtltcube_script(self, phase, sc_file, tmin, tmax):
        return f"""gtltcube evfile=./ft1_00.fits evtable="EVENTS" scfile={sc_file} sctable="SC_DATA" outfile=./ltcube_00.fits dcostheta=0.025 binsz=1.0 phibins=0 tmin={tmin} tmax={tmax} file_version="1" zmin=0.0 zmax=90.0 chatter=2 clobber=yes debug=no gui=no mode="ql" """

    def gtltcube_script_multiple(self, phase, sc_file, tmins, tmaxs):
        return f"""gtltcube evfile=./ft1_00.fits evtable="EVENTS" scfile={sc_file} sctable="SC_DATA" outfile=./ltcube_00.fits dcostheta=0.025 binsz=1.0 phibins=0 tmin={tmins[0]} tmax={tmaxs[1]} file_version="1" zmin=0.0 zmax=90.0 chatter=2 clobber=yes debug=no gui=no mode="ql" """

    def gen_header(self,phase, working_dir, phase_bins,cores,RUNTIME, FERMI_MAKE_DIR,PARTITION,CLUSTER_SCRIPT_PATH,FermiPyFermiTools_Installation):
        return f"""#!/bin/sh

#SBATCH -p {PARTITION}
#SBATCH --cpus-per-task={cores}
#SBATCH --gres=gpu:v100:4
#SBATCH -D {working_dir}
#SBATCH --export={FERMI_MAKE_DIR}
#SBATCH -t {RUNTIME}

. {CLUSTER_SCRIPT_PATH}


conda activate {FermiPyFermiTools_Installation}

run_phase (){{

PHASE=$1
SHIFT=$2

rm -rf ${{PHASE}}
mkdir -p ${{PHASE}}
cd ${{PHASE}}


"""


    def gen_closer(self, phase_bins, working_dir, phase, cores, RUNTIME, PARTITION,FERMI_MAKE_DIR,email,CLUSTER_SCRIPT_PATH,FermiPyFermiTools_Installation):
        return f"""
cd ..
echo phase done
}}


CORES={cores}
PHASE_BINS={phase_bins}
PHASE={phase*cores}


BLOCK=phase//cores


END=$((PHASE + CORES -1))
N_BLOCKS=$(( (PHASE_BINS + CORES - 1) / CORES ))



for ((i=PHASE; i<=END && i<=PHASE_BINS-1; i++)); do
    run_phase $((i+1)) $((i)) &
done

wait


touch done_${{PHASE}}.flag
sleep 60


COUNT=$(find . -type f -name "done_*.flag" | wc -l)

if [ "$COUNT" -eq "$PHASE_BINS" ]; then
    echo "All $COUNT phases complete. Running analysis."
    for i in {{1..{phase_bins}}}
    do
    cp config.yaml $i
    done








    # =============================================================================
    # This is the script that creates directs FermiPhased to execute the reduction
    # of Fermi data. This process is set up to run on SLURM and requires SBATCH to
    # specify job details. Please update to match your job manager.
    # =============================================================================
    cat > analyze_script.sh << 'EOF'
#!/bin/sh
#SBATCH -p {PARTITION}
#SBATCH --cpus-per-task={cores}
#SBATCH --export={FERMI_MAKE_DIR}
#SBATCH -t {RUNTIME}
#SBATCH -D {working_dir}

#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user={email}


. {CLUSTER_SCRIPT_PATH}

conda activate {FermiPyFermiTools_Installation}

python analyze_phases.py #Needs better parallelization - will be updated soon.
EOF


    sbatch analyze_script.sh
else
    echo "⏳ $COUNT/{phase_bins} phases done. Passing to another node..."
fi

"""
    # =============================================================================
    # Config File generation
    # Please update your config file accordingly
    # =============================================================================
    def generate_config(self, phase, local_dir, event_file, sc_file, ra, dec,
                        radius, tmin, tmax, emin, emax, ebins,
                        CLUSTER_ISODIFF_PATH, CLUSTER_GALDIFF_PATH,
                        CLUSTER_CAT_PATH, CLUSTER_EXT_CAT_PATH ):

        config = {
            "data": {
                "evfile": "./ft1_00.fits",
                "scfile": sc_file,
                "ltcube": "./ltcube_00.fits",
            },
            "binning": {
                "roiwidth": radius,
                "binsz": radius/200,
                "binsperdec": 8,
                "enumbins": ebins,
            },
            "selection": {
                "emin": emin,
                "emax": emax,
                "zmax": 90,
                "evclass": 128,
                "evtype": 3,
                "ra": ra,
                "dec": dec,
                "tmin": tmin,
                "tmax": tmax,
            },
            "gtlike": {
                "edisp": True,
                "irfs": "P8R3_SOURCE_V3",
                "edisp_disable": ["isodiff"],
                "edisp_bins": -2,
            },
            "model": {
                "src_roiwidth": str(int(radius)+5),
                "galdiff": CLUSTER_GALDIFF_PATH,
                "isodiff": CLUSTER_ISODIFF_PATH,
                "catalogs": CLUSTER_CAT_PATH
            }
        }
        config_path = os.path.join(local_dir, f"config.yaml")
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        self.status_text.append(f"Config saved: {config_path}")
        self.close()
    def generate_analysis_script(self, i, local_dir,working_dir,phase_bins,SRCNAME,CLUSTER_EXT_CAT_PATH):
        """Write a phase-analysis driver Python script."""
        script_content = f"""import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from math import *  # better to import only what you need
from fermipy.gtanalysis import GTAnalysis

os.environ["LATEXTDIR"] = "{CLUSTER_EXT_CAT_PATH}"

DEBUG = True
VERBOSITY = 4 if DEBUG else 0

def double_fig(*args):
    out = [np.array([args[0], args[0] + 1]).flatten()]
    for arg in args[1:]:
        out.append(np.array([arg, arg]).flatten())
    return out

def setup_gta(directory,phase_bin):
    phase_bin = phase_bin
    os.chdir(directory)
    match = re.search(r'{working_dir}(.*)', directory)
    string = match[1] if match else None

    gta = GTAnalysis(
        './config.yaml',
        optimizer={{'min_fit_quality': 3}},
        logging={{'verbosity': 3}}
    )
    gta.setup(optimizer={{
        'min_fit_quality': 3,
        'optimizer': "MINUIT",
        'retries': 1000,
        'max_iter': 1000
    }})
    gta.curvature('{SRCNAME}') #e eventually may save curvature test results  #

    gta.optimize() # At some point this will be replaced w a integrated model #

    gta.free_sources(distance=15, free=False)
    gta.free_source('{SRCNAME}', pars='norm')

    gta.fit(min_fit_quality=3, optimizer='MINUIT', retries=1000, tol=1e-8)
    gta.write_roi('norm', make_plots=True)

    gta.free_source('{SRCNAME}', free=True)

    gta.fit(min_fit_quality=3, optimizer='NEWMINUIT', retries=1000, tol=1e-8)
    gta.write_roi('spectral_pars', make_plots=True)

    # -------------------------
    # SED EXPORT
    # -------------------------
    sed = gta.sed('{SRCNAME}', use_local_index=True)
    TS_THRESH = 4
    MeV_erg = 1.60218e-6

    flux = sed["e2dnde"] * MeV_erg
    flux_err = sed["e2dnde_err"] * MeV_erg
    flux_err_lo = sed["e2dnde_err_lo"] * MeV_erg
    flux_err_hi = sed["e2dnde_err_hi"] * MeV_erg
    flux_ul = sed["e2dnde_ul95"] * MeV_erg
    ts = sed["ts"]

    flux_out = np.zeros_like(flux)
    flux_err_out = np.zeros_like(flux)
    is_ul = np.zeros_like(ts, dtype=bool)

    for i in range(len(ts)):
        if ts[i] < TS_THRESH:
            flux_out[i] = flux_ul[i]
            flux_err_out[i] = np.nan
            is_ul[i] = True
        else:
            flux_out[i] = flux[i]
            flux_err_out[i] = flux_err[i]

    df = pd.DataFrame({{
            "energy(MeV)":sed["e_ref"],
            "energy_min":sed["e_min"],
            "energy_max":sed["e_max"],
            "flux(MeV/cm2/s)":flux_out,
            "flux_err":flux_err_out,
            "ts":ts,
            "UL":is_ul
            }})

    df.to_csv(os.path.join(directory, f"{SRCNAME}_{{phase_bin}}_sed.csv"), index=False)



    return gta


def analyze_phases():
    gta_list = []
    base_dir = '{working_dir}'

    for d in sorted(os.listdir(base_dir), key=lambda x: int(x) if x.isdigit() else 1e9):
        phase_dir = os.path.join(base_dir, d)

        # only keep numeric directories (phase bins) just updated this....
        if not os.path.isdir(phase_dir) or not d.isdigit():
            continue

        phase_bin = int(d)
        print(f"--- Running phase bin {{phase_bin}} ---") # end update

        gta = setup_gta(phase_dir, phase_bin)
        gta_list.append(gta)

    return gta_list


def load_data_and_plot():
    fluxes, flux_err, ts = [], [], []
    num_bins = {phase_bins}
    spec_params = np.zeros((num_bins, 5))
    spec_errs = np.zeros((num_bins, 5))

    for i in range(num_bins):
        p = np.load(
            f'{working_dir}/{{i + 1}}/spectral_pars.npy',
            allow_pickle=True
        ).flat[0]

        src = p['sources']['{SRCNAME}']
        srctype = src['SpectrumType']

        fluxes.append(src['flux'])
        flux_err.append(src['flux_err'])
        ts.append(src['ts'])

        pars = src['spectral_pars']

        # -------------------------------
        # POWER LAW
        # -------------------------------
        if srctype == "PowerLaw":
            spec_params[i, 0] = pars['Prefactor']['value']
            spec_params[i, 1] = pars['Index']['value']

            spec_errs[i, 0] = pars['Prefactor']['error']
            spec_errs[i, 1] = pars['Index']['error']

        # -------------------------------
        # LOG PARABOLA
        # -------------------------------
        elif srctype == "LogParabola":
            spec_params[i, 0] = pars['norm']['value']
            spec_params[i, 1] = pars['alpha']['value']
            spec_params[i, 2] = pars['beta']['value']
            spec_params[i, 3] = pars['Eb']['value']

            spec_errs[i, 0] = pars['norm']['error']
            spec_errs[i, 1] = pars['alpha']['error']
            spec_errs[i, 2] = pars['beta']['error']
            spec_errs[i, 3] = pars['Eb']['error']

        # -------------------------------
        # PLEC4
        # -------------------------------
        elif srctype == "PLSuperExpCutoff4":
            spec_params[i, 0] = pars['Prefactor']['value']
            spec_params[i, 1] = pars['Index']['value']
            spec_params[i, 2] = pars['Expfactor']['value']
            spec_params[i, 3] = pars['ExpfactorS']['value']
            spec_params[i, 4] = pars['S']['value']

            spec_errs[i, 0] = pars['Prefactor']['error']
            spec_errs[i, 1] = pars['Index']['error']
            spec_errs[i, 2] = pars['Expfactor']['error']
            spec_errs[i, 3] = pars['ExpfactorS']['error']
            spec_errs[i, 4] = pars['S']['error']

        else:
            raise ValueError(f"Unknown SpectrumType")



    phase = np.arange(0, 1, 1 / num_bins)
    phase = np.append(phase, phase + 1)

    fluxes = np.append(fluxes, fluxes)
    flux_err = np.append(flux_err, flux_err)

    phase_half_width = np.full_like(phase, 1.0 / (2*num_bins))
    ts = np.append(ts, ts)

    spec_params = np.vstack([spec_params, spec_params])
    spec_errs = np.vstack([spec_errs, spec_errs])



    fig, axes = plt.subplots(4, 1, figsize=(20, 24), constrained_layout=True)
    ax1, ax2, ax3, axts = axes

    ax1.step(phase, fluxes * 1e8, "k", where='mid')
    ax1.errorbar(phase, fluxes * 1e8, yerr=flux_err * 1e8, fmt="k+")
    ax1.set_ylabel(r"Flux ($10^{{-8}}$ Ph cm$^{{-2}}$ s$^{{-1}}$)", fontsize=32)

    ax2.step(phase, spec_params[:, 1], "k", where='mid')
    ax2.errorbar(phase, spec_params[:, 1], yerr=spec_errs[:, 1], fmt="k+")
    ax2.set_ylabel(r'$\\alpha$', fontsize=32)


    ax3.step(phase, spec_params[:, 2], "k", where='mid')
    ax3.errorbar(phase, spec_params[:, 2], yerr=spec_errs[:, 2], fmt="k+")
    ax3.set_ylabel(r"$\\beta$", fontsize=32)


    axts.step(phase, ts, "k", where='mid')
    axts.set_ylabel("TS", fontsize=28)

    ax1.plot([],[],c="k",label="(A)")
    ax2.plot([],[],c="k",label="(B)")
    ax3.plot([],[],c="k",label="(C)")
    axts.plot([],[],c="k",label="(D)")

    ax1.legend(fontsize=20, frameon=False)
    ax2.legend(fontsize=20, frameon=False)
    ax3.legend(fontsize=20, frameon=False)
    axts.legend(fontsize=20, frameon=False)

    for ax in (ax1, ax2, ax3, axts):
        ax.set_xlim(0, 2)
        ax.axvline(1, color="gray", linestyle="--")
        ax.tick_params(axis='both', labelsize=24)

    ax1.set_xticks([])
    ax2.set_xticks([])
    ax3.set_xticks([])
    plt.xlabel("Phase", fontsize=28)
    plt.tight_layout()
    plt.savefig('{working_dir}/{SRCNAME}_phase_folded_lc.png')


    df = pd.DataFrame({{
        "phase": phase,
        "phase_hw": phase_half_width,
        "flux": fluxes,
        "flux_err": flux_err,
        "ts": ts
        }})

    for i in range(5):
        df[f"par_{i}"] = spec_params[:, i]
        df[f"par_{i}_err"] = spec_errs[:, i]
    df.to_csv('fluxes.csv', index=False)




    return spec_params, spec_errs, phase, fluxes, flux_err, ts

if __name__ == "__main__":

        analyze_phases()
        pars, errs, phase, fluxes, flux_err, ts = load_data_and_plot()

"""
        script_path = os.path.join(local_dir, "analyze_phases.py")
        with open(script_path, "w") as f:
            f.write(script_content)
        self.status_text.append(f"Analysis script written: {script_path}")


# Run the app
if __name__ == "__main__":
    app = QApplication(sys.argv)
    config = load_config()   # ← load once here
    window = FermiScriptGenerator(config)
    window.show()
    sys.exit(app.exec_())
