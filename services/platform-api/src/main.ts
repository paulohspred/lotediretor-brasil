import 'reflect-metadata';
import {NestFactory} from '@nestjs/core';
import {FastifyAdapter,NestFastifyApplication} from '@nestjs/platform-fastify';
import cookie from '@fastify/cookie';
import multipart from '@fastify/multipart';
import {join} from 'path';
import {AppModule} from './app.module';
import {AuthService} from './auth.service';
import {runMigrations} from './migrations';
import {beginHttpTrace,finishHttpTrace,traceparent} from './telemetry';
import {registerGraphql} from './graphql';
import {ApiExceptionFilter} from './common/api-exception.filter';

async function main(){
  const db=process.env.PLATFORM_DATABASE_URL||'';
  const migrationDb=process.env.PLATFORM_MIGRATION_DATABASE_URL||db;
  if(process.env.RUN_MIGRATIONS_ON_START==='true'&&migrationDb)await runMigrations(migrationDb,join(process.cwd(),'db/platform/migrations'));
  if(!db)throw new Error('PLATFORM_DATABASE_URL is required');
  const app=await NestFactory.create<NestFastifyApplication>(AppModule,new FastifyAdapter({logger:true,bodyLimit:Number(process.env.MAX_JSON_BODY_BYTES||2*1024*1024)}));
  app.useGlobalFilters(new ApiExceptionFilter());
  const fastify=app.getHttpAdapter().getInstance();
  fastify.addHook('onRequest',async(req:any,reply:any)=>{
    const incoming=String(req.headers?.['x-request-id']||'').slice(0,128);
    const id=incoming||String(req.id);
    req.requestId=id;
    const tr=beginHttpTrace(req);
    reply.header('traceparent',traceparent(tr));
    reply.header('x-request-id',id);
    reply.header('x-trace-id',tr.traceId);
    reply.header('x-content-type-options','nosniff');
    reply.header('referrer-policy','strict-origin-when-cross-origin');
  });
  fastify.addHook('onResponse',async(req:any,reply:any)=>{finishHttpTrace('platform-api',req,reply);});
  await app.register(cookie as any);
  await app.register(multipart as any,{limits:{fileSize:Number(process.env.MAX_UPLOAD_BYTES||25*1024*1024),files:1,fields:8}});
  await registerGraphql(fastify,app.get(AuthService));
  await app.listen({host:'0.0.0.0',port:Number(process.env.PORT||3001)});
}
main().catch(e=>{console.error(e);process.exit(1)});
