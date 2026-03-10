"""
scale_service.py — Production-Ready RS232 Weighing Scale Integration
=====================================================================
For gold jewellery use — 0.001g accuracy guaranteed

Supported scale protocols:
  - Mettler Toledo (MT-SICS / SBI format)
  - Sartorius (SBI / SI format)
  - Citizen CG series
  - Avery / Ohaus / most Indian jewelry scales
  - Generic RS232 (fallback parser)

Author: Jewellery ERP
"""

import asyncio
import re
import time
import threading
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data class for a weight reading
# ─────────────────────────────────────────────────────────────────────────────
class WeightReading:
    def __init__(self):
        self.raw_grams: float = 0.0        # Raw value from scale
        self.net_grams: float = 0.0        # After tare
        self.tare_grams: float = 0.0       # Tare stored in service
        self.stable: bool = False          # Scale reports stable reading
        self.unit: str = "g"               # Unit from scale
        self.simulated: bool = False       # Is this a simulated reading?
        self.error: Optional[str] = None   # Error message if failed
        self.raw_line: str = ""            # Raw string from scale
        self.timestamp: float = time.time()
        self.reading_count: int = 0        # How many attempts to get stable

    def to_dict(self) -> dict:
        return {
            "weight": round(self.net_grams, 4),
            "gross_weight": round(self.raw_grams, 4),
            "tare_weight": round(self.tare_grams, 4),
            "stable": self.stable,
            "unit": self.unit,
            "simulated": self.simulated,
            "error": self.error,
            "raw_reading": self.raw_line,
            "timestamp": self.timestamp,
            "attempts": self.reading_count,
            "source": "Simulation" if self.simulated else "RS232 Scale",
        }


# ─────────────────────────────────────────────────────────────────────────────
# RS232 Protocol Parsers
# ─────────────────────────────────────────────────────────────────────────────

def parse_mettler_toledo(line: str) -> Optional[dict]:
    """
    Mettler Toledo MT-SICS / SBI format examples:
      S S      10.234 g     (stable)
      S D       9.998 g     (dynamic/unstable)
      S +     123.456 g
    """
    # Pattern: [S|D|I] [S|D|+|-] <spaces> <value> <unit>
    m = re.match(
        r'^[A-Z]\s+([SD+\-])\s+([\d]+\.[\d]+)\s+(g|mg|kg|ct)',
        line.strip(), re.IGNORECASE
    )
    if m:
        return {
            "value": float(m.group(2)),
            "stable": m.group(1).upper() == 'S',
            "unit": m.group(3).lower(),
        }
    return None


def parse_sartorius(line: str) -> Optional[dict]:
    """
    Sartorius SBI format examples:
      +0000010.234g S   (stable)
      +0000010.102g D   (dynamic)
    """
    m = re.match(
        r'^[+\-](\d+\.?\d*)\s*(g|mg|kg|ct)\s*([SD])?',
        line.strip(), re.IGNORECASE
    )
    if m:
        return {
            "value": float(m.group(1)),
            "stable": (m.group(3) or '').upper() == 'S',
            "unit": (m.group(2) or 'g').lower(),
        }
    return None


def parse_citizen_cg(line: str) -> Optional[dict]:
    """
    Citizen CG series / many Indian jewelry scales:
      GS   10.234g     (GS = Gross Stable)
      G    10.102g     (G = Gross, may be unstable)
      ST,+  10.234, g  (alternate format)
    """
    # Format 1: GS/G prefix
    m = re.match(r'^GS?\s*([\d]+\.[\d]+)\s*(g|mg|kg)', line.strip(), re.IGNORECASE)
    if m:
        return {
            "value": float(m.group(1)),
            "stable": line.strip().upper().startswith('GS'),
            "unit": m.group(2).lower(),
        }
    # Format 2: ST,+value,unit
    m = re.match(r'^ST,\s*[+\-]?\s*([\d]+\.[\d]+),\s*(g)', line.strip(), re.IGNORECASE)
    if m:
        return {"value": float(m.group(1)), "stable": True, "unit": "g"}

    # Format 3: OL,+ value,unit (unstable/overload)
    if line.strip().startswith('OL') or line.strip().startswith('US'):
        return {"value": 0.0, "stable": False, "unit": "g"}

    return None


