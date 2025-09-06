#!/bin/bash
# RTL-SDR Driver Fix for macOS
# This script helps resolve kernel driver conflicts

echo "🔧 RTL-SDR Driver Conflict Resolution"
echo "===================================="
echo ""
echo "✅ RTL-SDR device detected: RTLSDRBlog V4"
echo "❌ Issue: Kernel driver dvb_usb_rtl28xxu is blocking access"
echo ""

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "⚠️  Running as root - this is not recommended for normal use"
fi

echo "🔍 Current USB devices with RTL chipset:"
system_profiler SPUSBDataType | grep -A 10 -B 5 -i rtl

echo ""
echo "💡 Solutions to try (in order):"
echo ""
echo "1️⃣ Unplug and replug the RTL-SDR dongle"
echo "   - Disconnect USB"
echo "   - Wait 5 seconds" 
echo "   - Reconnect to different USB port"
echo ""

echo "2️⃣ Kill any running RTL-SDR processes:"
echo "   sudo pkill -f rtl_"
echo "   sudo pkill -f gqrx"
echo ""

echo "3️⃣ Reset USB subsystem:"
echo "   sudo kextunload -b com.apple.driver.usb.IOUSBHostFamily"
echo "   sleep 2"
echo "   sudo kextload -b com.apple.driver.usb.IOUSBHostFamily"
echo ""

echo "4️⃣ Install proper RTL-SDR drivers (if not done):"
echo "   brew install librtlsdr"
echo "   # or"
echo "   brew install rtl-sdr"
echo ""

echo "5️⃣ Check for conflicting software:"
echo "   - Close any SDR software (GQRX, SDR#, etc.)"
echo "   - Check Activity Monitor for RTL processes"
echo ""

echo "🧪 After trying solutions, test with:"
echo "   rtl_test -t"
echo ""

echo "📱 If still not working, the dongle may need:"
echo "   - Different USB port (USB 2.0 vs 3.0)"
echo "   - Powered USB hub"
echo "   - Different driver installation"
