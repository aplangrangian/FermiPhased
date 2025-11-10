#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov  9 22:52:40 2025

@author: alexlange
"""

import sys
import json
import os
import time
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QTextEdit, QHBoxLayout, QFrame, QCheckBox, QGridLayout, QComboBox
)
from PyQt5.QtCore import Qt
import numpy as np
import yaml
import paramiko
from scp import SCPClient




# =============================================================================
# =============================================================================
# Configuration (Modify these settings)
SSH_HOST = "pegasus.arc.gwu.edu"  # Change this to your actual SSH server (e.g., "192.168.1.1")
SSH_USERNAME = "alexlange"
SSH_KEY_PATH = "~/.ssh/id_rsa.pub"
REMOTE_PATH = "/scratch/kargaltsevgrp/lange/J1702/contemp/final/epoch1"  # Remote directory on the server
LOCAL_PATH = "/Users/alexlange/Desktop/J1702/contemp/final/epoch1"  # Directory containing the .sh files (Change if needed)
# =============================================================================
# =============================================================================





class FermiScriptGenerator(QWidget):
    def __init__(self):
        super().__init__()

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
        self.mode_switch.addItems(["Basic", "Adaptive (Fixed Counts) Binning", "Joint Epoch Fitting"])
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
        self.create_input(layout, "Period", "3.90608")
        self.create_input(layout, "T0", "55016.58")
        self.create_input(layout, "RA", "276.5637")
        self.create_input(layout, "DEC", "-14.8496")
        self.create_input(layout, "Radius", "10")
        self.create_input(layout, "Min Time (MET)", "239557417")
        self.create_input(layout, "Max Time (MET)", "668413063")
        self.create_input(layout, "Min Energy", "100")
        self.create_input(layout, "Max Energy", "100000")
        self.create_input(layout, "Number of Energy Bins", "14")


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
        working_dir = self.fields["Remote Directory"].text().strip()
        local_dir = self.fields["Local Directory"].text().strip()
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
        if mode == "Adaptive (Fixed Counts) Binning":
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


            try:
                from astropy.io import fits
                import pandas as pd

                # --- Get Inputs ---
                num_counts = int(self.fields["Number of Counts"].text())
                event_file = self.fields["Event File"].text().strip()
                emin = float(self.fields["Min Energy"].text())
                emax = float(self.fields["Max Energy"].text())
                ra = float(self.fields["RA"].text())
                dec = float(self.fields["DEC"].text())
                rad = float(self.fields["Radius"].text())
                sc_file = self.fields["Spacecraft File"].text().strip()
                tmin = float(self.fields["Min Time (MET)"].text())
                tmax = float(self.fields["Max Time (MET)"].text())
                ebins = int(self.fields["Number of Energy Bins"].text())

                # --- Load FITS ---
                self.status_text.append(f"Loading event file: {event_file}")
                with fits.open(event_file) as hdul:
                    data = hdul[1].data
                    pulse_phase = data["PULSE_PHASE"][
                        (data["ENERGY"] > emin) & (data["ENERGY"] < emax)
                    ]

                # --- Adaptive Binning Calculation ---
                sorted_phases = np.sort(pulse_phase)
                num_bins = len(sorted_phases) // num_counts
                bin_edges = np.array(
                    [sorted_phases[i * num_counts] for i in range(num_bins)] + [1.0]
                )
                bin_widths = np.diff(bin_edges)
                bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

                # Save bin info for reproducibility
                bin_info = pd.DataFrame({
                    "Bin Start": bin_edges[:-1],
                    "Bin End": bin_edges[1:],
                    "Bin Width": bin_widths,
                    "Bin Center": bin_centers,
                })
                bin_info_path = os.path.join(local_dir, "adaptive_bins.csv")
                bin_info.to_csv(bin_info_path, index=False)
                self.status_text.append(f"📊 Adaptive bin edges saved → {bin_info_path}")

        #         # --- Generate Scripts ---
        #         for i, (pmin, pmax) in enumerate(zip(bin_edges[:-1], bin_edges[1:]), start=1):
        #             script_content = f"""#!/bin/sh
        # #SBATCH -p tiny
        # #SBATCH -N 1
        # #SBATCH -D {working_dir}/{i}/
        # #SBATCH --export=MY_FERMI_DIR=/scratch/groups/kargaltsevgrp/lange/4FGL_Make
        # #SBATCH -t 4:00:00

        # . /c1/apps/anaconda/2021.05/etc/profile.d/conda.sh
        # conda activate fermi2

        # gtselect infile={event_file} outfile=./ft1_00.fits \\
        #     ra={ra} dec={dec} rad={rad} \\
        #     tmin={tmin} tmax={tmax} emin={emin} emax={emax} \\
        #     phasemin={pmin:.6f} phasemax={pmax:.6f} \\
        #     zmin=0.0 zmax=90.0 evclass=128 evtype=3 \\
        #     convtype=-1 chatter=3 clobber=yes mode="ql"

        # gtbin evfile=./ft1_00.fits scfile={sc_file} outfile=./ccube_00.fits \\
        #     algorithm="ccube" ebinalg="LOG" emin={emin} emax={emax} enumbins={ebins} \\
        #     nxpix=200 nypix=200 binsz=0.1 coordsys="CEL" xref={ra} yref={dec} proj="AIT" \\
        #     clobber=yes debug=no gui=no mode="ql"

        # gtltcube evfile=./ft1_00.fits scfile={sc_file} outfile=./ltcube_00.fits \\
        #     dcostheta=0.025 binsz=1.0 phibins=0 tmin={tmin} tmax={tmax} chatter=2 clobber=yes

        # touch done.flag
        # """

                    # phase_dir = os.path.join(local_dir, f"adaptive_{i}")
                    # os.makedirs(phase_dir, exist_ok=True)
                    # script_path = os.path.join(phase_dir, f"adaptive_{i}.sh")
                    # with open(script_path, "w") as f:
                    #     f.write(script_content)

                self.status_text.append(
                    f"✅ Generated {num_bins} adaptive phase scripts in: {local_dir}"
                )

            except Exception as e:
                self.status_text.append(f"⚠️ Adaptive binning error: {e}")

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

        if mode == "Multiple Times":
                self.fields["Min Time (MET)"].setPlaceholderText("Comma-separated start times")
                self.fields["Max Time (MET)"].setPlaceholderText("Comma-separated end times")
                self.fields["T0"].setPlaceholderText("Comma-separated T0s")
                self.fields["Period"].setPlaceholderText("Comma-separated Periods")
        else:
            self.fields["Min Time (MET)"].setPlaceholderText("")
            self.fields["Max Time (MET)"].setPlaceholderText("")
            self.fields["T0"].setPlaceholderText("")
            self.fields["Period"].setPlaceholderText("")



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
        """Generates the scripts and saves them in the selected Remote Directory."""
        working_dir = self.fields["Remote Directory"].text().strip()
        local_dir = self.fields["Local Directory"].text().strip()
        if not working_dir:
            self.status_text.append("⚠️ Error: No remote directory selected!")
            return

        try:
            os.makedirs(local_dir, exist_ok=True)

            # Read user input values

            # period = float(self.fields["Period"].text())
            # t0 = float(self.fields["T0"].text())
            ra = float(self.fields["RA"].text())
            dec = float(self.fields["DEC"].text())
            rad = float(self.fields["Radius"].text())

            emin = int(self.fields["Min Energy"].text())
            emax = int(self.fields["Max Energy"].text())
            ebins = int(self.fields["Number of Energy Bins"].text())
            event_file = self.fields["Event File"].text()
            sc_file = self.fields["Spacecraft File"].text()


            if mode == "Basic":
                period = float(self.fields["Period"].text())
                t0 = float(self.fields["T0"].text())
                phase_bins = int(self.fields["Number of Phase Bins"].text())
                tmin = float(self.fields["Min Time (MET)"].text())
                tmax = float(self.fields["Max Time (MET)"].text())
                for i in range(1, phase_bins + 1):
                    script_content = "\n\n".join([
                        self.gen_header(i, working_dir, phase_bins),
                        self.gen_script(i, phase_bins, ra, dec, t0, period, event_file, sc_file),
                        self.gtselect_script(i, ra, dec, rad, tmin, tmax, emin, emax),
                        self.gtbin_script(i, sc_file, emin, emax, ebins, ra, dec),
                        self.gtltcube_script(i, sc_file, tmin, tmax),
                        self.gen_closer(phase_bins),


                    ])

                    script_path = os.path.join(local_dir, f"phase_{i}.sh")
                    self.generate_config(
                        i,
                        local_dir,
                        event_file,
                        sc_file,
                        ra,
                        dec,
                        rad,
                        tmin,
                        tmax,
                        emin,
                        emax,
                        ebins
                    )
                    self.generate_analysis_script(i, local_dir,working_dir,phase_bins)

                    with open(script_path, "w") as f:
                        f.write(script_content)



            if mode == "Adaptive (Fixed Counts) Binning":
                try:
                    from astropy.io import fits
                    import pandas as pd

                    self.status_text.append("🧮 Starting adaptive (fixed-count) binning...")

                    num_counts = int(self.fields["Number of Counts"].text())
                    event_file = self.fields["Event File"].text().strip()
                    sc_file = self.fields["Spacecraft File"].text().strip()
                    emin = float(self.fields["Min Energy"].text())
                    emax = float(self.fields["Max Energy"].text())
                    ra = float(self.fields["RA"].text())
                    dec = float(self.fields["DEC"].text())
                    rad = float(self.fields["Radius"].text())
                    tmin = float(self.fields["Min Time (MET)"].text())
                    tmax = float(self.fields["Max Time (MET)"].text())
                    ebins = int(self.fields["Number of Energy Bins"].text())
                    local_dir = self.fields["Local Directory"].text().strip()
                    working_dir = self.fields["Remote Directory"].text().strip()

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

                    # --- Generate scripts per adaptive bin ---
                    for i, (pmin, pmax) in enumerate(zip(bin_edges[:-1], bin_edges[1:]), start=1):
                        script_content = "\n\n".join([
                            self.gen_header(i, working_dir, num_bins),
                            self.gtselect_script_adaptive(i, ra, dec, rad, tmin, tmax, emin, emax, pmin, pmax),

#                             f"""gtselect infile={event_file} outfile=./ft1_00.fits \
# ra={ra} dec={dec} rad={rad} \
# tmin={tmin} tmax={tmax} emin={emin} emax={emax} \
# phasemin={pmin:.6f} phasemax={pmax:.6f} \
# zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 \
# evtable="EVENTS" chatter=3 clobber=yes debug=no gui=no mode="ql" """,
                            self.gtbin_script(i, sc_file, emin, emax, ebins, ra, dec),
                            self.gtltcube_script(i, sc_file, tmin, tmax)
                        ])

                        script_path = os.path.join(local_dir, f"phase_{i}.sh")


                        # phase_dir = os.path.join(local_dir, f"{i}")
                        # os.makedirs(phase_dir, exist_ok=True)
                        # script_path = os.path.join(phase_dir, f"phase_{i}.sh")
                        with open(script_path, "w") as f:
                            f.write(script_content)

                    self.status_text.append(
                        f"✅ Generated {num_bins} adaptive phase scripts in {local_dir}"
                    )

                    # Optional: Upload if toggle enabled
                    if self.upload_toggle.isChecked():
                        self.status_text.append("🚀 Uploading adaptive scripts to cluster...")
                        scp_transfer(local_dir, working_dir)

                except Exception as e:
                    self.status_text.append(f"⚠️ Adaptive binning error: {e}")




            if mode == "Multiple Times":
                phase_bins = int(self.fields["Number of Phase Bins"].text())
                # print(phase_bins)
                tmins = list(map(float, self.fields["Min Time (MET)"].text().split(',')))
                tmaxs = list(map(float, self.fields["Max Time (MET)"].text().split(',')))
                t0s = list(map(float, self.fields["T0"].text().split(',')))
                periods = list(map(float, self.fields["Period"].text().split(',')))
                # t0s = float(self.fields["T0"].text())
                # periods = float(self.fields["Period"].text())
                # t0s = [t0s,t0s]
                # periods = [periods,periods]


                if not (len(tmins) == len(tmaxs) == len(t0s) == len(periods)):
                    self.status_text.append("⚠️ Error: T0s, Periods, Start times, and Stop times must have the same count.")
                    return

                for i in range(1, phase_bins + 1):
                    script_content = "\n\n".join([

                        self.gen_header(i, working_dir, phase_bins),
                        self.gen_script_multiple(i, phase_bins, ra, dec, t0s, periods, event_file, sc_file,tmins,tmaxs),
                        self.gtselect_script_multiple(i, ra, dec, rad, tmins, tmaxs, emin, emax),
                        self.gtbin_script_multiple(i, sc_file, emin, emax, ebins, ra, dec),
                        self.gtltcube_script_multiple(i, sc_file, tmins, tmaxs)
                    ])

                    script_path = os.path.join(local_dir, f"phase_{i}.sh")
                    with open(script_path, "w") as f:
                        f.write(script_content)

            self.status_text.append(f"✅ Scripts successfully saved in: {local_dir}")

        except Exception as e:
            self.status_text.append(f"⚠️ Error: {e}")
        if self.upload_toggle.isChecked():
            self.status_text.append("🚀 Uploading scripts to the cluster...")
            # scp_transfer()
            scp_transfer(local_dir, working_dir)

    def gen_script(self, phase, phase_bins, ra, dec, t0, period, event_file, sc_file):
        cos_value = np.cos(360 / (2 * phase_bins) / 180 * np.pi)  # Precompute cosine
        return f"""gtmktime apply_filter=yes evfile={event_file} scfile={sc_file} outfile=./{phase}.fits filter="COS(2*3.14159265359*(START/(86400)+ 51910-{t0} - {phase-1}*{period}*{1/phase_bins})/{period})>{cos_value} && COS(2*3.14159265359*(STOP/(86400)+ 51910-{t0} - {phase-1}*{period}*{1/phase_bins})/{period})>{cos_value} && (DATA_QUAL>0) && (LAT_CONFIG==1)" roicut=no"""

    def gen_script_multiple(self, phase, phase_bins, ra, dec, t0s, periods, event_file, sc_file,tmins,tmaxs):
        cos_value = np.cos(360 / (2 * phase_bins) / 180 * np.pi)  # Precompute cosine
        return f"""gtmktime apply_filter=yes evfile={event_file} scfile={sc_file} outfile=./{phase}.fits filter="(START > {tmins[0]}) && (START < {tmaxs[0]}) && (STOP > {tmins[0]}) && (STOP < {tmaxs[0]}) && COS(2*3.14159265359*( (START) /(86400)+ 51910-{t0s[0]} - {phase-1}*{periods[0]}*{1/phase_bins})/{periods[0]})>{cos_value} && COS(2*3.14159265359*(( STOP  )/(86400)+ 51910-{t0s[0]} - {phase-1}*{periods[0]}*{1/phase_bins})/{periods[0]})>{cos_value} || (START > {tmins[1]}) && (START < {tmaxs[1]}) && (STOP > {tmins[1]}) && (STOP < {tmaxs[1]}) && COS(2*3.14159265359*( (START) /(86400)+ 51910-{t0s[1]} - {phase-1}*{periods[1]}*{1/phase_bins})/{periods[1]})>{cos_value} && COS(2*3.14159265359*((STOP)/(86400)+ 51910-{t0s[1]} - {phase-1}*{periods[1]}*{1/phase_bins})/{periods[1]})>{cos_value} && (DATA_QUAL>0) && (LAT_CONFIG==1)" roicut=no"""

    def gtselect_script(self, phase, ra, dec, radius, tmin, tmax, emin, emax):
        return f"""gtselect infile=./{phase}.fits outfile=./ft1_00.fits ra={ra} dec={dec} rad={radius} tmin={tmin} tmax={tmax} emin={emin} emax={emax} zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 evtable="EVENTS" chatter=3 clobber=yes debug=no gui=no mode="ql" """

    def gtselect_script_adaptive(self, phase, ra, dec, radius, tmin, tmax, emin, emax,pmin,pmax):
        # retun f"""gtselect infile="+str(ev_file_path)+" outfile=./ft1_00.fits ra="+str(ra)+" dec="+str(dec)+" rad=15 tmin="+str(tmin)+" tmax="+str(tmax)+" phasemin="+str(phases[int(phase),0])+" phasemax="+str(phases[int(phase),1]) + " emin="+str(emin)+" emax="+str(emax)+" zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 evtable=\"EVENTS\" chatter=3 clobber=yes debug=no gui=no mode=\"ql\" """
        return f"""gtselect infile=./{phase}.fits outfile=./ft1_00.fits ra={ra} dec={dec} rad={radius} tmin={tmin} tmax={tmax} emin={emin} emax={emax} phasemin={pmin} phasemax={pmax} zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 evtable="EVENTS" chatter=3 clobber=yes debug=no gui=no mode="ql" """

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

    def gen_header(self,i, working_dir, phase_bins):
        return f"""#!/bin/sh

#SBATCH -p tiny
#SBATCH -N 1
#SBATCH -D {working_dir}/{i}/
#SBATCH --export=MY_FERMI_DIR=/scratch/groups/kargaltsevgrp/lange/4FGL_Make
#SBATCH -t 4:00:00

. /c1/apps/anaconda/2021.05/etc/profile.d/conda.sh

conda activate fermi2
"""


    def gen_closer(self, phase_bins):
        return f"""

touch done.flag
sleep 60
cd ..
COUNT=$(find . -type f -name "*.flag" | wc -l)

if [ "$COUNT" -eq {phase_bins} ]; then
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
#SBATCH -p tiny
#SBATCH -N 1
#SBATCH --export=MY_FERMI_DIR=/scratch/groups/kargaltsevgrp/lange/4FGL_Make
#SBATCH -t 4:00:00


. /c1/apps/anaconda/2021.05/etc/profile.d/conda.sh
conda activate fermipy

python analyze_phases.py
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
    def generate_config(self, phase, local_dir, event_file, sc_file, ra, dec, radius, tmin, tmax, emin, emax, ebins):
        config = {
            "data": {
                "evfile": "./ft1_00.fits",
                "scfile": sc_file,
                "ltcube": "./ltcube_00.fits",
            },
            "binning": {
                "roiwidth": radius,
                "binsz": 0.05,
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
                "galdiff": '/CCAS/home/alexlange/.conda/envs/fermi2/share/fermitools/refdata/fermi/galdiffuse/gll_iem_v07.fits',
                "isodiff": "/CCAS/home/alexlange/.conda/envs/fermi2/share/fermitools/refdata/fermi/galdiffuse/iso_P8R3_SOURCE_V3_v1.txt",
                "catalogs": [
                    "/scratch/kargaltsevgrp/lange/dr4/gll_psc_v35.fit",
                    "/scratch/kargaltsevgrp/lange/ext/XML/FornaxA.xml","/scratch/kargaltsevgrp/lange/ext/XML/MSH15-56PWN.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1109.4-6115.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ2301.9+5855.xml","/scratch/kargaltsevgrp/lange/ext/XML/S147.xml","/scratch/kargaltsevgrp/lange/ext/XML/HB3.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ1723.5-0501.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1553.8-5325.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1836.5-0651.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1857.7+0246.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1655.5-4737.xml","/scratch/kargaltsevgrp/lange/ext/XML/G279.0+1.1.xml","/scratch/kargaltsevgrp/lange/ext/XML/W3.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1808-204.xml","/scratch/kargaltsevgrp/lange/ext/XML/HB9.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1640-465.xml","/scratch/kargaltsevgrp/lange/ext/XML/G150.3Gauss.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1614-518.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1745.8-3028.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1355.1-6420.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ2304.0+5406.xml","/scratch/kargaltsevgrp/lange/ext/XML/HB21Ambrogi.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ0851.9-4620.xml","/scratch/kargaltsevgrp/lange/ext/XML/G106.3+2.7.xml","/scratch/kargaltsevgrp/lange/ext/XML/SMC-Galaxy.xml","/scratch/kargaltsevgrp/lange/ext/XML/RXJ1713-3946.xml","/scratch/kargaltsevgrp/lange/ext/XML/G296.5+10.0.xml","/scratch/kargaltsevgrp/lange/ext/XML/W41.xml","/scratch/kargaltsevgrp/lange/ext/XML/RCW86.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1834.1-0706.xml","/scratch/kargaltsevgrp/lange/ext/XML/gammaCygni.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1303-631.xml","/scratch/kargaltsevgrp/lange/ext/XML/LMC-Galaxy.xml","/scratch/kargaltsevgrp/lange/ext/XML/LMC-North.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1023.3-5747.xml","/scratch/kargaltsevgrp/lange/ext/XML/IC443.xml","/scratch/kargaltsevgrp/lange/ext/XML/LMC-FarWest.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1213.3-6240.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ2208.4+6443.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ0822.1-4253.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1813-178.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ0534.5+2201.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1633.0-4746.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ1501.0-6310.xml","/scratch/kargaltsevgrp/lange/ext/XML/Monoceros.xml","/scratch/kargaltsevgrp/lange/ext/XML/CygnusCocoon.xml","/scratch/kargaltsevgrp/lange/ext/XML/G42.8+0.6.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1652.2-4633.xml","/scratch/kargaltsevgrp/lange/ext/XML/MSH15-56SNR.xml","/scratch/kargaltsevgrp/lange/ext/XML/W51C.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1514.2-5909.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1507.9-6228.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1420.3-6046.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ1626.9-2431.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1409.1-6121.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1534-571.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ2129.9+5833.xml","/scratch/kargaltsevgrp/lange/ext/XML/W30.xml","/scratch/kargaltsevgrp/lange/ext/XML/Kes73.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1636.3-4731.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1841-055.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1804.7-2144.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1631.6-4756.xml","/scratch/kargaltsevgrp/lange/ext/XML/W28.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ1642.1-5428.xml","/scratch/kargaltsevgrp/lange/ext/XML/CenALobes.xml","/scratch/kargaltsevgrp/lange/ext/XML/Rosette.xml","/scratch/kargaltsevgrp/lange/ext/XML/CygnusLoop.xml","/scratch/kargaltsevgrp/lange/ext/XML/LMC-30DorWest.xml","/scratch/kargaltsevgrp/lange/ext/XML/FHESJ1741.6-3917.xml","/scratch/kargaltsevgrp/lange/ext/XML/Kes79.xml","/scratch/kargaltsevgrp/lange/ext/XML/W44.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1036.3-5833.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1616-508.xml","/scratch/kargaltsevgrp/lange/ext/XML/FGESJ1838.9-0704.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1809-193.xml","/scratch/kargaltsevgrp/lange/ext/XML/VelaX_radio.xml","/scratch/kargaltsevgrp/lange/ext/XML/HESSJ1825Grondin.xml"
                ]
            }
        }
        config_path = os.path.join(local_dir, f"config.yaml")
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        self.status_text.append(f"📝 Config saved: {config_path}")
        self.close()
    def generate_analysis_script(self, i, local_dir,working_dir,phase_bins):
        """Write a phase-analysis driver Python script."""
        source_name = "4FGL J2032.4+4056"
        script_content = f"""import os
