#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = Path(os.environ.get('CORTEX_ARTIFACT_ROOT', ROOT / 'runtime-artifacts/cortex')).resolve()
REQUIRED_PROFILES = ('ci', 'soak', 'capacity')


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def current_commit() -> str | None:
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
    except Exception:
        return None


def collect_candidates():
    by_profile = {p: [] for p in REQUIRED_PROFILES}
    if not ARTIFACT_ROOT.exists():
        return by_profile
    for report_path in ARTIFACT_ROOT.glob('*/qualification-report.json'):
        artifact_dir = report_path.parent
        report = load_json(report_path)
        manifest = load_json(artifact_dir / 'evidence-manifest.json')
        if not isinstance(report, dict) or not isinstance(manifest, dict):
            continue
        profile = str(report.get('profile') or manifest.get('loadProfile') or '')
        if profile not in by_profile:
            continue
        if report.get('localQualificationStatus') != 'PASS':
            continue
        if report.get('productionHomologated') is not False:
            continue
        if manifest.get('qualificationStatus') != 'PASS':
            continue
        git = manifest.get('git') or {}
        commit = str(git.get('commit') or '')
        if len(commit) != 40 or git.get('dirty') is not False:
            continue
        generated = str(report.get('generatedAtUtc') or manifest.get('generatedAtUtc') or '')
        by_profile[profile].append({
            'profile': profile,
            'artifactDir': str(artifact_dir),
            'commit': commit,
            'generatedAtUtc': generated,
            'report': report,
            'manifest': manifest,
        })
    for profile in by_profile:
        by_profile[profile].sort(key=lambda x: x['generatedAtUtc'], reverse=True)
    return by_profile


def validate_local():
    errors = []
    by_profile = collect_candidates()
    selected = {}
    for profile in REQUIRED_PROFILES:
        if not by_profile[profile]:
            errors.append(f'missing PASS Cortex evidence for profile:{profile}')
        else:
            selected[profile] = by_profile[profile][0]
    commits = {item['commit'] for item in selected.values()}
    if selected and len(commits) != 1:
        errors.append(f'Cortex profile evidence comes from different commits:{sorted(commits)}')
    head = current_commit()
    if len(commits) == 1 and head and head not in commits:
        errors.append(f'current HEAD does not match qualified commit:{head}!={next(iter(commits))}')
    return errors, selected, head


def validate_production_if_requested():
    evidence = os.environ.get('PRODUCTION_HOMOLOGATION_EVIDENCE', '').strip()
    if not evidence:
        return False, ['production homologation evidence not supplied']
    cmd = [sys.executable, str(ROOT / 'ops/release/production-homologation.py')]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, env=os.environ.copy())
    if proc.returncode != 0:
        detail = (proc.stdout + '\n' + proc.stderr).strip()
        return False, [f'production homologation gate failed:{detail[-2000:]}']
    return True, []


def self_test():
    required = {'ci', 'soak', 'capacity'}
    assert set(REQUIRED_PROFILES) == required
    source = Path(__file__).read_text(encoding='utf-8')
    for needle in (
        'localQualificationStatus', 'evidence-manifest.json', 'qualificationStatus',
        "git.get('dirty') is not False", 'different commits', 'current HEAD does not match qualified commit',
        'production-homologation.py', 'readyToMergeDevelop', 'readyToPublishProduction',
    ):
        assert needle in source, needle
    print('Cortex publish-readiness fail-closed self-test PASS')


if '--self-test' in sys.argv:
    self_test()
    raise SystemExit(0)

local_errors, selected, head = validate_local()
local_ready = not local_errors
production_ready, production_errors = validate_production_if_requested()
if not local_ready:
    production_ready = False

report = {
    'schemaVersion': 'lotediretor-cortex-publish-readiness-v1',
    'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
    'headCommit': head,
    'requiredProfiles': list(REQUIRED_PROFILES),
    'selectedEvidence': {
        profile: {
            'artifactDir': item['artifactDir'],
            'commit': item['commit'],
            'generatedAtUtc': item['generatedAtUtc'],
        }
        for profile, item in selected.items()
    },
    'readyToMergeDevelop': local_ready,
    'readyToPublishProduction': local_ready and production_ready,
    'productionHomologated': local_ready and production_ready,
    'localErrors': local_errors,
    'productionErrors': production_errors,
    'policy': {
        'mergeDevelopRequires': 'ci+soak+capacity PASS on the same clean commit',
        'productionPublishRequires': 'local publish readiness plus production-homologation-v1 evidence PASS',
    },
}

out = Path(os.environ.get('CORTEX_PUBLISH_READINESS_OUTPUT', ARTIFACT_ROOT / 'publish-readiness.json')).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2, ensure_ascii=False))

if '--require-local' in sys.argv and not local_ready:
    raise SystemExit(1)
if '--require-production' in sys.argv and not report['readyToPublishProduction']:
    raise SystemExit(1)
