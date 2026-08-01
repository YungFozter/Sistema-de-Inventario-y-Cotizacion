import unittest
from datetime import datetime, timezone, timedelta
from models import obtener_fecha_bolivia

class TestTimezoneBolivia(unittest.TestCase):
    def test_obtener_fecha_bolivia_timezone(self):
        fecha_bo = obtener_fecha_bolivia()
        self.assertIsNotNone(fecha_bo.tzinfo)
        offset_seconds = fecha_bo.tzinfo.utcoffset(fecha_bo).total_seconds()
        self.assertEqual(offset_seconds, -14400)

if __name__ == '__main__':
    unittest.main()
