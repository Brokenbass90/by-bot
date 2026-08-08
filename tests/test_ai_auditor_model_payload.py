from research_lab.ai_auditor import parse_model_payload


def test_parse_model_payload_requires_falsifiable_fields():
    findings = parse_model_payload('''{
      "findings": [
        {
          "what": "stale context is consumed",
          "where": "scripts/build_ai_full_context.py:10",
          "why": "consumer lacks freshness gate",
          "how_to_verify": "rg freshness scripts/build_ai_full_context.py",
          "how_to_falsify": "show a fail-closed age check",
          "severity": "high"
        },
        {"what": "incomplete"}
      ]
    }''')
    assert len(findings) == 1
    assert findings[0].source == "model"
    assert findings[0].severity == "high"


def test_parse_model_payload_rejects_non_json_and_caps_findings():
    assert parse_model_payload("not json") == []
    rows = [
        {
            "what": f"candidate {index}",
            "where": "a.py:1",
            "why": "mechanism",
            "how_to_verify": "rg x a.py",
            "how_to_falsify": "show opposite",
            "severity": "invalid",
        }
        for index in range(5)
    ]
    import json
    findings = parse_model_payload(json.dumps({"findings": rows}))
    assert len(findings) == 3
    assert all(item.severity == "low" for item in findings)
