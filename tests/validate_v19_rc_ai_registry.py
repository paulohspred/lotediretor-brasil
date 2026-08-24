from pathlib import Path
p=Path('services/ai-gateway/src/prompts.ts').read_text();t=Path('services/ai-gateway/src/tools.ts').read_text();m=Path('services/ai-gateway/src/main.ts').read_text()
# v20 intentionally advances the legal-grounded prompt policy; keep the registry identity/version gate explicit.
for x in ('legal-grounded',"version:'1.1.0'",'decision_status','evidence_ids','fingerprint'):assert x in p,x
for x in ('territorial.rules.effective','territorial.spatial.intersections','aitec.site_solver.generate','requiresExplicitUserAction:true','explicit_user_action_required'):assert x in t,x
for x in ("/ai/v1/registry",'promptRegistry()','toolAuthorized(','prompt_id','promptVersion','promptFingerprint'):assert x in m,x
print('v19-rc Prompt/Tool Registry contracts OK (v20 policy version accepted)')
