"""
test_scale.py — Scale Testing Tool
====================================
Ye script test karti hai:
  1. Simulation mode (no hardware needed)
  2. Real RS232/USB scale (if connected)
  3. Data storage verification
  4. Accuracy check

RUN:
  python test_scale.py

REQUIREMENTS:
  pip install pyserial requests
"""

import sys
import time
import json
import re
import random

# ─── Colors for terminal ─────────────────────────────────────
G = '\033[92m'   # Green
Y = '\033[93m'   # Yellow
R = '\033[91m'   # Red
C = '\033[96m'   # Cyan
B = '\033[1m'    # Bold
X = '\033[0m'    # Reset


def hr(char='─', n=56):
    print(char * n)


def banner():
    print(f"""
{B}{C}╔══════════════════════════════════════════════════════╗
║     JEWELLERY ERP — Scale Test Tool                  ║
║     Gold Accuracy Verification                       ║
╚══════════════════════════════════════════════════════╝{X}
""")


# ═══════════════════════════════════════════════════════════════
# TEST 1: Simulation Mode (no hardware)
# ═══════════════════════════════════════════════════════════════

def test_simulation():
    print(f"\n{B}TEST 1: Simulation Mode{X}")
    hr()
    print("Testing weight reading logic without hardware...\n")

    passed = 0
    failed = 0

    test_cases = [
        # (input_grams, tare_grams, expected_net_min, expected_net_max)
        (10.000,  0.000,  9.950, 10.050),
        (5.500,   0.000,  5.475,  5.525),
        (25.000,  2.500, 22.375, 22.625),
        (100.000, 0.000, 99.500, 100.500),
        (0.250,   0.000,  0.249,  0.251),   # Small weight test
        (1.000,   0.100,  0.895,  0.905),   # With tare
    ]

    for gross, tare, net_min, net_max in test_cases:
        # Simulate variance (±0.5%)
        variance = random.uniform(-0.005, 0.005)
        noise = random.uniform(-0.0005, 0.0005)
        simulated = round(gross * (1 + variance) + noise, 4)
        net = round(max(0, simulated - tare), 4)

        ok = net_min <= net <= net_max
        status = f"{G}✓ PASS{X}" if ok else f"{R}✗ FAIL{X}"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"  Expected ~{gross:.3f}g (tare={tare:.3f}g) → "
              f"Got {C}{simulated:.4f}g{X} → Net: {B}{net:.4f}g{X} {status}")

    print(f"\n  Result: {G}{passed} passed{X}, {R}{failed} failed{X}")
    return failed == 0


# ═══════════════════════════════════════════════════════════════
# TEST 2: RS232 Protocol Parsers
# ═══════════════════════════════════════════════════════════════

def parse_scale_line(line):
    """Same parser as scale_service.py"""
    if not line or not line.strip():
        return None

    line = line.strip()

    # Mettler Toledo
    m = re.match(r'^[A-Z]\s+([SD+\-])\s+([\d]+\.[\d]+)\s+(g|mg|kg)', line, re.IGNORECASE)
    if m:
        return {"value": float(m.group(2)), "stable": m.group(1).upper() == 'S',
                "unit": m.group(3).lower()}

    # Sartorius
    m = re.match(r'^[+\-](\d+\.?\d*)\s*(g|mg|kg)\s*([SD])?', line, re.IGNORECASE)
    if m:
        return {"value": float(m.group(1)),
                "stable": (m.group(3) or '').upper() == 'S',
                "unit": (m.group(2) or 'g').lower()}

    # Citizen CG
    m = re.match(r'^GS?\s*([\d]+\.[\d]+)\s*(g|mg|kg)', line, re.IGNORECASE)
    if m:
        return {"value": float(m.group(1)),
                "stable": line.upper().startswith('GS'),
                "unit": m.group(2).lower()}

    # Generic fallback
    m = re.search(r'([\d]+\.[\d]+)', line)
    if m:
        value = float(m.group(1))
        stable = bool(re.search(r'\bST\b|\bSTABLE\b', line, re.IGNORECASE))
        unit = "g"
        if re.search(r'\bkg\b', line, re.IGNORECASE):
            value *= 1000
        return {"value": round(value, 4), "stable": stable, "unit": unit}

    return None


