#!/usr/bin/env python3
import subprocess
import numpy as np
import datetime
import csv
import tempfile
import os
import time

# ---- Config ----
# 2m Amateur Radio Band Scanner (144-148 MHz)
# FREQS = [162550000]  # NOAA Weather Radio test (confirmed working!)

# Full 2m ham band (144-148 MHz in 25 kHz steps)
FREQS = []
for freq_khz in range(144000, 148001, 25):  # 25 kHz steps
    FREQS.append(freq_khz * 1000)  # Convert to Hz

DWELL = 1.5       # seconds per frequency (faster scanning)
HOLD = 10         # seconds to hold on active channel
GAIN = 25         # rtl_fm gain (reduced from 49.6 to reduce noise)
SQUELCH_DB = 5    # rtl_fm squelch (5dB - filters static but allows signals)
PPM = 0           # frequency correction
SR = 22050        # sample rate
RMS_THRESH = 0.005  # squelch threshold (moderate sensitivity)

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
print(f"📡 2m Amateur Radio Band Scanner")
print(f"�️  Scanning {len(FREQS)} frequencies from 144.000 to 148.000 MHz")
print(f"📻 {DWELL}s dwell time, {HOLD}s hold on active channels")
print(f"🔧 Settings: Gain={GAIN}, Squelch={SQUELCH_DB}dB, RMS threshold>{RMS_THRESH}")
print(f"📊 RTL-SDR confirmed working with NOAA test!")
print(f"🎯 Looking for amateur radio activity on 2m band")
print()

with open(LOGFILE, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["timestamp", "frequency_Hz", "frequency_MHz", "rms", "active"])
    
    scan_count = 0
    while True:
        scan_count += 1
        for i, f in enumerate(FREQS):
            disp = freq_to_str(f)
            print(f"🔍 [Scan #{scan_count:3d}] {disp} ...", end=" ")
            rms = scan_freq(f)
            active = rms > RMS_THRESH
            
            # Show activity status
            if active:
                print(f"ACTIVE! (RMS={rms:.6f})")
                writer.writerow([datetime.datetime.now().isoformat(), f, f/1e6, rms, int(active)])
                csvfile.flush()
                print(f"🎵 Playing audio for {HOLD} seconds...")
                hold_listen(f, HOLD)
            else:
                print(f"quiet (RMS={rms:.6f})")
                writer.writerow([datetime.datetime.now().isoformat(), f, f/1e6, rms, int(active)])
        
        print(f"⏸️  Scan #{scan_count} complete - pausing 1s before next scan")
        time.sleep(1)
