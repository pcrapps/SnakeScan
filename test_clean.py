#!/usr/bin/env python3
"""
Simple RTL-SDR test using the same approach as your working noaa.sh
"""
import subprocess
import tempfile
import numpy as np
import os

def test_noaa_frequency():
    """Test NOAA frequency the same way as your working script"""
    print("Testing NOAA 162.550 MHz (same as your working noaa.sh)")
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
        
        print("Running: {}".format(' '.join(cmd)))
        
        with open(tmp.name, "wb") as f:
            # Redirect stderr to devnull to avoid mixing with audio data
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL)
        
        # Check what we got
        file_size = os.path.getsize(tmp.name)
        print("Captured {} bytes of pure audio data".format(file_size))
        
        if file_size > 0:
            # Read and analyze the data
            with open(tmp.name, "rb") as f:
                data = np.frombuffer(f.read(), dtype=np.int16)
            
            if len(data) > 0:
                rms = np.sqrt(np.mean((data/32768.0) ** 2))
                print("SUCCESS! RMS: {:.6f}".format(rms))
                print("Sample count: {}".format(len(data)))
                print("Data range: {} to {}".format(data.min(), data.max()))
                
                if rms > 0.003:
                    print("Strong signal detected!")
                elif rms > 0.001:
                    print("Weak signal detected")
                else:
                    print("Very weak/no signal")
                    
                return rms
            else:
                print("No data in file")
        else:
            print("Zero bytes captured - RTL-SDR might not be working")
        
    except Exception as e:
        print("Error: {}".format(e))
    finally:
        os.unlink(tmp.name)
    
    return 0.0

if __name__ == "__main__":
    rms = test_noaa_frequency()
    print("\nFinal RMS: {:.6f}".format(rms))
    
    if rms > 0.003:
        print("Test PASSED - RTL-SDR is working!")
    else:
        print("Test FAILED - RTL-SDR issues detected")
