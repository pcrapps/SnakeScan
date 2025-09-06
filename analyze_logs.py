#!/usr/bin/env python3
"""
Log analyzer for SDR scanner
Shows summary of scanning activity
"""
import csv
import sys
from datetime import datetime
from collections import Counter

def analyze_log(filename):
    """Analyze a scanner log file"""
    try:
        with open(filename, 'r') as f:
            reader = csv.DictReader(f)
            data = list(reader)
        
        print(f"📊 Scanner Log Analysis: {filename}")
        print("=" * 50)
        
        # Basic stats
        total_scans = len(data)
        active_scans = sum(1 for row in data if int(row['active']) == 1)
        silent_scans = total_scans - active_scans
        
        print(f"📈 Total scans: {total_scans}")
        print(f"✅ Active detections: {active_scans}")
        print(f"💤 Silent scans: {silent_scans}")
        print(f"📻 Activity rate: {(active_scans/total_scans*100):.1f}%")
        
        # Frequency range
        frequencies = [float(row['frequency_MHz']) for row in data]
        min_freq = min(frequencies)
        max_freq = max(frequencies)
        print(f"🔢 Frequency range: {min_freq:.3f} - {max_freq:.3f} MHz")
        
        # Time range
        start_time = datetime.fromisoformat(data[0]['timestamp'])
        end_time = datetime.fromisoformat(data[-1]['timestamp'])
        duration = end_time - start_time
        print(f"⏱️  Scan duration: {duration}")
        
        # Most active frequencies
        if active_scans > 0:
            print("\n🔥 Most Active Frequencies:")
            active_freqs = [float(row['frequency_MHz']) for row in data if int(row['active']) == 1]
            freq_counts = Counter(active_freqs)
            for freq, count in freq_counts.most_common(5):
                print(f"   {freq:.3f} MHz: {count} detections")
        
        # RMS statistics
        rms_values = [float(row['rms']) for row in data]
        avg_rms = sum(rms_values) / len(rms_values)
        max_rms = max(rms_values)
        
        print(f"\n📊 RMS Statistics:")
        print(f"   Average RMS: {avg_rms:.6f}")
        print(f"   Max RMS: {max_rms:.6f}")
        print(f"   Active threshold: 0.012")
        
        return data
        
    except Exception as e:
        print(f"❌ Error analyzing log: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        # Find the most recent log file
        import glob
        log_files = glob.glob("sdr_scan_*.csv")
        if log_files:
            filename = max(log_files, key=lambda x: datetime.strptime(x.split('_')[2] + '_' + x.split('_')[3].split('.')[0], '%Y%m%d_%H%M%S'))
            print(f"📁 Using most recent log: {filename}")
        else:
            print("❌ No log files found!")
            sys.exit(1)
    
    analyze_log(filename)
