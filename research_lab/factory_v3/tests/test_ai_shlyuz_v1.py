import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_shlyuz_v1 as S


def fake(otvet_obj, usage=(100, 50), zapis=None):
    def otpravit(url, klyuch, body, timeout):
        if zapis is not None: zapis.append(body)
        return {"choices": [{"message": {"content": json.dumps(otvet_obj)}}],
                "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}
    return otpravit


class TestShlyuz(unittest.TestCase):
    def setUp(self):
        self.put = Path(tempfile.mkdtemp()) / "rashod.jsonl"

    def test_vyzov_i_uchet(self):
        bodies = []
        k = S.klient_deepseek(put_rashoda=self.put, otpravit=fake({"a": 1}, zapis=bodies), klyuch="x")
        self.assertEqual(k("сис", "запрос"), {"a": 1})
        self.assertEqual(bodies[0]["max_tokens"], S.MAKS_VYHOD_TOK)
        zap = json.loads(self.put.read_text())
        self.assertNotIn("запрос", self.put.read_text()); self.assertNotIn("x", zap.get("klyuch", ""))
        self.assertAlmostEqual(zap["usd"], S.stoimost(100, 50), 9)

    def test_bez_klyucha_otkaz(self):
        k = S.klient_deepseek(put_rashoda=self.put, otpravit=fake({}), klyuch="")
        with self.assertRaises(S.OtkazShlyuza): k("s", "z")

    def test_utechka_nichego_ne_uhodit(self):
        bodies = []
        k = S.klient_deepseek(put_rashoda=self.put, otpravit=fake({}, zapis=bodies), klyuch="x")
        for plohoy in ("мой API_KEY=abc", "sk-abcdefghijklmnopqrstuv", "a" * 0 + "0123456789abcdef" * 3, "смотри signal_copy/config.json"):
            with self.assertRaises(S.OtkazShlyuza): k("s", plohoy)
        self.assertEqual(bodies, [])

    def test_byudzhet(self):
        k = S.klient_deepseek(put_rashoda=self.put, otpravit=fake({}, usage=(1_000_000, 1_000_000)), klyuch="x", byudzhet_usd=2.0)
        k("s", "z")                                   # $1.76 списано
        with self.assertRaises(S.OtkazShlyuza): k("s", "z" * 2000)   # худший случай не помещается
        self.assertLessEqual(S.potracheno(put=self.put), 2.0)

    def test_dlina(self):
        k = S.klient_deepseek(put_rashoda=self.put, otpravit=fake({}), klyuch="x")
        with self.assertRaises(S.OtkazShlyuza): k("s", "я" * (S.MAKS_VHOD_SIMV + 1))


if __name__ == "__main__":
    unittest.main()
