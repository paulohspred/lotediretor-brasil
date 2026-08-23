import {Controller,Get} from '@nestjs/common';
import {PLATFORM_VERSION} from '../version';
import {routeCatalog} from './route-catalog';

function pathItem(route:(typeof routeCatalog)[number]){
  return {
    summary:route.summary,
    tags:route.tags,
    security:route.auth==='public'?[]:[{cookieSession:[]}],
    ...(route.idempotent?{parameters:[{name:'Idempotency-Key',in:'header',required:false,schema:{type:'string',maxLength:160},description:'Chave de repetição segura para comandos; quando enviada, a resposta é reproduzida sem duplicar efeito.'}]}:{}),
    responses:route.stream?{'200':{description:'Fluxo SSE de progresso do job',content:{'text/event-stream':{schema:{type:'string'}}}}}:{'200':{description:'Sucesso'},'400':{$ref:'#/components/responses/Error'},'401':{$ref:'#/components/responses/Error'},'403':{$ref:'#/components/responses/Error'},'409':{$ref:'#/components/responses/Error'},'500':{$ref:'#/components/responses/Error'}},
  };
}

@Controller('api/v1')
export class OpenApiController{
  @Get('openapi.json')
  document(){
    const paths:any={};
    for(const route of routeCatalog){paths[route.path]??={};paths[route.path][route.method]=pathItem(route);}
    return {
      openapi:'3.1.0',
      info:{title:'LoteDiretor Platform API',version:PLATFORM_VERSION,description:'Contrato público versionado da Platform API. A cobertura cresce por bounded context e contract tests.'},
      servers:[{url:'/'}],
      paths,
      components:{
        securitySchemes:{cookieSession:{type:'apiKey',in:'cookie',name:'ld_session'}},
        schemas:{ApiError:{type:'object',required:['code','message','trace_id','retryable'],properties:{code:{type:'string'},message:{type:'string'},fields:{type:'object',additionalProperties:true},trace_id:{type:['string','null']},retryable:{type:'boolean'}}}},
        responses:{Error:{description:'Erro padronizado',content:{'application/json':{schema:{$ref:'#/components/schemas/ApiError'}}}}},
      },
    };
  }
}
