#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jun 26 17:35:03 2025

@author: alexlange
"""

#!/usr/bin/env python3

import os
import json
import argparse
import time
import numpy as np
import paramiko
from scp import SCPClient

# ========== SSH CONFIG ==========
SSH_HOST = "pegasus.arc.gwu.edu"
SSH_USERNAME = "alexlange"
SSH_KEY_PATH = os.path.expanduser("~/.ssh/id_rsa.pub")

# ========== SCRIPT GENERATOR ==========

def cos_value(phase_bins):
    return np.cos(360 / (2 * phase_bins) / 180 * np.pi)

def gen_script(phase, bins, t0, period, event_file, sc_file):
    cosval = cos_value(bins)
    return f"""gtmktime apply_filter=yes evfile={event_file} scfile={sc_file} outfile=./{phase}.fits \\
filter="COS(2*3.14159265359*(START/(86400)+ 51910-{t0} - {phase-1}*{period}*{1/bins})/{period})>{cosval} \\
&& COS(2*3.14159265359*(STOP/(86400)+ 51910-{t0} - {phase-1}*{period}*{1/bins})/{period})>{cosval} \\
&& (DATA_QUAL>0) && (LAT_CONFIG==1)" roicut=no"""

def gen_header(i, remote_dir):
    return f"""#!/bin/sh
#SBATCH -p tiny
#SBATCH -N 1
#SBATCH -D {remote_dir}/{i}/
#SBATCH --export=MY_FERMI_DIR=/scratch/groups/kargaltsevgrp/lange/4FGL_Make
#SBATCH -t 4:00:00

. /c1/apps/anaconda/2021.05/etc/profile.d/conda.sh
conda activate fermi2
"""

def gtselect_script(phase, ra, dec, rad, tmin, tmax, emin, emax):
    return f"""gtselect infile=./{phase}.fits outfile=./ft1_00.fits ra={ra} dec={dec} rad={rad} \\
tmin={tmin} tmax={tmax} emin={emin} emax={emax} zmin=0.0 zmax=90.0 \\
evclass=128 evtype=3 convtype=-1 evtable="EVENTS" chatter=3 clobber=yes mode="ql" """

def gtbin_script(sc_file, emin, emax, ebins, ra, dec):
    return f"""gtbin evfile=./ft1_00.fits scfile={sc_file} outfile=./ccube_00.fits \\
algorithm="ccube" ebinalg="LOG" emin={emin} emax={emax} enumbins={ebins} \\
nxpix=200 nypix=200 binsz=0.1 coordsys="CEL" xref={ra} yref={dec} proj="AIT" chatter=3 clobber=yes mode="ql" """

def gtltcube_script(sc_file, tmin, tmax):
    return f"""gtltcube evfile=./ft1_00.fits evtable="EVENTS" scfile={sc_file} \\
outfile=./ltcube_00.fits dcostheta=0.025 binsz=1.0 phibins=0 \\
tmin={tmin} tmax={tmax} file_version="1" chatter=2 clobber=yes mode="ql" """

def create_ssh_client():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SSH_HOST, username=SSH_USERNAME, key_filename=SSH_KEY_PATH)
    return ssh

def scp_transfer(local_dir, remote_dir):
    ssh = create_ssh_client()
    scp = SCPClient(ssh.get_transport())

    files = [f for f in os.listdir(local_dir) if f.endswith(".sh")]
    if not files:
        print("❌ No .sh files found.")
        return

    for f in files:
        scp.put(os.path.join(local_dir, f), os.path.join(remote_dir, f))
        print(f"📤 Uploaded: {f} → {remote_dir}")

    commands = f"""
    cd {remote_dir} &&
    for file in *.sh; do
        echo "Submitting $file"
        sbatch "$file"
    done
    """
    stdin, stdout, stderr = ssh.exec_command(commands)
    print(stdout.read().decode())
    print(stderr.read().decode())
    ssh.close()

# ========== CLI ==========

def main():
    parser = argparse.ArgumentParser(description="Generate and optionally upload phase-resolved Fermi scripts.")
    parser.add_argument("settings", help="Path to the settings JSON file.")
    parser.add_argument("--upload", action="store_true", help="Upload and submit via SCP/SLURM.")
    args = parser.parse_args()

    with open(args.settings, "r") as f:
        settings = json.load(f)

    required_fields = [
        "Period", "T0", "RA", "DEC", "Radius",
        "Min Time (MET)", "Max Time (MET)",
        "Min Energy", "Max Energy", "Number of Energy Bins",
        "Remote Directory", "Local Directory",
        "Spacecraft File", "Event File",
        "Number of Phase Bins"
    ]

    for key in required_fields:
        if key not in settings:
            raise ValueError(f"Missing required setting: {key}")

    # Extract settings
    period = float(settings["Period"])
    t0 = float(settings["T0"])
    ra = float(settings["RA"])
    dec = float(settings["DEC"])
    rad = float(settings["Radius"])
    tmin = float(settings["Min Time (MET)"])
    tmax = float(settings["Max Time (MET)"])
    emin = int(settings["Min Energy"])
    emax = int(settings["Max Energy"])
    ebins = int(settings["Number of Energy Bins"])
    remote_dir = settings["Remote Directory"]
    local_dir = settings["Local Directory"]
    sc_file = settings["Spacecraft File"]
    event_file = settings["Event File"]
    phase_bins = int(settings["Number of Phase Bins"])

    os.makedirs(local_dir, exist_ok=True)

    for i in range(1, phase_bins + 1):
        script = "\n\n".join([
            gen_header(i, remote_dir),
            gen_script(i, phase_bins, t0, period, event_file, sc_file),
            gtselect_script(i, ra, dec, rad, tmin, tmax, emin, emax),
            gtbin_script(sc_file, emin, emax, ebins, ra, dec),
            gtltcube_script(sc_file, tmin, tmax)
        ])

        script_path = os.path.join(local_dir, f"phase_{i}.sh")
        with open(script_path, "w") as f:
            f.write(script)
        print(f"✅ Script generated: {script_path}")

    if args.upload:
        print("🚀 Uploading scripts to cluster...")
        time.sleep(3)
        scp_transfer(local_dir, remote_dir)

if __name__ == "__main__":
    main()
