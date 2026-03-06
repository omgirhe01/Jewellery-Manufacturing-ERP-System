import asyncio
import random
import time
from app.core.config import settings


class ScaleService:
    """Weighing scale - supports SIMULATION and real USB/RS232"""

    def __init__(self):
        self.simulation_mode = settings.SCALE_SIMULATION_MODE
        self.port = settings.SCALE_PORT
        self.baudrate = settings.SCALE_BAUDRATE
        self._serial = None
        self._last_weight = 0.0

    async def read_weight(self, expected_weight: float = 10.0) -> dict:
        if self.simulation_mode:
            return await self._simulate(expected_weight)
        return await self._read_real()

    async def _simulate(self, expected: float) -> dict:
        await asyncio.sleep(0.3)
        weight = round(expected * (1 + random.uniform(-0.05, 0.05)) + random.uniform(-0.002, 0.002), 4)
        self._last_weight = weight
        return {"weight": weight, "stable": True, "unit": "g", "simulated": True,
                "timestamp": time.time(), "raw_reading": f"{weight:.4f}g ST"}

    async def _read_real(self) -> dict:
        try:
            import serial, re
            if not self._serial or not self._serial.is_open:
                self._serial = serial.Serial(self.port, self.baudrate, timeout=2)
            self._serial.write(b'\r\n')
            await asyncio.sleep(0.1)
            line = self._serial.readline().decode('utf-8', errors='ignore').strip()
            match = re.search(r'(\d+\.?\d*)', line)
            if match:
                weight = float(match.group(1))
                self._last_weight = weight
                return {"weight": weight, "stable": 'ST' in line, "unit": "g",
                        "simulated": False, "timestamp": time.time(), "raw_reading": line}
            raise ValueError(f"Cannot parse: {line}")
        except Exception as e:
            return {"weight": 0.0, "stable": False, "unit": "g", "simulated": False,
                    "error": str(e), "timestamp": time.time()}

    async def get_status(self) -> dict:
        if self.simulation_mode:
            return {"connected": True, "mode": "simulation", "port": "SIMULATED",
                    "last_weight": self._last_weight}
        try:
            import serial
            s = serial.Serial(self.port, self.baudrate, timeout=1)
            s.close()
            return {"connected": True, "mode": "real", "port": self.port}
        except Exception as e:
            return {"connected": False, "mode": "real", "port": self.port, "error": str(e)}


scale_service = ScaleService()
