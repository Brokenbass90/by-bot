"""Offline proof only; this object is NOT a valid or accepted signal receipt."""
import hashlib
import json
from pathlib import Path

root = Path('.private/kity_oct8_source_inventory')
source = root/'actual_complete_capture_bundle.json'
bundle = json.loads(source.read_text())
census = json.loads(bundle['census']['raw'])
active = {row['symbol'] for row in census['symbols']
          if row.get('contractType') == 'PERPETUAL'
          and row.get('quoteAsset') == 'USDT'
          and row.get('marginAsset') == 'USDT'
          and row.get('status') == 'TRADING'}
assert set(bundle['oi']) == active | {'GAIBUSDT'}
pins = {'census': bundle['census']['sha256']}
for prefix, captures in (('oi', bundle['oi']), ('klines', bundle['klines'])):
    for symbol, capture in captures.items():
        assert hashlib.sha256(capture['raw'].encode()).hexdigest() == capture['sha256']
        pins[prefix+':'+symbol] = capture['sha256']
assert len(active) == 525 and len(pins) == 577
canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode('ascii')
minimum = {'receipt': {'signal': {'source_bundle': bundle,
                                 'frozen_signal': {'source_pins': pins}}}}
input_bytes, lower = len(canonical(bundle)), len(canonical(minimum))
assert input_bytes == 2087545 and lower == 2134621 and lower > 2*1024*1024
result = {'schema': 'KITY_FULL_PUBLICATION_SIZE_LOWER_BOUND_V1',
          'input_bundle_bytes': input_bytes, 'bound_bytes': 2*1024*1024,
          'source_pin_count': len(pins), 'mandatory_fields_lower_bound_bytes': lower,
          'at_least_over_bound_bytes': lower-2*1024*1024,
          'lower_bound_is_valid_receipt': False, 'accepted_signal_created': False,
          'proof': 'canonical subset retaining mandated full source_bundle and frozen source_pins already exceeds current complete-envelope bound; other receipt/frozen/seal fields only add bytes',
          'original_bundle_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
out = Path('.private/kity_intake_20261008/publication_size_lower_bound.json')
out.write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
print(json.dumps(result, sort_keys=True))
