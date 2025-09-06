#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple RTL-SDR test using the same approach as your working noaa.sh
"""
import subprocess
import tempfile
import numpy as np
import os

def test_noaa_frequency():
    """Test NOAA frequency the same way as your working script"""
    print("📻 Testing NOAA 162.550 MHz (same as your working noaa.sh)")
    print("=" * 50)
    
    # Create a temporary file
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    
    try:
        # Same command as your working script but capture to file for 3 seconds
        # Redirect stderr to /dev/null like your script does
        cmd = [
            "timeout", "3s",
            "rtl_fm", 
            "-f", "162550000", 
            "-M", "fm", 
            "-s", "22050", 
            "-r", "22050", 
            "-"
        ]
        
        print(f"🔧 Running: {' '.join(cmd)}")
        
        with open(tmp.name, "wb") as f:
            # Redirect stderr to devnull to avoid mixing with audio data
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL)
        
        # Check what we got
        file_size = os.path.getsize(tmp.name)
        print(f"📊 Captured {file_size} bytes of pure audio data")
        
        if file_size > 0:
            # Read and analyze the data
            with open(tmp.name, "rb") as f:
                data = np.frombuffer(f.read(), dtype=np.int16)
            
            if len(data) > 0:
                rms = np.sqrt(np.mean((data/32768.0) ** 2))
                print(f"✅ SUCCESS! RMS: {rms:.6f}")
                print(f"📈 Sample count: {len(data)}")
                print(f"📊 Data range: {data.min()} to {data.max()}")
                
                if rms > 0.003:
                    print("🔊 Strong signal detected!")
                elif rms > 0.001:
                    print("📡 Weak signal detected")
                else:
                    print("💤 Very weak/no signal")
                    
                return rms
            else:
                print("❌ No data in file")
        else:
            print("❌ Zero bytes captured - RTL-SDR might not be working")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        os.unlink(tmp.name)
    
    return 0.0

if __name__ == "__main__":
    rms = test_noaa_frequency()
    print(f"\n🎯 Result: RMS = {rms:.6f}")
    if rms > 0:
        print("✅ RTL-SDR is working! The scanner should work too.")
    else:
        print("❌ Something's still wrong...")