import re
import numpy as np
import matplotlib.pyplot as plt
from math import *  # better to import only what you need
from fermipy.gtanalysis import GTAnalysis

os.environ["LATEXTDIR"] = "/scratch/kargaltsevgrp/lange/ext/"

DEBUG = True
VERBOSITY = 4 if DEBUG else 0

def double_fig(*args):
    out = [np.array([args[0], args[0] + 1]).flatten()]
    for arg in args[1:]:
        out.append(np.array([arg, arg]).flatten())
    return out

def setup_gta(directory):
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

    gta.free_sources(distance=15, free=False)
    # gta.free_source('4FGL J2032.4+4056', pars='norm')
    gta.free_source('{source_name}', pars='norm')

    gta.fit(min_fit_quality=3, optimizer='MINUIT', retries=1000, tol=1e-8)
    gta.write_roi('norm', make_plots=True)
    return gta


def analyze_phases():
    gta_list = []
    base_dir = '{working_dir}'

    for directory, _, _ in os.walk(base_dir):
        if directory == base_dir:
            continue
        gta = setup_gta(directory)
        gta_list.append(gta)
    return gta_list

def load_data_and_plot():
    fluxes, flux_err, ts = [], [], []
    num_bins = {phase_bins}
    spec_params = np.zeros((num_bins, 5))
    spec_errs = np.zeros((num_bins, 5))

    for i in range(num_bins):
        p = np.load(
            f'{working_dir}/{{i + 1}}/norm.npy',
            allow_pickle=True
        ).flat[0]

        src = p['sources'][{source_name}]
        fluxes.append(src['flux'])
        flux_err.append(src['flux_err'])
        ts.append(src['ts'])

        spec_params[i, 0] = src['spectral_pars']['norm']['value']
        spec_params[i, 1] = src['spectral_pars']['alpha']['value']
        spec_params[i, 2] = src['spectral_pars']['beta']['value']
        spec_params[i, 3] = src['spectral_pars']['Eb']['value']

        spec_errs[i, 0] = src['spectral_pars']['norm']['error']
        spec_errs[i, 1] = src['spectral_pars']['alpha']['error']
        spec_errs[i, 2] = src['spectral_pars']['beta']['error']
        spec_errs[i, 3] = src['spectral_pars']['Eb']['error']

    phase = np.arange(0, 1, 1 / num_bins)
    phase = np.append(phase, phase + 1)

    fluxes = np.append(fluxes, fluxes)
    flux_err = np.append(flux_err, flux_err)
    ts = np.append(ts, ts)
    spec_params = np.vstack([spec_params, spec_params])
    spec_errs = np.vstack([spec_errs, spec_errs])

    fig, axes = plt.subplots(4, 1, figsize=(20, 24), constrained_layout=True)
    ax1, ax2, ax3, axts = axes

    ax1.step(phase, fluxes * 1e8, "k", where='mid')
    ax1.errorbar(phase, fluxes * 1e8, yerr=flux_err * 1e8, fmt="k+")
    ax1.set_ylabel(r"Flux ($10^{{-8}}$ Ph cm$^{{-2}}$ s$^{{-1}}$)", fontsize=32)
    ax1.legend(["(a)"], fontsize=20, frameon=False)

    ax2.step(phase, spec_params[:, 1], "k", where='mid')
    ax2.errorbar(phase, spec_params[:, 1], yerr=spec_errs[:, 1], fmt="k+")
    ax2.set_ylabel(r'$\alpha$', fontsize=32)
    ax2.legend(["(b)"], fontsize=20, frameon=False)

    ax3.step(phase, spec_params[:, 2], "k", where='mid')
    ax3.errorbar(phase, spec_params[:, 2], yerr=spec_errs[:, 2], fmt="k+")
    ax3.set_ylabel(r"$\beta$", fontsize=32)
    ax3.legend(["(c)"], fontsize=20, frameon=False)

    axts.step(phase, ts, "k", where='mid')
    axts.set_ylabel("TS", fontsize=28)
    axts.legend(["(d)"], fontsize=20, frameon=False)

    for ax in (ax1, ax2, ax3, axts):
        ax.set_xlim(0, 2)
        ax.axvline(1, color="gray", linestyle="--")
        ax.tick_params(axis='both', labelsize=24)

    ax1.set_xticks([])
    ax2.set_xticks([])
    ax3.set_xticks([])
    plt.xlabel("Phase", fontsize=28)
    plt.tight_layout()
    plt.savefig("test.png")

    return spec_params, spec_errs, phase, fluxes, flux_err, ts

