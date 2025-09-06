#!/usr/bin/env python3
import subprocess
import numpy as np
import datetime
import csv
import tempfile
import os
import time

# ---- Config ----
# 2m ham band frequencies: 144.000 - 148.000 MHz in 25 kHz steps
FREQS = []
for freq_khz in range(144000, 148001, 25):  # 25 kHz steps
    FREQS.append(freq_khz * 1000)  # Convert to Hz

DWELL = 1         # seconds per frequency
HOLD = 10         # seconds to hold on active channel
GAIN = 35         # rtl_fm gain
SQUELCH_DB = 25   # rtl_fm squelch
PPM = 0           # frequency correction
SR = 22050        # sample rate
RMS_THRESH = 0.012  # squelch threshold

LOGFILE = f"sdr_scan_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"

# ---- Helpers ----
def freq_to_str(f):
    return f"{f/1e6:.3f} MHz"

def measure_rms(rawfile):
    """Compute RMS amplitude of raw int16 audio"""
    with open(rawfile, "rb") as f:
        data = np.frombuffer(f.read(), dtype=np.int16)
    if data.size == 0:
        return 0.0
    return np.sqrt(np.mean((data/32768.0) ** 2))

def scan_freq(freq):
    """Capture DWELL seconds, measure RMS, return activity status"""
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    cmd = [
        "timeout", f"{DWELL}s",
        "rtl_fm",
        "-f", str(freq),
        "-M", "fm",
        "-s", str(SR),
        "-r", str(SR),
        "-g", str(GAIN),
        "-l", str(SQUELCH_DB),
        "-p", str(PPM),
        "-"
    ]
    with open(tmp.name, "wb") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL)
    rms = measure_rms(tmp.name)
    os.unlink(tmp.name)
    return rms

def hold_listen(freq, seconds=HOLD):
    """Play audio from rtl_fm for HOLD seconds"""
    cmd_fm = [
        "timeout", f"{seconds}s",
        "rtl_fm", "-f", str(freq),
        "-M", "fm",
        "-s", str(SR),
        "-r", str(SR),
        "-g", str(GAIN),
        "-l", str(SQUELCH_DB),
        "-p", str(PPM),
        "-"
    ]
    cmd_play = [
        "play", "-q",
        "-r", str(SR), "-t", "raw", "-e", "s", "-b", "16", "-c", "1", "-"
    ]
    fm = subprocess.Popen(cmd_fm, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    subprocess.run(cmd_play, stdin=fm.stdout, stderr=subprocess.DEVNULL)
    fm.wait()

# ---- Main ----
print(f"📡 2m Ham band scanner starting: {len(FREQS)} frequencies (144-148 MHz)")
print(f"📻 {DWELL}s dwell time, RMS threshold > {RMS_THRESH}")

with open(LOGFILE, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["timestamp", "frequency_Hz", "frequency_MHz", "rms", "active"])
    
    while True:
        for i, f in enumerate(FREQS):
            disp = freq_to_str(f)
            print(f"🔍 [{i+1:3d}/{len(FREQS)}] Scanning {disp} ...", end=" ")
            rms = scan_freq(f)
            active = rms > RMS_THRESH
            
            if active:
                print(f"✅ ACTIVE (RMS={rms:.4f})")
                writer.writerow([datetime.datetime.now().isoformat(), f, f/1e6, rms, 1])
                csvfile.flush()
                hold_listen(f, HOLD)
            else:
                print(f"💤 silent (RMS={rms:.4f})")
                writer.writerow([datetime.datetime.now().isoformat(), f, f/1e6, rms, 0])
                csvfile.flush()
        
        print("⏸️  Full band scan complete - pausing 1s before next pass")
        time.sleep(1)
