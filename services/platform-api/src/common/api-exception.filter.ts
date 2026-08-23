import {ArgumentsHost,Catch,ExceptionFilter,HttpException,HttpStatus} from '@nestjs/common';

function normalizeMessage(value:unknown){
  if(typeof value==='string')return value;
  if(Array.isArray(value))return value.join('; ');
  if(value&&typeof value==='object'){
    const v=value as any;
    if(typeof v.message==='string')return v.message;
    if(Array.isArray(v.message))return v.message.join('; ');
    if(typeof v.error==='string')return v.error;
  }
  return 'internal_error';
}

@Catch()
export class ApiExceptionFilter implements ExceptionFilter{
  catch(exception:unknown,host:ArgumentsHost){
    const ctx=host.switchToHttp();
    const response:any=ctx.getResponse();
    const request:any=ctx.getRequest();
    const status=exception instanceof HttpException?exception.getStatus():HttpStatus.INTERNAL_SERVER_ERROR;
    const body=exception instanceof HttpException?exception.getResponse():null;
    const message=normalizeMessage(body||((exception as any)?.message));
    const code=(body&&typeof body==='object'&&typeof (body as any).code==='string')?(body as any).code:message.toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'').slice(0,96)||'internal_error';
    const fields=(body&&typeof body==='object'&&(body as any).fields&&typeof (body as any).fields==='object')?(body as any).fields:undefined;
    const traceId=String(request?.traceId||request?.requestId||request?.id||'');
    response.status(status).send({
      code,
      message,
      ...(fields?{fields}:{}),
      trace_id:traceId||null,
      retryable:status===408||status===409||status===425||status===429||status>=500,
    });
  }
}
