import io
import base64
import random
import string
from datetime import datetime


class BarcodeService:
    """Generates Code128 barcodes as base64 PNG strings"""

    def generate_job_barcode(self, job_code: str) -> tuple[str, str]:
        """Returns (barcode_value, base64_png_image)"""
        barcode_value = f"{job_code}-{self._suffix()}"
        b64 = self._make_barcode_b64(barcode_value)
        return barcode_value, b64

    def _suffix(self) -> str:
        return ''.join(random.choices(string.digits, k=4))

    def _make_barcode_b64(self, value: str) -> str:
        try:
            import barcode
            from barcode.writer import ImageWriter
            buf = io.BytesIO()
            code128 = barcode.get('code128', value, writer=ImageWriter())
            code128.write(buf, options={"module_height": 12, "font_size": 8,
                                        "text_distance": 3, "quiet_zone": 3})
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            # Fallback: return a placeholder base64 string
            return ""


class JobCodeGenerator:
    """Generates unique job codes in format JEW-YYYYMMDD-###"""

    @staticmethod
    def generate(db) -> str:
        from app.models.all_models import Job
        today = datetime.now().strftime("%Y%m%d")
        prefix = f"JEW-{today}-"
        count = db.query(Job).filter(Job.job_code.like(f"{prefix}%")).count()
        return f"{prefix}{str(count + 1).zfill(3)}"


barcode_service = BarcodeService()