if __name__ == "__main__":
    # user_input = input("Recalculate everything? (Enter=No, any key=Yes): ").strip()
    # if user_input == "":
        # pars, errs, phase, fluxes, flux_err, ts = load_data_and_plot()
    # else:
        analyze_phases()
        pars, errs, phase, fluxes, flux_err, ts = load_data_and_plot()

"""
        script_path = os.path.join(local_dir, "analyze_phases.py")
        with open(script_path, "w") as f:
            f.write(script_content)
        self.status_text.append(f"🐍 Analysis script written: {script_path}")






def create_ssh_client(hostname, username, key_filename):
    """Creates and returns an SSH client connection using key authentication."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Accept new host keys automatically
    ssh.connect(hostname, username=username, key_filename=os.path.expanduser(key_filename))
    return ssh

def scp_transfer(LOCAL_PATH, REMOTE_PATH):
    """Transfers all .sh files in LOCAL_PATH to the remote server via SCP."""
    try:
        ssh = create_ssh_client(SSH_HOST, SSH_USERNAME, SSH_KEY_PATH)
        scp = SCPClient(ssh.get_transport())

        # List all .sh files in LOCAL_PATH
        files_to_transfer = [f for f in os.listdir(LOCAL_PATH) if f.endswith(".sh") or f.endswith(".yaml") or f.endswith("analyze_phases.py")]

        if not files_to_transfer:
            print("❌ No .sh files found to transfer.")
            return

        # SCP Transfer
        for file in files_to_transfer:
            local_file_path = os.path.join(LOCAL_PATH, file)
            remote_file_path = os.path.join(REMOTE_PATH, file)
            scp.put(local_file_path, remote_file_path)
            print(f"📤 Uploaded: {file} → {REMOTE_PATH}")

        scp.close()
        commands = f"""
        cd {REMOTE_PATH} &&
        for file in *.sh; do
            echo "Submitting job: $file"
            sbatch "$file"
        done
        """

        stdin, stdout, stderr = ssh.exec_command(commands)
        print(stdout.read().decode())  # Print output from the command
        print(stderr.read().decode())  # Print any errors
        ssh.close()
        print(f"✅ All scripts uploaded successfully to {SSH_HOST}:{REMOTE_PATH}")

    except Exception as e:
        print(f"⚠️ SCP Upload Error: {e}")


# Run the app
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FermiScriptGenerator()
    window.show()

    app.exec_()
    for i in range(2, 0, -1):
        print(f"⏳ Transferring scripts in {i} seconds...", end="\r")
        time.sleep(1)
    print("\n🚀 Starting SCP transfer now!")
    # self.close()
    # sys.exit()