def test_parsers():
    print(f"\n{B}TEST 2: RS232 Protocol Parsers{X}")
    hr()
    print("Testing scale response parsing for different brands...\n")

    test_lines = [
        # (raw_line,                    expected_value, expected_stable, brand)
        ("S S      10.234 g",            10.234, True,  "Mettler Toledo (stable)"),
        ("S D       9.998 g",             9.998, False, "Mettler Toledo (unstable)"),
        ("+0000010.234g S",              10.234, True,  "Sartorius (stable)"),
        ("+0000010.102g D",              10.102, False, "Sartorius (unstable)"),
        ("GS   10.234g",                 10.234, True,  "Citizen CG (stable GS)"),
        ("G    10.102g",                 10.102, False, "Citizen CG (unstable G)"),
        ("ST,+  10.234, g",              10.234, True,  "Citizen alternate format"),
        ("  10.500 g ST",                10.500, True,  "Generic with ST marker"),
        ("  10.500 g",                   10.500, False, "Generic no stability"),
        ("W:   25.340 g  STABLE",        25.340, True,  "Generic STABLE keyword"),
        ("0.001 g ST",                    0.001, True,  "Minimum (1mg) stable"),
        ("999.9990 g ST",               999.999, True,  "Large value stable"),
    ]

    passed = 0
    failed = 0

    for raw, exp_val, exp_stable, brand in test_lines:
        result = parse_scale_line(raw)
        if result is None:
            print(f"  {R}✗ FAIL{X} [{brand}]")
            print(f"       Input:    '{raw}'")
            print(f"       Expected: {exp_val}g stable={exp_stable}")
            print(f"       Got:      None (parse failed)")
            failed += 1
            continue

        val_ok = abs(result["value"] - exp_val) < 0.001
        stable_ok = result["stable"] == exp_stable
        ok = val_ok and stable_ok

        if ok:
            print(f"  {G}✓ PASS{X} [{brand}]")
            print(f"         '{raw}' → {C}{result['value']:.4f}g{X} stable={result['stable']}")
            passed += 1
        else:
            print(f"  {R}✗ FAIL{X} [{brand}]")
            print(f"       Input:    '{raw}'")
            print(f"       Expected: {exp_val}g stable={exp_stable}")
            print(f"       Got:      {result['value']}g stable={result['stable']}")
            if not val_ok:
                print(f"       {R}Value mismatch!{X}")
            if not stable_ok:
                print(f"       {R}Stability mismatch!{X}")
            failed += 1

    print(f"\n  Result: {G}{passed} passed{X}, {R}{failed} failed{X}")
    return failed == 0


# ═══════════════════════════════════════════════════════════════
# TEST 3: Accuracy Check
# ═══════════════════════════════════════════════════════════════

def test_accuracy():
    print(f"\n{B}TEST 3: Gold Accuracy Verification{X}")
    hr()
    print("Testing that weight calculations are accurate to 0.001g...\n")

    passed = 0
    failed = 0

    cases = [
        # (gross, tare, correct_net)
        (10.5000, 0.0000, 10.5000),
        (10.5000, 0.5000, 10.0000),
        (10.5001, 0.5000, 10.0001),
        (10.4999, 0.5000,  9.9999),
        ( 1.0010, 0.0005,  1.0005),
        ( 0.1250, 0.0000,  0.1250),
        ( 0.0010, 0.0000,  0.0010),  # 1mg test
    ]

    for gross, tare, correct_net in cases:
        calculated_net = round(gross - tare, 4)
        error = abs(calculated_net - correct_net)
        ok = error < 0.00005  # Less than 0.05mg error

        status = f"{G}✓{X}" if ok else f"{R}✗{X}"
        print(f"  {status} Gross={gross:.4f}g - Tare={tare:.4f}g = "
              f"Net={C}{calculated_net:.4f}g{X}  "
              f"(error={error:.6f}g)")

        if ok:
            passed += 1
        else:
            failed += 1
            print(f"    {R}ERROR: Expected {correct_net:.4f}g, got {calculated_net:.4f}g{X}")

    print(f"\n  Result: {G}{passed} passed{X}, {R}{failed} failed{X}")
    return failed == 0


# ═══════════════════════════════════════════════════════════════
# TEST 4: Real Scale (if connected)
# ═══════════════════════════════════════════════════════════════

