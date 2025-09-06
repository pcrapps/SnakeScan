#!/usr/bin/env python3
import subprocess
import numpy as np
import datetime
import csv
import tempfile
import os
import time

# ---- Co# ---- Config ----
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
        time.sleep(1) ----
# Generate 2m ham band frequencies: 144.000 - 148.000 MHz in 25 kHz steps
FREQS = []

# 2m ham band: 144-148 MHz
for freq_mhz in range(144000, 148001, 25):  # 25 kHz steps (common channel spacing)
    FREQS.append(freq_mhz * 1000)  # Convert to Hz

# Aviation frequencies (118-137 MHz)
# Common aviation channels in 25 kHz steps
aviation_freqs = []

# Tower frequencies (most common range)
for freq_khz in range(118000, 137000, 25):  # 118.000 - 137.000 MHz in 25 kHz steps
    aviation_freqs.append(freq_khz * 1000)  # Convert to Hz

# Add specific common aviation frequencies that might not be in the range
common_aviation = [
    121500000,  # 121.500 MHz - Emergency frequency
    122800000,  # 122.800 MHz - Unicom
    123000000,  # 123.000 MHz - Common tower
    124100000,  # 124.100 MHz - Common approach
    125300000,  # 125.300 MHz - Common approach
    126200000,  # 126.200 MHz - Military
    127800000,  # 127.800 MHz - Common tower
    132050000,  # 132.050 MHz - Common approach
    135100000,  # 135.100 MHz - Common approach
]

# Add aviation frequencies to main list
FREQS.extend(aviation_freqs)

# Add NOAA Weather Radio
FREQS.append(162550000)  # NOAA Weather Radio

# Sort all frequencies
FREQS.sort()

DWELL = 1         # seconds per frequency (reduced for faster scanning)
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

def get_band_label(freq):
    """Return a label identifying the frequency band"""
    freq_mhz = freq / 1e6
    if 118.0 <= freq_mhz <= 137.0:
        if freq == 121500000:
            return "[AVIATION-EMERGENCY]"
        elif freq == 122800000:
            return "[AVIATION-UNICOM]"
        else:
            return "[AVIATION]"
    elif 144.0 <= freq_mhz <= 148.0:
        return "[2M-HAM]"
    elif freq == 162550000:
        return "[NOAA]"
    else:
        return ""

def measure_rms(rawfile):
    """Compute RMS amplitude of raw int16 audio"""
    with open(rawfile, "rb") as f:
        data = np.frombuffer(f.read(), dtype=np.int16)
    if data.size == 0:
        return 0.0
    return np.sqrt(np.mean((data/32768.0) ** 2))

def scan_freq(freq, dwell_time=DWELL):
    """Capture dwell_time seconds, measure RMS, return activity status"""
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    cmd = [
        "timeout", f"{dwell_time}s",
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
ham_count = sum(1 for f in FREQS if 144e6 <= f <= 148e6)
aviation_count = sum(1 for f in FREQS if 118e6 <= f <= 137e6)
noaa_count = sum(1 for f in FREQS if f == 162550000)

print(f"📡 SDR scanner starting: {len(FREQS)} total frequencies")
print(f"   ✈️  Aviation: {aviation_count} freqs (118-137 MHz)")
print(f"   � 2m Ham: {ham_count} freqs (144-148 MHz)")
print(f"   🌤️  NOAA: {noaa_count} freq (162.550 MHz)")
print(f"   ⏱️  {DWELL}s dwell (5s for NOAA), RMS>{RMS_THRESH}")

with open(LOGFILE, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["timestamp", "frequency_Hz", "frequency_MHz", "band", "rms", "active"])
    pass_count = 0
    while True:
        pass_count += 1
        print(f"\n🔄 Pass #{pass_count}")
        for i, f in enumerate(FREQS):
            disp = freq_to_str(f)
            band_label = get_band_label(f)
            # Use 5 seconds for NOAA weather radio, reduced time for others
            dwell_time = 5 if f == 162550000 else DWELL
            print(f"🔍 [{i+1:3d}/{len(FREQS)}] {disp} {band_label} ({dwell_time}s) ...", end=" ")
            rms = scan_freq(f, dwell_time)
            active = rms > RMS_THRESH
            if active:
                print(f"✅ ACTIVE (RMS={rms:.4f})")
                writer.writerow([datetime.datetime.now().isoformat(), f, f/1e6, band_label.strip('[]'), rms, 1])
                csvfile.flush()
                hold_listen(f, HOLD)
            else:
                print(f"💤 silent (RMS={rms:.4f})")
                writer.writerow([datetime.datetime.now().isoformat(), f, f/1e6, band_label.strip('[]'), rms, 0])
                csvfile.flush()
        print(f"⏸️  Pass #{pass_count} complete - pausing 1s before next pass")
        time.sleep(1)  # pause between passes
