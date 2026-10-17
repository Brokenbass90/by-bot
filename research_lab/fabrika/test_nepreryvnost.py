import sys, unittest, tempfile, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nepreryvnost as N


class T(unittest.TestCase):
    def test_zhurnal(self):
        t0 = dt.datetime(2026, 10, 17, 18, 0, tzinfo=dt.timezone.utc)
        lines = [f"{(t0 - dt.timedelta(hours=h)).isoformat(timespec='seconds')} хук asm1_fiks_ten: {{}}" for h in (1, 2)]
        lines.append(f"{(t0 - dt.timedelta(minutes=30)).isoformat(timespec='seconds')} хук liq_v2_1_konveyer не прошёл: X")
        lines.append(f"{(t0 - dt.timedelta(hours=5)).isoformat(timespec='seconds')} brain_shadow: {{}}")
        with tempfile.NamedTemporaryFile("w", delete=False) as f: f.write("\n".join(lines))
        N.LOG = Path(f.name)
        z = N.iz_zhurnala(t0.timestamp())
        self.assertEqual(z["asm1_fiks_ten"]["prohodov"], 2)
        self.assertIsNotNone(z["liq_v2_1_konveyer"]["posl_oshibka"])
        r = N.proverki(t0.timestamp())
        self.assertEqual(r["prohod/asm1_fiks_ten"]["status"], "OK")
        self.assertEqual(r["prohod/liq_v2_1_konveyer"]["status"], "OSHIBKA")
        self.assertEqual(r["prohod/brain_shadow"]["status"], "PROPUSK_PROHODA")


if __name__ == "__main__":
    unittest.main()
