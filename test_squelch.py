#!/usr/bin/env python3
"""
Test squelch settings with NOAA frequency
"""
import subprocess
import tempfile
import numpy as np
import os

def test_squelch():
    """Test NOAA frequency with current squelch settings"""
    freq = 162550000  # NOAA frequency
    
    # Current settings from main.py
    DWELL = 1.5
    GAIN = 25         # Reduced gain
    SQUELCH_DB = 5    # 5dB squelch (reduced from 10dB)
    SR = 22050
    PPM = 0
    
    print("Testing NOAA 162.550 MHz with squelch settings...")
    print(f"Settings: Gain={GAIN}, Squelch={SQUELCH_DB}dB")
    print()
    
    # Create temporary file
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    
    try:
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
        
        print(f"Running: {' '.join(cmd)}")
        
        with open(tmp.name, "wb") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL)
        
        # Measure RMS
        file_size = os.path.getsize(tmp.name)
        if file_size > 0:
            with open(tmp.name, "rb") as f:
                data = np.frombuffer(f.read(), dtype=np.int16)
            
            if len(data) > 0:
                rms = np.sqrt(np.mean((data/32768.0) ** 2))
                print(f"File size: {file_size} bytes")
                print(f"Samples: {len(data)}")
                print(f"RMS: {rms:.6f}")
                
                if rms > 0.01:
                    print("✅ ACTIVE - Real signal detected through squelch!")
                elif rms > 0.001:
                    print("⚠️  Weak signal - may need to adjust squelch")
                else:
                    print("💤 Quiet - squelch working (or no signal)")
                
                return rms
            else:
                print("❌ No audio data")
        else:
            print("❌ Zero bytes captured")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        os.unlink(tmp.name)
    
    return 0.0

if __name__ == "__main__":
    rms = test_squelch()
    print(f"\nResult: RMS={rms:.6f}")