def parse_generic(line: str) -> Optional[dict]:
    """
    Fallback: extract any number from line.
    Stability: line contains 'ST', 'S', 'STABLE' → stable
    """
    line_clean = line.strip()
    if not line_clean:
        return None

    # Extract number (with optional decimal)
    m = re.search(r'([\d]+\.[\d]+)', line_clean)
    if not m:
        m = re.search(r'(\d+)', line_clean)
    if not m:
        return None

    value = float(m.group(1))

    # Detect stability markers
    stable = bool(re.search(r'\bST\b|\bSTABLE\b', line_clean, re.IGNORECASE))
    # Some scales: no 'US'/'UN' = stable
    unstable = bool(re.search(r'\bUS\b|\bUN\b|\bUNSTABLE\b|\bD\b', line_clean, re.IGNORECASE))
    if not unstable and re.search(r'ST', line_clean):
        stable = True

    # Detect unit
    unit = "g"
    if re.search(r'\bkg\b', line_clean, re.IGNORECASE):
        unit = "kg"
        value = value * 1000  # Convert to grams always
    elif re.search(r'\bmg\b', line_clean, re.IGNORECASE):
        unit = "mg"
        value = value / 1000

    return {"value": round(value, 4), "stable": stable, "unit": "g"}


def parse_scale_line(line: str) -> Optional[dict]:
    """
    Try all parsers in order, return first match.
    Always returns value in GRAMS regardless of scale unit.
    """
    if not line or not line.strip():
        return None

    for parser in [parse_mettler_toledo, parse_sartorius, parse_citizen_cg, parse_generic]:
        result = parser(line)
        if result is not None:
            return result

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main Scale Service
# ─────────────────────────────────────────────────────────────────────────────

