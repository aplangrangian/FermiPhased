import sys
import json
import os
import time
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QTextEdit, QHBoxLayout, QFrame, QCheckBox, QGridLayout, QComboBox
)
from PyQt5.QtCore import Qt  # Add this at the top
import numpy as np

class FermiScriptGenerator(QWidget):
    def __init__(self):
        super().__init__()

        self.settings_file = "settings.json"  # Default settings file
        self.setWindowTitle("Fermi Script Generator")
        self.setGeometry(100, 100, 600, 600)
        self.setStyleSheet("background-color: #0b0d1b; color: white; font-family: Arial;")

        # Main layout
        layout = QVBoxLayout()

        # # Add Fermi Logo
        self.logo_label = QLabel(self)
        self.logo_label.setPixmap(QPixmap("fermi_logo.png").scaled(200, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.logo_label.setAlignment(Qt.AlignCenter)  # Correct
        layout.addWidget(self.logo_label)

        # Title
        title_label = QLabel("Fermi Script Generator")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        self.logo_label.setAlignment(Qt.AlignCenter)  # Correct
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
        self.mode_switch.addItems(["Basic", "Constant Counts", "Multiple Times"])
        self.mode_switch.currentIndexChanged.connect(self.update_mode_fields)
        layout.addWidget(QLabel("Mode:"))
        layout.addWidget(self.mode_switch)

        # Input fields
        self.fields = {}
        self.counts_input_layout = None
        self.phase_bins_layout = None
        self.main_layout = layout
        self.create_input(layout, "Period", "3.90608")
        self.create_input(layout, "T0", "55016.58")
        self.create_input(layout, "RA", "276.5637")
        self.create_input(layout, "DEC", "-14.8496")
        self.create_input(layout, "Radius", "10")
        # self.create_input(layout, "Number of Phase Bins", "14")
        self.create_input(layout, "Min Time (MET)", "239557417")
        self.create_input(layout, "Max Time (MET)", "668413063")
        self.create_input(layout, "Min Energy", "100")
        self.create_input(layout, "Max Energy", "100000")
        self.create_input(layout, "Number of Energy Bins", "14")
        self.phase_bins_layout = self.create_custom_input("Number of Phase Bins", "14")
        layout.insertLayout(11, self.phase_bins_layout)


        # File paths
        self.create_file_input(layout, "Working Directory", is_directory=True)
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

        # Load previous settings if available
        self.load_settings()

    def create_input(self, layout, label, default_value=""):
        """Creates a labeled input field."""
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet("color: #00BFFF;")  # Light blue
        row.addWidget(lbl)
        entry = QLineEdit()
        entry.setText(default_value)
        entry.setStyleSheet("background-color: #1E1E30; color: white; border: 1px solid #00BFFF;")
        row.addWidget(entry)
        self.fields[label] = entry
        layout.addLayout(row)

    def create_custom_input(self, label, default_value=""):
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet("color: #00BFFF;")
            row.addWidget(lbl)
            entry = QLineEdit()
            entry.setText(default_value)
            entry.setStyleSheet("background-color: #1E1E30; color: white; border: 1px solid #00BFFF;")
            row.addWidget(entry)
            self.fields[label] = entry
            return row

    def create_file_input(self, layout, label, is_directory=False):
        """Creates a file or directory input field with a browse button."""
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet("color: #00BFFF;")
        row.addWidget(lbl)
        entry = QLineEdit()
        entry.setStyleSheet("background-color: #1E1E30; color: white; border: 1px solid #00BFFF;")
        row.addWidget(entry)
        browse_button = QPushButton("Browse")
        browse_button.setStyleSheet("background-color: #3A3D66; color: white; padding: 3px;")
        browse_button.clicked.connect(lambda: self.browse_file(entry, is_directory))
        row.addWidget(browse_button)
        self.fields[label] = entry
        layout.addLayout(row)

    def update_mode_fields(self):
        mode = self.mode_switch.currentText()

        # Remove Number of Counts field if it exists
        if self.counts_input_layout:
            for i in reversed(range(self.counts_input_layout.count())):
                widget = self.counts_input_layout.itemAt(i).widget()
                if widget:
                    widget.setParent(None)
            self.main_layout.removeItem(self.counts_input_layout)
            self.counts_input_layout = None
            if "Number of Counts" in self.fields:
                del self.fields["Number of Counts"]

        # Remove Number of Phase Bins if switching to Constant Counts
        if mode == "Constant Counts":
            if self.phase_bins_layout:
                for i in reversed(range(self.phase_bins_layout.count())):
                    widget = self.phase_bins_layout.itemAt(i).widget()
                    if widget:
                        widget.setParent(None)
                self.main_layout.removeItem(self.phase_bins_layout)
                self.phase_bins_layout = None
                if "Number of Phase Bins" in self.fields:
                    del self.fields["Number of Phase Bins"]

            # Add Number of Counts input
            self.counts_input_layout = self.create_custom_input("Number of Counts", "10000")
            self.main_layout.insertLayout(11, self.counts_input_layout)

        else:
            # If switching *back*, re-add Number of Phase Bins if it's missing
            if "Number of Phase Bins" not in self.fields:
                self.phase_bins_layout = self.create_custom_input("Number of Phase Bins", "14")
                self.main_layout.insertLayout(11, self.phase_bins_layout)

            # Placeholder handling
            if mode == "Multiple Times":
                self.fields["Min Time (MET)"].setPlaceholderText("Comma-separated start times")
                self.fields["Max Time (MET)"].setPlaceholderText("Comma-separated end times")
            else:
                self.fields["Min Time (MET)"].setPlaceholderText("")
                self.fields["Max Time (MET)"].setPlaceholderText("")

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

    def generate_scripts(self):
        """Generates the scripts and saves them in the selected working directory."""
        working_dir = self.fields["Working Directory"].text().strip()
        local_dir = self.fields["Local Directory"].text().strip()
        if not working_dir:
            self.status_text.append("⚠️ Error: No working directory selected!")
            return

        try:
            os.makedirs(local_dir, exist_ok=True)

            # Read user input values
            phase_bins = int(self.fields["Number of Phase Bins"].text())
            period = float(self.fields["Period"].text())
            t0 = float(self.fields["T0"].text())
            ra = float(self.fields["RA"].text())
            dec = float(self.fields["DEC"].text())
            rad = float(self.fields["Radius"].text())
            tmin = int(self.fields["Min Time (MET)"].text())
            tmax = int(self.fields["Max Time (MET)"].text())
            emin = int(self.fields["Min Energy"].text())
            emax = int(self.fields["Max Energy"].text())
            ebins = int(self.fields["Number of Energy Bins"].text())
            event_file = self.fields["Event File"].text()
            sc_file = self.fields["Spacecraft File"].text()

            for i in range(1, phase_bins + 1):
                script_content = "\n\n".join([
                    self.gen_header(i, working_dir, phase_bins),
                    self.gen_script(i, phase_bins, ra, dec, t0, period, event_file, sc_file),
                    self.gtselect_script(i, ra, dec, rad, tmin, tmax, emin, emax),
                    self.gtbin_script(i, sc_file, emin, emax, ebins, ra, dec),
                    self.gtltcube_script(i, sc_file, tmin, tmax)
                ])

                script_path = os.path.join(local_dir, f"phase_{i}.sh")
                with open(script_path, "w") as f:
                    f.write(script_content)

            self.status_text.append(f"✅ Scripts successfully saved in: {local_dir}")

        except Exception as e:
            self.status_text.append(f"⚠️ Error: {e}")
        if self.upload_toggle.isChecked():
            self.status_text.append("🚀 Uploading scripts to the cluster...")
            scp_transfer()

    def gen_script(self, phase, phase_bins, ra, dec, t0, period, event_file, sc_file):
        cos_value = np.cos(360 / (2 * phase_bins) / 180 * np.pi)  # Precompute cosine
        return f"""gtmktime apply_filter=yes evfile={event_file} scfile={sc_file} outfile=./{phase}.fits filter="COS(2*3.14159265359*(START/(86400)+ 51910-{t0} - {phase-1}*{period}*{1/phase_bins})/{period})>{cos_value} && COS(2*3.14159265359*(STOP/(86400)+ 51910-{t0} - {phase-1}*{period}*{1/phase_bins})/{period})>{cos_value} && (DATA_QUAL>0) && (LAT_CONFIG==1)" roicut=no"""

    def gtselect_script(self, phase, ra, dec, radius, tmin, tmax, emin, emax):
        return f"""gtselect infile=./{phase}.fits outfile=./ft1_00.fits ra={ra} dec={dec} rad={radius} tmin={tmin} tmax={tmax} emin={emin} emax={emax} zmin=0.0 zmax=90.0 evclass=128 evtype=3 convtype=-1 evtable="EVENTS" chatter=3 clobber=yes debug=no gui=no mode="ql" """

    def gtbin_script(self, phase, sc_file, emin, emax, ebins, ra, dec):
        return f"""gtbin evfile=./ft1_00.fits scfile={sc_file} outfile=./ccube_00.fits algorithm="ccube" ebinalg="LOG" emin={emin} emax={emax} enumbins={ebins} ebinfile=NONE tbinalg="LIN" tbinfile=NONE nxpix=200 nypix=200 binsz=0.1 coordsys="CEL" xref={ra} yref={dec} axisrot=0.0 rafield="RA" decfield="DEC" proj="AIT" hpx_ordering_scheme="RING" hpx_order=3 hpx_ebin=yes hpx_region= evtable="EVENTS" sctable="SC_DATA" efield="ENERGY" tfield="TIME" chatter=3 clobber=yes debug=no gui=no mode="ql" """

    def gtltcube_script(self, phase, sc_file, tmin, tmax):
        return f"""gtltcube evfile=./ft1_00.fits evtable="EVENTS" scfile={sc_file} sctable="SC_DATA" outfile=./ltcube_00.fits dcostheta=0.025 binsz=1.0 phibins=0 tmin={tmin} tmax={tmax} file_version="1" zmin=0.0 zmax=90.0 chatter=2 clobber=yes debug=no gui=no mode="ql" """
    def gen_header(self,i, working_dir, phase_bins):
        return f"""#!/bin/sh

#SBATCH -p tiny
#SBATCH -N 1
#SBATCH -D {working_dir}/{i}/
#SBATCH --export=MY_FERMI_DIR=/scratch/groups/kargaltsevgrp/lange/4FGL_Make
#SBATCH -t 4:00:00

. /c1/apps/anaconda/2021.05/etc/profile.d/conda.sh

conda activate fermi
"""

import paramiko
from scp import SCPClient

# Configuration (Modify these settings)
SSH_HOST = "pegasus.arc.gwu.edu"  # Change this to your actual SSH server (e.g., "192.168.1.1")
SSH_USERNAME = "alexlange"
SSH_KEY_PATH = "~/.ssh/id_rsa.pub"
REMOTE_PATH = "/scratch/kargaltsevgrp/lange/J1702/epoch2/"  # Remote directory on the server
LOCAL_PATH = "/Users/alexlange/Desktop/J1702/epoch2/"  # Directory containing the .sh files (Change if needed)

def create_ssh_client(hostname, username, key_filename):
    """Creates and returns an SSH client connection using key authentication."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Accept new host keys automatically
    ssh.connect(hostname, username=username, key_filename=os.path.expanduser(key_filename))
    return ssh

def scp_transfer():
    """Transfers all .sh files in LOCAL_PATH to the remote server via SCP."""
    try:
        ssh = create_ssh_client(SSH_HOST, SSH_USERNAME, SSH_KEY_PATH)
        scp = SCPClient(ssh.get_transport())

        # List all .sh files in LOCAL_PATH
        files_to_transfer = [f for f in os.listdir(LOCAL_PATH) if f.endswith(".sh")]

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
    for i in range(5, 0, -1):
        print(f"⏳ Transferring scripts in {i} seconds...", end="\r")
        time.sleep(1)
    print("\n🚀 Starting SCP transfer now!")
    # if self.upload_toggle.isChecked():
    #     scp_transfer()
    sys.exit()
