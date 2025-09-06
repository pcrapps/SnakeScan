#!/usr/bin/env python3
"""
RTL-SDR Test Script
Tests if RTL-SDR hardware is connected and working
"""
import subprocess
import tempfile
import os
import numpy as np

def test_rtl_sdr():
    """Test RTL-SDR connectivity and basic functionality"""
    print("🔍 Testing RTL-SDR Hardware...")
    print("=" * 40)
    
    # Test 1: Check if rtl_test is available
    print("1️⃣ Testing rtl_test availability...")
    try:
        result = subprocess.run(["rtl_test", "-t"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✅ rtl_test found and working")
            print(f"📟 Device info: {result.stdout.split(chr(10))[0] if result.stdout else 'No output'}")
        else:
            print("❌ rtl_test failed or no device found")
            print(f"   Error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("✅ rtl_test found (timeout is expected)")
    except FileNotFoundError:
        print("❌ rtl_test not found - install rtl-sdr tools")
        return False
    
    # Test 2: Check if rtl_fm works
    print("\n2️⃣ Testing rtl_fm...")
    try:
        # Test rtl_fm for 2 seconds on 146.520 MHz (2m calling frequency)
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        
        cmd = [
            "timeout", "2s",
            "rtl_fm",
            "-f", "146520000",
            "-M", "fm",
            "-s", "22050",
            "-r", "22050",
            "-g", "49.6",
            "-l", "0",
            "-"
        ]
        
        with open(tmp.name, "wb") as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=5)
        
        # Check if we got any data
        file_size = os.path.getsize(tmp.name)
        print(f"📊 Captured {file_size} bytes in 2 seconds")
        
        if file_size > 0:
            # Analyze the captured data
            with open(tmp.name, "rb") as f:
                data = np.frombuffer(f.read(), dtype=np.int16)
            
            if len(data) > 0:
                rms = np.sqrt(np.mean((data/32768.0) ** 2))
                print(f"✅ RTL-SDR working! RMS level: {rms:.6f}")
                print(f"📈 Data points: {len(data)}")
                print(f"📊 Min/Max values: {data.min()}/{data.max()}")
                
                if rms > 0.001:
                    print("🔊 Significant signal detected - RTL-SDR is receiving!")
                else:
                    print("📻 Low signal - RTL-SDR working but weak/no signal")
            else:
                print("❌ No data captured - check RTL-SDR connection")
        else:
            print("❌ No data captured - RTL-SDR might not be connected")
            print(f"   stderr: {result.stderr.decode()}")
        
        os.unlink(tmp.name)
        return file_size > 0
        
    except Exception as e:
        print(f"❌ rtl_fm test failed: {e}")
        return False
    
    # Test 3: Suggest optimal settings
    print("\n3️⃣ Recommended Settings:")
    print("🔧 For maximum sensitivity:")
    print("   - Gain: 49.6 (maximum)")
    print("   - Squelch: 0 (disabled)")
    print("   - RMS Threshold: 0.001-0.005")
    print("   - Ensure antenna is connected")
    print("   - Try different USB ports")
    
    return True

if __name__ == "__main__":
    test_rtl_sdr()
