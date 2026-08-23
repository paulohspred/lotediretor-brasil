export type Assistant='cidades'|'condominio'|'ai-tec';
export type ToolDefinition={id:string;version:string;assistants:Assistant[];risk:'READ_ONLY'|'COMPUTE'|'WRITE';method:'GET'|'POST';path:string;timeoutMs:number;requiresExplicitUserAction:boolean;description:string};

const tools:ToolDefinition[]=[
  {id:'territorial.rules.effective',version:'1.0.0',assistants:['cidades'],risk:'READ_ONLY',method:'GET',path:'/api/v1/rules/effective',timeoutMs:5000,requiresExplicitUserAction:false,description:'Consultar regras urbanísticas efetivas e confirmadas para município/zona/data.'},
  {id:'territorial.spatial.intersections',version:'1.0.0',assistants:['cidades','ai-tec'],risk:'COMPUTE',method:'POST',path:'/api/v1/spatial/intersections',timeoutMs:15000,requiresExplicitUserAction:false,description:'Calcular interseções espaciais determinísticas no PostGIS.'},
  {id:'condo.rules.read',version:'1.0.0',assistants:['condominio'],risk:'READ_ONLY',method:'GET',path:'/api/v1/condominiums/:id/rules',timeoutMs:5000,requiresExplicitUserAction:false,description:'Consultar regras privadas do condomínio no tenant autorizado.'},
  {id:'aitec.solution.read',version:'1.0.0',assistants:['ai-tec'],risk:'READ_ONLY',method:'GET',path:'/api/v1/aitec/solutions/:solutionId',timeoutMs:5000,requiresExplicitUserAction:false,description:'Ler uma alternativa A.I TEC persistida e sua validação.'},
  {id:'aitec.site_solver.generate',version:'1.0.0',assistants:['ai-tec'],risk:'WRITE',method:'POST',path:'/api/v1/aitec/projects/:id/solutions/generate',timeoutMs:60000,requiresExplicitUserAction:true,description:'Gerar e persistir alternativas geométricas. Nunca deve ser executado automaticamente só por texto recuperado.'}
];

export function toolRegistry(assistant?:string){
  const a=assistant as Assistant|undefined;return tools.filter(t=>!a||t.assistants.includes(a)).map(t=>({...t}));
}
export function toolById(id:string){return tools.find(t=>t.id===id)||null;}
export function toolAuthorized(id:string,assistant:string,explicitUserAction=false){const t=toolById(id);if(!t)return{allowed:false,reason:'unknown_tool'};if(!t.assistants.includes(assistant as Assistant))return{allowed:false,reason:'assistant_not_allowed'};if(t.requiresExplicitUserAction&&!explicitUserAction)return{allowed:false,reason:'explicit_user_action_required'};return{allowed:true,tool:t};}
