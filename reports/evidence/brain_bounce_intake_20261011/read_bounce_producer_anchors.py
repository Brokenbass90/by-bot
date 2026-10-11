from pathlib import Path
import json,hashlib
p=Path("/root/by-bot/smart_pump_reversal_bot.py")
raw=p.read_bytes();s=raw.decode()
need=["from bot.strategy_shadow_ledger import", "BOUNCE1_SHADOW_ENABLE", "def _bounce1_shadow_active", "def _ensure_bounce1_shadow_ledger", "BOUNCE1_SHADOW_LEDGER.record_signal", "BOUNCE1_SHADOW_LEDGER.on_price", "bounce1_shadow_ledger.jsonl", "bounce1_shadow_state.json"]
out={"source_path":str(p),"sha256":hashlib.sha256(raw).hexdigest(),"anchors_present":{k:k in s for k in need},"scope":"ON_DISK_SOURCE_ONLY_NOT_IN_MEMORY_PROOF","orders_allowed":False}
print(json.dumps(out,sort_keys=True))
