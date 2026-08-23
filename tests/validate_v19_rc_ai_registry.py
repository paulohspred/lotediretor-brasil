from pathlib import Path
p=Path('services/ai-gateway/src/prompts.ts').read_text();t=Path('services/ai-gateway/src/tools.ts').read_text();m=Path('services/ai-gateway/src/main.ts').read_text()
for x in ('legal-grounded','version:\'1.0.0\'','decision_status','evidence_ids'):assert x in p,x
for x in ('territorial.rules.effective','territorial.spatial.intersections','aitec.site_solver.generate','requiresExplicitUserAction:true','explicit_user_action_required'):assert x in t,x
for x in ("/ai/v1/registry",'promptRegistry()','toolAuthorized(','prompt_id','promptVersion'):assert x in m,x
print('v19-rc Prompt/Tool Registry contracts OK')
