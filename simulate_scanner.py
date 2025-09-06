#!/usr/bin/env python3
"""
RTL-SDR Simulated Scanner
Simulates scanner behavior when RTL-SDR hardware issues prevent real scanning
"""
import csv
import datetime
import time
import random
import numpy as np

# Simulate realistic amateur radio activity
def simulate_2m_activity():
    """Simulate 2m ham band activity patterns"""
    
    # Common active frequencies in 2m band
    popular_freqs = [
        146.520,  # National calling frequency
        146.940, 146.880, 146.820,  # Common repeaters
        147.000, 147.120, 147.180,  # More repeaters 
        145.500, 145.230,  # Simplex
        144.200,  # Weak signal
    ]
    
    # Generate frequency list
    freqs = []
    for freq_khz in range(144000, 148001, 25):
        freqs.append(freq_khz / 1000.0)  # MHz
    
    print("📡 2m Ham Band Simulator (RTL-SDR Hardware Issues)")
    print("=" * 50)
    print(f"🎭 Simulating realistic amateur radio activity patterns")
    print(f"📻 {len(freqs)} frequencies (144-148 MHz)")
    print(f"🔧 This shows what you'd see with working RTL-SDR hardware")
    print()
    
    logfile = f"simulated_scan_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"
    
    with open(logfile, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["timestamp", "frequency_Hz", "frequency_MHz", "rms", "active", "simulated"])
        
        pass_count = 0
        while True:
            pass_count += 1
            active_this_pass = 0
            print(f"\n🔄 Simulated Pass #{pass_count}")
            
            for i, freq_mhz in enumerate(freqs):
                freq_hz = int(freq_mhz * 1e6)
                
                # Simulate RMS based on frequency popularity and random activity
                base_noise = random.uniform(0.001, 0.005)  # Background noise
                
                if freq_mhz in popular_freqs:
                    # Popular frequencies more likely to be active
                    if random.random() < 0.15:  # 15% chance of activity
                        signal_strength = random.uniform(0.01, 0.08)
                        rms = base_noise + signal_strength
                        active = True
                    else:
                        rms = base_noise
                        active = False
                else:
                    # Less popular frequencies 
                    if random.random() < 0.02:  # 2% chance of activity
                        signal_strength = random.uniform(0.005, 0.03)
                        rms = base_noise + signal_strength
                        active = True
                    else:
                        rms = base_noise
                        active = False
                
                # Apply threshold
                threshold = 0.008
                active = rms > threshold
                
                if active:
                    active_this_pass += 1
                    print(f"🔍 [{i+1:3d}/{len(freqs)}] {freq_mhz:.3f} MHz ... ✅ ACTIVE (RMS={rms:.6f})")
                    # Simulate holding for 3 seconds
                    print(f"🎵 [SIMULATED] Playing audio for 3 seconds...")
                    time.sleep(0.1)  # Short delay to show realistic timing
                else:
                    if rms > 0.003:
                        print(f"🔍 [{i+1:3d}/{len(freqs)}] {freq_mhz:.3f} MHz ... 🔊 SIGNAL (RMS={rms:.6f}) - below threshold")
                    else:
                        print(f"🔍 [{i+1:3d}/{len(freqs)}] {freq_mhz:.3f} MHz ... 💤 silent (RMS={rms:.6f})")
                
                writer.writerow([datetime.datetime.now().isoformat(), freq_hz, freq_mhz, rms, int(active), 1])
                csvfile.flush()
                
                # Small delay to show scanning
                time.sleep(0.05)
            
            print(f"⏸️  Simulated pass #{pass_count}: {active_this_pass} active frequencies")
            print(f"📊 In real scanner: signals would be played through speakers")
            time.sleep(2)

if __name__ == "__main__":
    try:
        simulate_2m_activity()
    except KeyboardInterrupt:
        print("\n🛑 Simulation stopped")
        print("💡 To fix RTL-SDR hardware issues:")
        print("   1. Unplug/replug RTL-SDR dongle")
        print("   2. Try different USB port")
        print("   3. Close other SDR software")
        print("   4. Run: rtl_test -t")
