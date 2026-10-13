import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import svodka_v1 as S


class TestSvodka(unittest.TestCase):
    def test_sobiraetsya_bez_istochnikov(self):
        d = Path(tempfile.mkdtemp())
        old = (S.D, S.CODEX); S.D, S.CODEX = d, d / "net"
        try: md = S.sobrat()
        finally: S.D, S.CODEX = old
        for razdel in ("## Деньги", "## Тени и сборщики", "## Данные", "## Реестр", "## Нужно от тебя"):
            self.assertIn(razdel, md)
        self.assertIn("нет доступа к отчёту Codex", md)
        self.assertTrue(any(d.glob("svodka/*.md")))


if __name__ == "__main__":
    unittest.main()