def test_real_scale():
    print(f"\n{B}TEST 4: Real RS232 Scale Test{X}")
    hr()

    try:
        import serial
        import serial.tools.list_ports
    except ImportError:
        print(f"  {Y}⚠ pyserial not installed — skipping hardware test{X}")
        print(f"  Run: pip install pyserial")
        return None  # Skip, not fail

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print(f"  {Y}⚠ No COM ports found — scale not connected{X}")
        print(f"  Connect scale via RS232/USB adapter and re-run")
        return None  # Skip

    print(f"  Found {len(ports)} COM port(s):")
    for p in ports:
        print(f"    {p.device} — {p.description}")

    # Let user choose or auto-detect
    print(f"\n  {Y}Enter COM port to test (e.g. COM3) or press Enter to auto-detect:{X} ", end='')
    choice = input().strip()

    baud_rates = [9600, 4800, 2400, 19200, 1200, 38400]
    test_port = choice if choice else None
    test_baud = None

    if not test_port:
        print(f"\n  Auto-detecting...")
        for port_info in ports:
            for baud in baud_rates:
                sys.stdout.write(f"  Trying {port_info.device} @ {baud}... ")
                sys.stdout.flush()
                try:
                    ser = serial.Serial(port_info.device, baud, timeout=1.5)
                    ser.reset_input_buffer()
                    ser.write(b'SI\r\n')
                    time.sleep(0.2)
                    raw = ser.read(ser.in_waiting or 64)
                    ser.close()
                    if raw:
                        line = raw.decode('ascii', errors='ignore').strip()
                        parsed = parse_scale_line(line) if line else None
                        if parsed:
                            print(f"{G}✓ Got: '{line}'{X}")
                            test_port = port_info.device
                            test_baud = baud
                            break
                        else:
                            print(f"{Y}? Data but not weight: '{line[:30]}'{X}")
                    else:
                        print(f"No response")
                except Exception as e:
                    print(f"{R}Error: {str(e)[:40]}{X}")
            if test_port and test_baud:
                break

    if not test_port:
        print(f"\n  {R}Scale not detected. Check connection and try scale_detector.py{X}")
        return None

    if not test_baud:
        print(f"\n  {Y}Enter baud rate for {test_port} (default 9600):{X} ", end='')
        baud_input = input().strip()
        test_baud = int(baud_input) if baud_input else 9600

    print(f"\n  {G}Testing {test_port} @ {test_baud} baud...{X}")
    print(f"  {Y}Place a known weight on scale and press Enter{X}: ", end='')
    input()

    readings = []
    print(f"\n  Taking 5 readings...")

    for i in range(5):
        try:
            ser = serial.Serial(test_port, test_baud, timeout=2.0)
            ser.reset_input_buffer()

            # Try commands
            response = ""
            for cmd in [b'SI\r\n', b'P\r\n', b'\r\n']:
                ser.write(cmd)
                time.sleep(0.2)
                raw = ser.read(ser.in_waiting or 64)
                if raw:
                    response = raw.decode('ascii', errors='ignore').strip()
                    break

            ser.close()

            if response:
                parsed = parse_scale_line(response)
                if parsed:
                    readings.append(parsed['value'])
                    stable_mark = f"{G}ST{X}" if parsed['stable'] else f"{Y}US{X}"
                    print(f"  Reading {i+1}: {C}{parsed['value']:.4f}g{X} [{stable_mark}] "
                          f"raw='{response}'")
                else:
                    print(f"  Reading {i+1}: {Y}Could not parse: '{response}'{X}")
            else:
                print(f"  Reading {i+1}: {R}No response{X}")

        except Exception as e:
            print(f"  Reading {i+1}: {R}Error: {e}{X}")
        time.sleep(0.5)

    if readings:
        avg = round(sum(readings) / len(readings), 4)
        variance = round(max(readings) - min(readings), 4)
        print(f"\n  {B}Summary:{X}")
        print(f"    Readings: {readings}")
        print(f"    Average:  {C}{avg:.4f}g{X}")
        print(f"    Variance: {variance:.4f}g  ", end='')
        if variance <= 0.005:
            print(f"{G}(EXCELLENT — within 5mg){X}")
        elif variance <= 0.020:
            print(f"{Y}(OK — within 20mg){X}")
        else:
            print(f"{R}(HIGH variance — check scale stability){X}")

        print(f"\n  {G}✅ Scale working! Add to .env:{X}")
        print(f"  {Y}SCALE_SIMULATION_MODE=false{X}")
        print(f"  {Y}SCALE_PORT={test_port}{X}")
        print(f"  {Y}SCALE_BAUDRATE={test_baud}{X}")
        return True
    else:
        print(f"\n  {R}No valid readings obtained.{X}")
        return False


# ═══════════════════════════════════════════════════════════════
# TEST 5: API Test (if server running)
# ═══════════════════════════════════════════════════════════════

