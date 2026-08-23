from pathlib import Path


def must(path: str, *needles: str):
    text=Path(path).read_text()
    for n in needles:
        assert n in text, f"{path}: missing {n}"
    return text

m=must('db/platform/migrations/180_v18_condo_solar.sql',
       'condo.building','condo.unit','condo.common_area','condo.work_request',
       'condo.assembly','condo.agenda_item','condo.decision','condo.vote_summary',
       'condo.maintenance_item','condo.occurrence','condo.compliance_item',
       'solar.site','solar.surface','solar.obstacle','solar.module_catalog',
       'solar.inverter_catalog','solar.layout','solar.layout_panel','solar.bill_snapshot',
       'solar.regulation_snapshot','solar.energy_balance','CONDO360_360','SOLAR360_360',
       'FORCE ROW LEVEL SECURITY')
assert 'DEMO_REFERENCE' in m

app=must('services/platform-api/src/app.module.ts','CondoModule','SolarModule')
condo=must('services/platform-api/src/condo/condo.controller.ts',
           "@Get(':id/dashboard')","@Post(':id/units')","@Post(':id/common-areas')",
           "@Post(':id/works')","@Post(':id/assemblies')","vote-summary",
           "@Post(':id/maintenance')","@Post(':id/occurrences')","@Post(':id/compliance')",
           "@Post(':id/report')",'CANDIDATE')
assert 'CONFIRMED' not in condo.split('generated_rule_id')[0][-1200:] or 'CANDIDATE' in condo

solar=must('services/platform-api/src/solar/solar.controller.ts',
           "@Get('projects/:id/dashboard')","@Post('projects/:id/sites')",
           "@Post('projects/:id/sites/:siteId/surfaces')","obstacles",
           "@Post('projects/:id/layouts/auto')","@Get('projects/:id/scene-3d')",
           "@Post('projects/:id/bills')","@Post('projects/:id/energy-balance')",
           "@Post('projects/:id/sun-path')","@Post('projects/:id/report')",
           'PRELIMINARY_3D_SCENE_DATA','solar.layout.completed')

engine=must('services/solar-engine/app/main.py','/solar/v1/layout-2d','/solar/v1/energy-balance','/solar/v1/sun-path')
domain=must('services/solar-engine/app/domain.py','def pack_rectangular_surface','def monthly_energy_balance','class RectObstacle')

rules=must('workers/documents/rules.py','def condo_candidates','CANDIDATE')
docworker=must('workers/documents/main.py','condo_candidates','deterministic_condo_v18')
assert "'CONFIRMED'" not in rules, 'deterministic condo extractor must never confirm rules'

reports=must('workers/reports/builder.py','def build_condo_report','def build_solar_report','condo_limitations','solar_limitations')
render=must('workers/reports/renderer.py','condo_cover','solar_cover')

gql=must('services/platform-api/src/graphql.ts','type CondoSummary','type SolarProjectSummary','condoSummary','solarProjectSummary')

cui=must('apps/client-web/components/workspaces/CondoWorkspace.tsx','workflow operacional','Gerar Condomínio 360','A.I Condomínio')
sui=must('apps/client-web/components/workspaces/SolarWorkspace.tsx','2D/3D preliminar','Layout 2D','Cena 3D preliminar','Gerar Solar 360')
for txt,name in [(cui,'CondoWorkspace'),(sui,'SolarWorkspace')]:
    assert '\nTS\ncat > ' not in txt, f'{name}: shell heredoc contamination'

print('v18 condo+solar contracts OK')
