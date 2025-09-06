# RTL-SDR Troubleshooting Guide

## Current Status ✅
- **RTL-SDR Device**: Detected (RTLSDRBlog V4, Serial: 00000001)
- **Software**: Installed and working (rtl_test, rtl_fm found)
- **Scanner Code**: Optimized with maximum sensitivity settings
- **Test Signal**: NOAA 162.550 MHz (broadcasts 24/7)

## Issue ❌
**Kernel driver conflict**: `dvb_usb_rtl28xxu` driver is blocking librtlsdr access
**Result**: All RMS values = 0.0000 (no data from hardware)

## Solutions (Try in Order)

### 1. Simple USB Reset 🔌
```bash
# Unplug RTL-SDR dongle from USB
# Wait 10 seconds
# Plug into different USB port (try USB 2.0 vs 3.0)
# Test: rtl_test -t
```

### 2. Kill Conflicting Processes 🔄
```bash
# Check for running SDR software
ps aux | grep -i rtl
ps aux | grep -i sdr

# Kill any found processes
sudo pkill -f rtl_
sudo pkill -f gqrx
sudo pkill -f sdr

# Test: rtl_test -t
```

### 3. Check Driver Installation 📦
```bash
# Ensure proper drivers
brew install librtlsdr
# or
brew install rtl-sdr

# Test: rtl_test -t
```

### 4. Advanced USB Reset 🔧
```bash
# Reset USB subsystem (requires admin)
sudo kextunload -b com.apple.driver.usb.IOUSBHostFamily
sleep 3
sudo kextload -b com.apple.driver.usb.IOUSBHostFamily

# Test: rtl_test -t
```

### 5. Alternative Test Method 🧪
If still not working, try direct rtl_fm test:
```bash
# Test direct capture (2 seconds)
timeout 2s rtl_fm -f 162550000 -M fm -s 22050 -r 22050 -g 49.6 - | head -c 1000
```

Should output binary data if working, error if not.

## Expected Working Behavior ✅

When RTL-SDR is working properly:
- **NOAA Scanner**: RMS values 0.001-0.1+ (not 0.0000)
- **rtl_test**: Shows device info, no "usb_claim_interface error"
- **Audio**: Actually hear NOAA weather broadcasts

## Current Scanner Features 🎯

Your scanner is optimized with:
- **Gain**: 49.6 (maximum)
- **Squelch**: 0dB (disabled)  
- **Threshold**: 0.002 (very sensitive)
- **NOAA Test**: Perfect for verifying connectivity

## Next Steps 📋

1. **Try USB reset first** (easiest solution)
2. **Run NOAA test**: `python main.py`
3. **Look for RMS > 0**: Any non-zero value means RTL-SDR working
4. **Once working**: Switch back to full 2m ham scanning

## Fallback: Simulation Mode 🎭

If hardware issues persist, run:
```bash
python simulate_scanner.py
```
Shows what the scanner would look like with working RTL-SDR hardware.
