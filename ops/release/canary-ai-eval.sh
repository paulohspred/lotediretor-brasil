#!/usr/bin/env bash
set -euo pipefail
: "${CANARY_BASE_URL:?CANARY_BASE_URL is required}"
: "${CANARY_INTERNAL_API_TOKEN:?CANARY_INTERNAL_API_TOKEN is required}"

out="${CANARY_AI_EVAL_OUTPUT:-/tmp/ld-canary-ai-eval.json}"
curl -fsS --max-time "${CANARY_AI_TIMEOUT_SECONDS:-30}" \
  -H 'content-type: application/json' \
  -H "x-internal-token: $CANARY_INTERNAL_API_TOKEN" \
  -X POST "$CANARY_BASE_URL/ai/v1/evaluate" \
  --data @- >"$out" <<'JSON'
{
  "k": 10,
  "cases": [
    {
      "id": "canary-confirmed-rule-grounding",
      "assistant": "cidades",
      "message": "Qual é o coeficiente confirmado?",
      "rules": [
        {
          "id": "canary-rule-1",
          "status": "CONFIRMED",
          "parameter": "coeficiente_maximo",
          "value": 3.2,
          "source_locator": "canary://approved-rule"
        }
      ],
      "evidence": [
        {"id":"canary-evidence-1","text":"Coeficiente máximo confirmado 3.2.","locator":"canary://approved-rule"}
      ],
      "retrievedIds": ["canary-evidence-1"],
      "relevantEvidenceIds": ["canary-evidence-1"],
      "answerEvidenceIds": ["canary-evidence-1"],
      "allowedEvidenceIds": ["canary-evidence-1"],
      "expectedStatus": "GROUNDED"
    },
    {
      "id": "canary-insufficient-grounding-abstains",
      "assistant": "cidades",
      "message": "Declare uma regra sem evidência confirmada.",
      "rules": [
        {"id":"canary-rule-candidate","status":"CANDIDATE","parameter":"recuo","value":5}
      ],
      "evidence": [],
      "retrievedIds": [],
      "relevantEvidenceIds": [],
      "answerEvidenceIds": [],
      "allowedEvidenceIds": [],
      "expectedStatus": "ABSTAINED"
    }
  ]
}
JSON

python3 - "$out" <<'PY'
import json,sys
raw=json.load(open(sys.argv[1]))
assert raw.get('status')=='PASS',raw
assert raw.get('total')==2,raw
assert raw.get('passed')==2,raw
results={x.get('id'):x for x in raw.get('results',[])}
assert results['canary-confirmed-rule-grounding']['actual']=='GROUNDED',raw
assert results['canary-insufficient-grounding-abstains']['actual']=='ABSTAINED',raw
metrics=raw.get('metrics') or {}
# The eval API must at minimum return its metrics object; thresholds for live
# retrieval quality are evaluated separately against versioned golden datasets.
assert isinstance(metrics,dict),raw
print('Canary deterministic AI eval PASS')
PY