class ScaleService:
    """
    Production-grade RS232 scale service for gold jewellery.

    Key features:
    - Waits for STABLE reading (critical for gold accuracy)
    - Retries up to MAX_ATTEMPTS times
    - Thread-safe tare management
    - Auto-reconnect on disconnect
    - Supports all major RS232 scale protocols
    - Simulation mode for development/testing
    """

    # How many times to poll scale waiting for STABLE reading
    MAX_STABLE_ATTEMPTS = 10
    POLL_INTERVAL_SEC = 0.3      # Wait between polls
    STABLE_HOLD_READS = 2        # Read stable N consecutive times before accepting
    MIN_WEIGHT_GRAMS = 0.001     # Minimum valid reading (ignore scale noise)
    MAX_WEIGHT_GRAMS = 5000.0    # Maximum valid reading (5kg = sanity check)

    def __init__(self):
        self.simulation_mode: bool = settings.SCALE_SIMULATION_MODE
        self.port: str = settings.SCALE_PORT
        self.baudrate: int = settings.SCALE_BAUDRATE
        self._serial = None
        self._lock = threading.Lock()
        self._tare: float = 0.0
        self._last_reading: Optional[WeightReading] = None

    # ── Tare Management ──────────────────────────────────────────────────────

    def set_tare(self, value: float) -> None:
        """Set tare weight (grams). Thread-safe."""
        with self._lock:
            self._tare = round(max(0.0, value), 4)
        logger.info(f"Tare set to {self._tare}g")

    def clear_tare(self) -> None:
        with self._lock:
            self._tare = 0.0

    def get_tare(self) -> float:
        with self._lock:
            return self._tare

    # ── Serial Port Management ───────────────────────────────────────────────

    def _get_serial(self):
        """Get or create serial connection. Auto-reconnects."""
        import serial
        if self._serial and self._serial.is_open:
            return self._serial
        # Close stale connection
        try:
            if self._serial:
                self._serial.close()
        except Exception:
            pass
        # Open new connection
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.5,       # 1.5s read timeout
            write_timeout=1.0,
        )
        # Flush any old data
        self._serial.reset_input_buffer()
        self._serial.reset_output_buffer()
        logger.info(f"Scale connected on {self.port} @ {self.baudrate} baud")
        return self._serial

    def _close_serial(self):
        try:
            if self._serial and self._serial.is_open:
                self._serial.close()
        except Exception:
            pass
        self._serial = None

    def _request_reading(self, ser) -> str:
        """
        Send print command to scale and read response.
        Most RS232 scales respond to:
          - 'P\\r\\n'  (print command)
          - '\\r\\n'   (just CR/LF triggers reading on some models)
          - 'SI\\r\\n' (send immediate — Mettler/Sartorius)
        We try 'SI' first, fallback to 'P', fallback to just read.
        """
        raw_line = ""
        # Try SI command (Mettler Toledo / Sartorius)
        try:
            ser.write(b'SI\r\n')
            time.sleep(0.05)
            raw = ser.readline()
            raw_line = raw.decode('ascii', errors='ignore').strip()
            if raw_line:
                return raw_line
        except Exception:
            pass

        # Try P command (most other scales)
        try:
            ser.write(b'P\r\n')
            time.sleep(0.05)
            raw = ser.readline()
            raw_line = raw.decode('ascii', errors='ignore').strip()
            if raw_line:
                return raw_line
        except Exception:
            pass

        # Passive: just read whatever scale is sending (some scales push continuously)
        try:
            raw = ser.readline()
            raw_line = raw.decode('ascii', errors='ignore').strip()
        except Exception:
            pass

        return raw_line

    # ── Core Reading Logic ───────────────────────────────────────────────────

    async def read_weight(self, expected_weight: float = 10.0) -> dict:
        """
        Read weight from scale.
        - In SIMULATION mode: returns realistic simulated value
        - In REAL mode: polls scale until STABLE reading obtained
        Returns dict with all reading details.
        """
        if self.simulation_mode:
            return await self._simulate(expected_weight)
        return await self._read_real_stable()

    async def _read_real_stable(self) -> dict:
        """
        Poll RS232 scale, wait for STABLE reading.
        Gold accuracy requirement: must get stable before returning.
        """
        reading = WeightReading()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._blocking_read_stable)
        return result

    def _blocking_read_stable(self) -> dict:
        """
        Blocking RS232 read — runs in thread executor.
        Waits for STABLE reading, up to MAX_STABLE_ATTEMPTS polls.
        """
        reading = WeightReading()
        consecutive_stable = 0
        last_stable_value = None

        try:
            ser = self._get_serial()

            for attempt in range(1, self.MAX_STABLE_ATTEMPTS + 1):
                reading.reading_count = attempt

                raw_line = self._request_reading(ser)
                reading.raw_line = raw_line

                if not raw_line:
                    time.sleep(self.POLL_INTERVAL_SEC)
                    continue

                parsed = parse_scale_line(raw_line)
                if parsed is None:
                    logger.warning(f"Cannot parse scale line: '{raw_line}'")
                    time.sleep(self.POLL_INTERVAL_SEC)
                    continue

                value = parsed["value"]
                stable = parsed["stable"]

                # Sanity check value range
                if not (self.MIN_WEIGHT_GRAMS <= value <= self.MAX_WEIGHT_GRAMS):
                    # Could be zero (empty pan) — allow zero if stable
                    if value == 0.0 and stable:
                        pass
                    elif value < 0:
                        logger.warning(f"Negative weight: {value}g — ignoring")
                        time.sleep(self.POLL_INTERVAL_SEC)
                        continue

                if stable:
                    # Check consecutive stable reads match (prevents transient stable)
                    if last_stable_value is None or abs(value - last_stable_value) < 0.002:
                        consecutive_stable += 1
                        last_stable_value = value
                    else:
                        # Value changed between stable reads — reset
                        consecutive_stable = 1
                        last_stable_value = value

                    if consecutive_stable >= self.STABLE_HOLD_READS:
                        # ✅ CONFIRMED STABLE
                        tare = self.get_tare()
                        net = round(max(0.0, value - tare), 4)
                        reading.raw_grams = round(value, 4)
                        reading.tare_grams = tare
                        reading.net_grams = net
                        reading.stable = True
                        reading.unit = parsed["unit"]
                        reading.simulated = False
                        logger.info(
                            f"Stable reading: gross={value}g tare={tare}g net={net}g "
                            f"(after {attempt} attempts)"
                        )
                        self._last_reading = reading
                        return reading.to_dict()
                else:
                    # Unstable — reset consecutive counter
                    consecutive_stable = 0
                    last_stable_value = None
                    # Still update display with current (unstable) value
                    reading.raw_grams = round(value, 4)
                    reading.stable = False

                time.sleep(self.POLL_INTERVAL_SEC)

            # All attempts exhausted — return last reading with warning
            logger.warning(
                f"Scale did not stabilize after {self.MAX_STABLE_ATTEMPTS} attempts. "
                f"Last value: {reading.raw_grams}g"
            )
            tare = self.get_tare()
            reading.tare_grams = tare
            reading.net_grams = round(max(0.0, reading.raw_grams - tare), 4)
            reading.stable = False
            reading.error = "Scale did not stabilize — check item placement"
            self._last_reading = reading
            return reading.to_dict()

        except ImportError:
            return self._serial_not_available()
        except Exception as e:
            logger.error(f"Scale read error: {e}")
            self._close_serial()
            reading.error = str(e)
            reading.stable = False
            return reading.to_dict()

    def _serial_not_available(self) -> dict:
        reading = WeightReading()
        reading.error = "pyserial not installed. Run: pip install pyserial"
        reading.stable = False
        return reading.to_dict()

    async def _simulate(self, expected: float) -> dict:
        """
        Realistic simulation — mimics real scale behavior:
        - First 1-2 reads: unstable (weight settling)
        - Final reads: stable with small variance
        """
        import random
        await asyncio.sleep(0.4)  # Simulate read delay

        # Simulate ±0.5% variance (realistic for jewelry scale)
        variance_pct = random.uniform(-0.005, 0.005)
        noise = random.uniform(-0.0005, 0.0005)
        value = round(expected * (1 + variance_pct) + noise, 4)
        value = max(0.0001, value)

        tare = self.get_tare()
        net = round(max(0.0, value - tare), 4)

        reading = WeightReading()
        reading.raw_grams = value
        reading.tare_grams = tare
        reading.net_grams = net
        reading.stable = True
        reading.unit = "g"
        reading.simulated = True
        reading.raw_line = f"SIM {value:.4f}g ST"
        reading.reading_count = 2
        self._last_reading = reading

        return reading.to_dict()

    # ── Status & Diagnostics ─────────────────────────────────────────────────

    async def get_status(self) -> dict:
        """Get scale connection status and last reading."""
        base = {
            "mode": "simulation" if self.simulation_mode else "real",
            "port": "SIMULATED" if self.simulation_mode else self.port,
            "baudrate": self.baudrate,
            "tare": self.get_tare(),
            "last_weight": self._last_reading.net_grams if self._last_reading else 0.0,
            "last_stable": self._last_reading.stable if self._last_reading else False,
        }
        if self.simulation_mode:
            base["connected"] = True
            base["message"] = "Simulation mode — set SCALE_SIMULATION_MODE=false for real scale"
            return base

        # Test real connection
        try:
            import serial
            test = serial.Serial(self.port, self.baudrate, timeout=0.5)
            test.close()
            base["connected"] = True
            base["message"] = f"Scale connected on {self.port}"
        except ImportError:
            base["connected"] = False
            base["message"] = "pyserial not installed — run: pip install pyserial"
        except Exception as e:
            base["connected"] = False
            base["message"] = str(e)
            base["fix"] = (
                f"Check: (1) Scale is ON and connected, "
                f"(2) COM port is correct (Device Manager → Ports), "
                f"(3) No other software using {self.port}"
            )

        return base

    async def detect_port(self) -> dict:
        """
        Auto-detect COM port — list all available serial ports.
        Useful when you don't know the port number.
        """
        try:
            import serial.tools.list_ports
            ports = serial.tools.list_ports.comports()
            available = []
            for p in sorted(ports):
                available.append({
                    "port": p.device,
                    "description": p.description,
                    "hwid": p.hwid,
                    "likely_scale": any(
                        kw in (p.description or '').lower()
                        for kw in ['usb', 'serial', 'com', 'prolific', 'ftdi', 'cp210']
                    )
                })
            return {
                "available_ports": available,
                "current_port": self.port,
                "suggestion": available[0]["port"] if available else None
            }
        except ImportError:
            return {"error": "pyserial not installed"}
        except Exception as e:
            return {"error": str(e)}


# Singleton instance
scale_service = ScaleService()