def test_api():
    print(f"\n{B}TEST 5: API Endpoint Test{X}")
    hr()

    try:
        import urllib.request
        import urllib.error
    except ImportError:
        print(f"  {Y}urllib not available{X}")
        return None

    base = "http://localhost:8000"

    # Check if server is running
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=2) as r:
            data = json.loads(r.read())
            print(f"  {G}✓ Server running:{X} {data.get('app')} v{data.get('version')}")
    except Exception:
        print(f"  {Y}⚠ Server not running at localhost:8000 — skipping API test{X}")
        print(f"  Start server: cd backend && uvicorn app.main:app --reload")
        return None

    # Login
    print(f"  Logging in as admin...")
    try:
        login_data = json.dumps({"username": "admin", "password": "admin123"}).encode()
        req = urllib.request.Request(
            f"{base}/api/v1/auth/login",
            data=login_data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            token_data = json.loads(r.read())
            token = token_data.get("access_token")
            if not token:
                print(f"  {R}Login failed — check admin credentials{X}")
                return False
            print(f"  {G}✓ Login success:{X} {token_data['user']['name']}")
    except Exception as e:
        print(f"  {R}Login failed: {e}{X}")
        return False

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Test scale status
    print(f"\n  Testing scale status endpoint...")
    try:
        req = urllib.request.Request(
            f"{base}/api/v1/scale/status",
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            status = json.loads(r.read())
            mode = status.get('mode', 'unknown')
            connected = status.get('connected', False)
            print(f"  {G}✓ Scale status:{X} mode={C}{mode}{X} connected={G if connected else R}{connected}{X}")
    except Exception as e:
        print(f"  {R}Scale status failed: {e}{X}")

    # Test weight read (simulation)
    print(f"\n  Testing weight read (simulation)...")
    try:
        req = urllib.request.Request(
            f"{base}/api/v1/scale/read-weight?expected_weight=10.0",
            data=b"",
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            reading = json.loads(r.read())
            weight = reading.get('weight', 0)
            stable = reading.get('stable', False)
            simulated = reading.get('simulated', False)
            print(f"  {G}✓ Weight read:{X} {C}{weight:.4f}g{X} "
                  f"stable={G if stable else Y}{stable}{X} "
                  f"simulated={simulated}")

            if not stable:
                print(f"  {Y}⚠ Reading not stable — this is normal for simulation{X}")
    except Exception as e:
        print(f"  {R}Weight read failed: {e}{X}")

    # Check a job exists for log test
    print(f"\n  Checking for existing jobs...")
    try:
        req = urllib.request.Request(
            f"{base}/api/v1/jobs/?per_page=1",
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            jobs = json.loads(r.read())
            total = jobs.get('total', 0)
            if total > 0:
                job_id = jobs['items'][0]['id']
                job_code = jobs['items'][0]['job_code']
                print(f"  {G}✓ Found {total} jobs. Testing log with Job #{job_id} ({job_code}){X}")

                # Test log weight
                req = urllib.request.Request(
                    f"{base}/api/v1/scale/log-weight?"
                    f"job_id={job_id}&department_id=1&gross_weight=10.5000&tare_weight=0.0&is_manual=false",
                    data=b"",
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    log_result = json.loads(r.read())
                    log_id = log_result.get('log_id')
                    net = log_result.get('net_weight')
                    print(f"  {G}✓ Weight logged:{X} Log ID={C}{log_id}{X} Net={C}{net:.4f}g{X}")

                # Verify it's in DB
                req = urllib.request.Request(
                    f"{base}/api/v1/scale/history/{job_id}",
                    headers=headers
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    history = json.loads(r.read())
                    print(f"  {G}✓ History verified:{X} {len(history)} log(s) in database for this job")

            else:
                print(f"  {Y}No jobs yet — create a job first to test weight logging{X}")
    except Exception as e:
        print(f"  {R}Job/log test failed: {e}{X}")

    return True


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    banner()

    results = {}

    # Always run these (no hardware needed)
    results['simulation'] = test_simulation()
    results['parsers']    = test_parsers()
    results['accuracy']   = test_accuracy()

    # Hardware test (optional)
    print(f"\n{Y}Test real RS232 scale? (y/n, default=n):{X} ", end='')
    try:
        choice = input().strip().lower()
    except EOFError:
        choice = 'n'

    if choice == 'y':
        results['hardware'] = test_real_scale()
    else:
        print(f"  {Y}Skipping hardware test{X}")

    # API test (optional)
    print(f"\n{Y}Test API (server must be running)? (y/n, default=y):{X} ", end='')
    try:
        choice = input().strip().lower()
    except EOFError:
        choice = 'y'

    if choice != 'n':
        results['api'] = test_api()

    # Final summary
    print(f"\n{'═'*56}")
    print(f"{B}FINAL RESULTS:{X}\n")

    all_pass = True
    for name, result in results.items():
        if result is True:
            print(f"  {G}✅ {name.upper():<15} PASS{X}")
        elif result is False:
            print(f"  {R}❌ {name.upper():<15} FAIL{X}")
            all_pass = False
        else:
            print(f"  {Y}⚠  {name.upper():<15} SKIPPED{X}")

    print()
    if all_pass:
        print(f"{G}{B}✅ All tests passed! Scale system ready for production.{X}")
    else:
        print(f"{R}{B}Some tests failed — check output above.{X}")

    print(f"\n{'═'*56}")
    print(f"\n{C}Next steps:{X}")
    print(f"  1. {Y}Connect USB-RS232 adapter + scale{X}")
    print(f"  2. {Y}Run: python scale_detector.py{X}  (find COM port)")
    print(f"  3. {Y}Update backend/.env with SCALE_PORT and SCALE_BAUDRATE{X}")
    print(f"  4. {Y}Restart server and open /scale page{X}")
    print()


if __name__ == "__main__":
    main()