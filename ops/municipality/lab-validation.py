from __future__ import annotations
import json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def validate(path:Path):
    data=json.loads(path.read_text())
    cases=data.get('cases') or []
    errors=[]
    required=data.get('required_case_fields') or []
    for idx,case in enumerate(cases,1):
        for key in required:
            if key not in case or case[key] in (None,'',{}): errors.append(f'case {idx}: missing {key}')
        if case.get('status')=='PASS' and not case.get('reviewer'): errors.append(f"{case.get('case_code',idx)}: PASS sem reviewer")
        if case.get('status')=='PASS' and not case.get('expected_official_reference'): errors.append(f"{case.get('case_code',idx)}: PASS sem referência oficial")
    summary={'municipality_ibge':data.get('municipality_ibge'),'cases':len(cases),'minimum_cases':data.get('minimum_cases',10),'ready_for_homologation':len(cases)>=data.get('minimum_cases',10) and not errors and all(c.get('status')=='PASS' for c in cases),'errors':errors}
    return summary

if __name__=='__main__':
    path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'data/municipality-labs/sao-paulo-validation-plan.json'
    print(json.dumps(validate(path),ensure_ascii=False,indent=2))
