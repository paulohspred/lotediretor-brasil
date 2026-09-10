'use client';
import {useState} from 'react';
import {Card,Badge} from '@lotediretor/ui';
import {getJson,postJson,State,useApi,waitForJob} from './ApiBox';

const samplePolygon={type:'Polygon',coordinates:[[[-46.634,-23.551],[-46.632,-23.551],[-46.632,-23.549],[-46.634,-23.549],[-46.634,-23.551]]]};
const sampleMix=[{name:'2D',target_area_m2:65,min_count:8,target_share:.55},{name:'3D',target_area_m2:82,min_count:4,target_share:.30},{name:'1D',target_area_m2:45,min_count:2,target_share:.15}];
const sampleTin=[{x:0,y:0,z:100},{x:10,y:0,z:101},{x:0,y:10,z:102},{x:10,y:10,z:103}];

export function AitecWorkspace(){
  const {data,error,loading,reload}=useApi<any>('/api/v1/aitec/projects');
  const [selected,setSelected]=useState('');const [detail,setDetail]=useState<any>(null);const [name,setName]=useState('Estudo de massa');
  const [polygonText,setPolygonText]=useState(JSON.stringify(samplePolygon));const [setback,setSetback]=useState('3');const [ca,setCa]=useState('2.0');const [to,setTo]=useState('0.60');const [tp,setTp]=useState('0.15');const [height,setHeight]=useState('24');
  const [spaces,setSpaces]=useState('40');const [stallWidth,setStallWidth]=useState('2.5');const [stallLength,setStallLength]=useState('5.0');const [aisleWidth,setAisleWidth]=useState('6.0');
  const [accessLon,setAccessLon]=useState('-46.634');const [accessLat,setAccessLat]=useState('-23.550');const [roadWidth,setRoadWidth]=useState('6');
  const [unitMixText,setUnitMixText]=useState(JSON.stringify(sampleMix));const [minUnits,setMinUnits]=useState('14');const [terrainText,setTerrainText]=useState('[]');
  const [count,setCount]=useState('30');const [seed,setSeed]=useState('1903');const [out,setOut]=useState<any>(null);const [solutions,setSolutions]=useState<any>(null);const [solutionDetail,setSolutionDetail]=useState<any>(null);
  const [jobSamplesText,setJobSamplesText]=useState(JSON.stringify(sampleTin,null,2));const [jobSeed,setJobSeed]=useState('42');const [jobState,setJobState]=useState<any>(null);const [jobError,setJobError]=useState('');const [jobRunning,setJobRunning]=useState(false);

  async function create(){const p:any=await postJson('/api/v1/aitec/projects',{name});await reload();setSelected(p.id);await load(p.id)}
  async function load(id:string){setSelected(id);setDetail(await getJson(`/api/v1/aitec/projects/${id}`));setSolutions(await getJson(`/api/v1/aitec/projects/${id}/solutions`));setSolutionDetail(null);setJobState(null);setJobError('')}
  async function generate(){if(!selected)return;let polygon:any,unitMix:any,terrain:any;try{polygon=JSON.parse(polygonText);unitMix=JSON.parse(unitMixText);terrain=JSON.parse(terrainText)}catch{setOut({error:'GeoJSON/Unit Mix/Terreno JSON inválido'});return}const r=await postJson(`/api/v1/aitec/projects/${selected}/solutions/generate`,{polygon,setbackM:Number(setback),caMax:Number(ca),toMax:Number(to),tpMin:Number(tp),heightMaxM:Number(height),requiredSpaces:Number(spaces),stallWidthM:Number(stallWidth),stallLengthM:Number(stallLength),aisleWidthM:Number(aisleWidth),accessPoint:{type:'Point',coordinates:[Number(accessLon),Number(accessLat)]},accessRequired:true,roadWidthM:Number(roadWidth),unitMix,minTotalUnits:Number(minUnits),terrainSamples:terrain,coreAreaM2:40,circulationWidthM:1.8,count:Number(count),seed:Number(seed),efficiency:.78,avgUnitAreaM2:65,baseDate:new Date().toISOString().slice(0,10),objectives:{estimated_net_area_m2:'MAX',tp_achieved:'MAX',parking_area_m2:'MIN'}},{idempotent:true});setOut(r);await load(selected)}
  async function openSolution(id:string){setSolutionDetail(await getJson(`/api/v1/aitec/solutions/${id}`))}
  async function lockFirstBuilding(){const id=solutionDetail?.solution?.id;const first=solutionDetail?.geometryObjects?.find((x:any)=>x.object_type==='BUILDING_FOOTPRINT');if(!id||!first)return;await postJson(`/api/v1/aitec/solutions/${id}/locks`,{geometryObjectIds:[first.id],lockCode:'GEOMETRY'});await openSolution(id)}
  async function branch(){const id=solutionDetail?.solution?.id;if(!id)return;const r=await postJson(`/api/v1/aitec/solutions/${id}/branch`,{seed:Number(solutionDetail.solution.seed||0)+101,count:12,baseDate:new Date().toISOString().slice(0,10)});setOut(r);if(selected)await load(selected)}
  async function exportSolution(kind:'geojson'|'csv'){const id=solutionDetail?.solution?.id;if(!id)return;setOut(await postJson(`/api/v1/aitec/solutions/${id}/export-${kind}`,{}))}
  async function runTinJob(){
    if(!selected)return;setJobError('');setJobRunning(true);setJobState(null);
    try{
      const samples=JSON.parse(jobSamplesText);if(!Array.isArray(samples)||samples.length<3)throw new Error('Informe ao menos três amostras TIN.');
      const queued:any=await postJson(`/api/v1/aitec/projects/${selected}/jobs`,{operation:'terrain.tin',seed:Number(jobSeed),kwargs:{samples}},{idempotent:true});
      setJobState(queued);
      // The worker can legitimately spend up to 180 s per attempt and retry three
      // times. Use the durable SSE job stream instead of a 90 s client poll timeout.
      await waitForJob(queued.id,12*60*1000);
      const completed:any=await getJson(`/api/v1/aitec/jobs/${queued.id}`);
      setJobState(completed);
      if(completed.status!=='COMPLETED')throw new Error(`Job ${completed.status}: ${completed.error||'falha sem detalhe'}`);
    }catch(e:any){setJobError(e?.message||String(e));try{if(jobState?.id)setJobState(await getJson(`/api/v1/aitec/jobs/${jobState.id}`))}catch{}}finally{setJobRunning(false)}
  }

  return <>
    <header className="pageHead"><div><h1>A.I TEC</h1><p>Site Solver geometry-aware, alternativas persistidas e fila v20 auditável para operações determinísticas do solver.</p></div><Badge tone="success">v20 · pré-projeto</Badge></header>
    <State loading={loading} error={error}/>
    <div className="twoCol">
      <Card className="panel noTop"><h2>Projetos</h2><div className="inlineForm"><input aria-label="Nome do projeto" value={name} onChange={e=>setName(e.target.value)}/><button onClick={()=>void create()}>Criar</button></div>{data?.items?.map((x:any)=><button className={selected===x.id?'activeChoice':'secondary'} key={x.id} onClick={()=>void load(x.id)}><b>{x.name}</b><span>{x.status} · {x.scenarios} cenários legados</span></button>)}{detail&&<><h3>Contexto</h3><pre>{JSON.stringify(detail,null,2)}</pre></>}</Card>
      <Card className="panel noTop"><h2>Gerar alternativas</h2><label>Terreno GeoJSON<textarea rows={6} value={polygonText} onChange={e=>setPolygonText(e.target.value)}/></label>
        <div className="inlineForm"><label>Recuo (m)<input value={setback} onChange={e=>setSetback(e.target.value)}/></label><label>CA máx.<input value={ca} onChange={e=>setCa(e.target.value)}/></label><label>TO máx.<input value={to} onChange={e=>setTo(e.target.value)}/></label><label>TP mín.<input value={tp} onChange={e=>setTp(e.target.value)}/></label></div>
        <div className="inlineForm"><label>Altura máx. (m)<input value={height} onChange={e=>setHeight(e.target.value)}/></label><label>Vagas-meta<input value={spaces} onChange={e=>setSpaces(e.target.value)}/></label><label>Vaga L (m)<input value={stallWidth} onChange={e=>setStallWidth(e.target.value)}/></label><label>Vaga C (m)<input value={stallLength} onChange={e=>setStallLength(e.target.value)}/></label><label>Faixa (m)<input value={aisleWidth} onChange={e=>setAisleWidth(e.target.value)}/></label></div>
        <h3>Acesso explícito</h3><div className="inlineForm"><label>Longitude<input value={accessLon} onChange={e=>setAccessLon(e.target.value)}/></label><label>Latitude<input value={accessLat} onChange={e=>setAccessLat(e.target.value)}/></label><label>Via (m)<input value={roadWidth} onChange={e=>setRoadWidth(e.target.value)}/></label></div>
        <h3>Programa</h3><label>Unit mix JSON<textarea rows={4} value={unitMixText} onChange={e=>setUnitMixText(e.target.value)}/></label><div className="inlineForm"><label>Mínimo de unidades<input value={minUnits} onChange={e=>setMinUnits(e.target.value)}/></label><label>Alternativas<input value={count} onChange={e=>setCount(e.target.value)}/></label><label>Seed<input value={seed} onChange={e=>setSeed(e.target.value)}/></label></div>
        <label>Amostras topográficas JSON (longitude, latitude, elevation_m)<textarea rows={3} value={terrainText} onChange={e=>setTerrainText(e.target.value)}/></label>
        <button disabled={!selected} onClick={()=>void generate()}>Gerar, validar e persistir</button><small>O ponto de acesso é obrigatório neste fluxo e nunca é inferido. Terrain/cut-fill só é calculado quando amostras explícitas são fornecidas. A saída continua pré-projeto.</small>{out&&<><h3>Última operação</h3><pre>{JSON.stringify(out,null,2)}</pre></>}
      </Card>
    </div>

    <Card className="panel" data-testid="aitec-job-panel"><h2>Job v20 persistido</h2><p>Executa <code>terrain.tin</code> pela fila durável. O resultado preserva solver version, classificação e exigência de revisão profissional.</p>
      <label>Amostras TIN JSON<textarea aria-label="Amostras TIN JSON" rows={7} value={jobSamplesText} onChange={e=>setJobSamplesText(e.target.value)}/></label>
      <div className="inlineForm"><label>Seed do job<input aria-label="Seed do job" value={jobSeed} onChange={e=>setJobSeed(e.target.value)}/></label><button disabled={!selected||jobRunning} onClick={()=>void runTinJob()}>{jobRunning?'Executando job…':'Executar job v20'}</button></div>
      {jobError&&<div className="notice error" role="alert">{jobError}</div>}
      {jobState&&<><div className="notice neutral" data-testid="aitec-job-status">Status: <b>{jobState.status}</b> · job {jobState.id}</div><pre data-testid="aitec-job-result">{JSON.stringify(jobState,null,2)}</pre></>}
    </Card>

    {solutions&&<Card className="panel"><h2>Alternativas persistidas</h2>{solutions.items?.length?<table className="dataTable"><thead><tr><th>Alternativa</th><th>Status</th><th>Seed</th><th>Edifícios</th><th>Área líquida</th><th>Unidades</th><th>Vagas</th><th>Acesso</th><th>Terra</th><th>Pareto</th></tr></thead><tbody>{solutions.items.map((x:any)=><tr key={x.id} onClick={()=>void openSolution(x.id)} style={{cursor:'pointer'}}><td>{String(x.id).slice(0,8)}</td><td>{x.status}</td><td>{x.seed}</td><td>{x.metrics?.building_count??'—'}</td><td>{x.metrics?.estimated_net_area_m2??'—'} m²</td><td>{x.metrics?.total_units??'—'}</td><td>{x.metrics?.parking_spaces_generated??'—'} / {x.metrics?.required_spaces??'—'}</td><td>{x.metrics?.access_connected?'OK':'—'}</td><td>{x.metrics?.earthwork_m3==null?'—':`${x.metrics.earthwork_m3} m³`}</td><td>{x.is_pareto?'Sim':'—'}</td></tr>)}</tbody></table>:<div className="notice neutral">Ainda não há alternativas do Site Solver.</div>}</Card>}
    {solutionDetail&&<Card className="panel"><h2>Solução selecionada</h2><div className="inlineForm"><button onClick={()=>void lockFirstBuilding()}>Travar edifício 1</button><button className="secondary" onClick={()=>void branch()}>Branch + regenerate</button><button className="secondary" onClick={()=>void exportSolution('geojson')}>Exportar GeoJSON</button><button className="secondary" onClick={()=>void exportSolution('csv')}>Exportar CSV</button></div><pre>{JSON.stringify(solutionDetail,null,2)}</pre></Card>}
  </>;
}
