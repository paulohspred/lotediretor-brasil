from pathlib import Path

def must(path,*needles):
    text=Path(path).read_text()
    for n in needles: assert n in text, f'{path}: missing {n}'
    return text
m=must('db/platform/migrations/190_v19_publication_scope.sql','ADD COLUMN IF NOT EXISTS dataset_code','source_publication_active_dataset_uq',"s.metadata->>'dataset_code'")
lab=must('workers/data-pipelines/municipality_lab.py','dataset_code=%s','source.publication(source_id,municipality_ibge,dataset_code,snapshot_id,status)','promote_parcels','promote_zones','planning.zone','geo.parcel')
api=must('services/platform-api/src/v7.controller.ts','snapshot_dataset_code','dataset_code is not distinct from $3','source.publication_event(source_id,municipality_ibge,dataset_code')
terr=must('services/platform-api/src/territorial/territorial.service.ts','p.dataset_code=sc.dataset_code')
print('v19 dataset-scoped publication + domain promotion contracts OK')
