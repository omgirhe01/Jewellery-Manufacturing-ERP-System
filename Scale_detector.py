"""
scale_detector.py — Auto-Detect RS232 Scale on Windows
=======================================================
Ye script automatically:
1. Sab available COM ports dhundta hai
2. Har port par har baud rate try karta hai
3. Monitors scale response
4. Reports the correct SCALE_PORT and SCALE_BAUDRATE settings

USAGE:
  python scale_detector.py

REQUIREMENTS:
  pip install pyserial
"""

import serial
import serial.tools.list_ports
import time
import re
import sys

# All common baud rates — most common first
BAUD_RATES = [9600, 4800, 2400, 19200, 1200, 38400, 57600, 115200]

# Commands to trigger scale output
TRIGGER_COMMANDS = [
    b'SI\r\n',    # Mettler Toledo / Sartorius — Send Immediate
    b'P\r\n',     # Most scales — Print command
    b'\r\n',      # CR+LF only
    b'W\r\n',     # Some Chinese/Indian scales
    b'ESC p',     # Some Ohaus scales
]

CYAN  = '\033[96m'
GREEN = '\033[92m'
YELLOW= '\033[93m'
RED   = '\033[91m'
RESET = '\033[0m'
BOLD  = '\033[1m'

def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════╗
║      JEWELLERY ERP — Scale Auto-Detector             ║
║      RS232 Scale Port & Baud Rate Finder             ║
╚══════════════════════════════════════════════════════╝{RESET}
""")

def list_ports():
    """List all available COM ports on Windows."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print(f"{RED}❌ No COM ports found!{RESET}")
        print("""
Possible reasons:
  1. Scale RS232 cable is not connected
  2. USB-to-RS232 adapter driver is not installed
  
Fix:
  - Turn on the scale and properly connect the RS232 cable
  - If using a USB-to-RS232 adapter, install the driver first
    (Prolific PL2303 ya FTDI FT232 driver)
  - Check 'Ports (COM & LPT)' in Device Manager
""")
        return []
    
    print(f"{CYAN}Found {len(ports)} COM port(s):{RESET}")
    for p in sorted(ports):
        mark = "★" if any(kw in (p.description or '').lower() 
                          for kw in ['usb', 'prolific', 'ftdi', 'cp210', 'serial']) else " "
        print(f"  {YELLOW}{mark} {p.device:8}{RESET} — {p.description}")
    print()
    return sorted(ports, key=lambda p: p.device)

def try_read(port_name: str, baud: int, timeout: float = 1.5) -> str:
    """Try to open port at given baud and get a reading."""
    try:
        ser = serial.Serial(
            port=port_name,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=1.0,
        )
        ser.reset_input_buffer()
        
        # Try each trigger command
        for cmd in TRIGGER_COMMANDS:
            try:
                ser.write(cmd)
                time.sleep(0.15)
                raw = ser.read(ser.in_waiting or 64)
                if raw:
                    line = raw.decode('ascii', errors='ignore').strip()
                    if line:
                        ser.close()
                        return line
            except Exception:
                continue
        
        # If no trigger worked, wait passively
        time.sleep(1.0)
        raw = ser.read(ser.in_waiting or 128)
        ser.close()
        if raw:
            return raw.decode('ascii', errors='ignore').strip()
        return ""
    except serial.SerialException as e:
        return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: {e}"

def looks_like_weight(text: str) -> bool:
    """Check if response looks like a weight reading."""
    if not text or text.startswith("ERROR"):
        return False
    # Must contain a number with decimal point
    if not re.search(r'\d+\.\d+', text):
        return False
    # Must contain 'g' or 'kg' or 'mg' or weight-related patterns
    has_unit = bool(re.search(r'\b(g|kg|mg|ct|lb)\b', text, re.IGNORECASE))
    has_weight_pattern = bool(re.search(r'(ST|GS|SBI|\+0+\d)', text, re.IGNORECASE))
    has_reasonable_number = False
    
    # Check if number is in reasonable jewelry weight range (0.001g to 5000g)
    matches = re.findall(r'[\d]+\.[\d]+', text)
    for m in matches:
        val = float(m)
        if 0.001 <= val <= 5000:
            has_reasonable_number = True
            break
    
    return (has_unit or has_weight_pattern) and has_reasonable_number

def detect():
    banner()
    
    # Step 1: List ports
    ports = list_ports()
    if not ports:
        input("Press Enter to exit...")
        sys.exit(1)
    
    print(f"{BOLD}Scanning all ports at all baud rates...{RESET}")
    print(f"{YELLOW}(Scale ON hona chahiye aur idle hona chahiye){RESET}\n")
    
    results = []
    
    for port_info in ports:
        port = port_info.device
        print(f"  Testing {CYAN}{port}{RESET} ({port_info.description})")
        
        for baud in BAUD_RATES:
            sys.stdout.write(f"    Baud {baud:7}... ")
            sys.stdout.flush()
            
            response = try_read(port, baud, timeout=1.5)
            
            if response.startswith("ERROR"):
                err_short = response[:50]
                # Port in use or access denied — skip remaining bauds
                if "Access" in response or "denied" in response or "in use" in response:
                    print(f"{RED}Port busy/locked{RESET}")
                    break
                print(f"{RED}✗{RESET} {err_short}")
                continue
            
            if response and looks_like_weight(response):
                print(f"{GREEN}✅ WEIGHT DATA: '{response}'{RESET}")
                results.append({
                    "port": port,
                    "baud": baud,
                    "response": response,
                    "description": port_info.description,
                })
                break  # Found baud for this port, move to next
            elif response:
                print(f"{YELLOW}? Data (not weight): '{response[:40]}'{RESET}")
            else:
                print(f"✗ No response")
    
    # Results
    print(f"\n{'═'*56}")
    
    if not results:
        print(f"""
{RED}{BOLD}❌ Scale not detected on any port.{RESET}

Troubleshooting:
  1. Scale ON hai? Check power
  2. RS232 cable properly connected hai? Try re-plugging
  3. Scale ka RS232 port enable hai? (some scales have menu option)
  4. Is another application using the scale? Close it
  5. Try a different RS232 cable (straight vs null modem)
  
Try triggering the print command manually using scale buttons —
koi output print/display hona chahiye.
""")
    else:
        print(f"\n{GREEN}{BOLD}✅ SCALE DETECTED!{RESET}\n")
        best = results[0]
        
        print(f"""
{BOLD}Your scale settings:{RESET}

  {CYAN}SCALE_PORT    = {best['port']}{RESET}
  {CYAN}SCALE_BAUDRATE = {best['baud']}{RESET}

{BOLD}Copy these to your backend/.env file:{RESET}

{YELLOW}SCALE_SIMULATION_MODE=false
SCALE_PORT={best['port']}
SCALE_BAUDRATE={best['baud']}{RESET}

Scale response was: {GREEN}'{best['response']}'{RESET}
""")
        
        if len(results) > 1:
            print(f"Other detections:")
            for r in results[1:]:
                print(f"  {r['port']} @ {r['baud']}: '{r['response']}'")
    
    print('═'*56)
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    try:
        detect()
    except KeyboardInterrupt:
        print("\nCancelled.")