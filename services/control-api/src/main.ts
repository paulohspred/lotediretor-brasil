import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { FastifyAdapter, NestFastifyApplication } from '@nestjs/platform-fastify';
import cookie from '@fastify/cookie';
import { join } from 'path';
import { ControlV20Module } from './v20.module';
import { runMigrations } from './migrations';
import { beginHttpTrace, finishHttpTrace, traceparent } from './telemetry';
import {ApiExceptionFilter} from './common/api-exception.filter';

async function main() {
  const db = process.env.CONTROL_DATABASE_URL || '';
  const migrationDb = process.env.CONTROL_MIGRATION_DATABASE_URL || db;
  if (process.env.RUN_MIGRATIONS_ON_START==='true' && migrationDb) await runMigrations(migrationDb, join(process.cwd(), 'db/control/migrations'));
  if (!db) throw new Error('CONTROL_DATABASE_URL is required');
  const app = await NestFactory.create<NestFastifyApplication>(ControlV20Module, new FastifyAdapter({ logger: true }));
  app.useGlobalFilters(new ApiExceptionFilter());
  const fastify = app.getHttpAdapter().getInstance();
  fastify.addHook('onRequest', async (req:any, reply:any) => {
    const incoming=String(req.headers?.['x-request-id']||'').slice(0,128);const id=incoming||String(req.id);req.requestId=id;
    const tr=beginHttpTrace(req);reply.header('traceparent',traceparent(tr));reply.header('x-request-id',id);reply.header('x-trace-id',tr.traceId);reply.header('x-content-type-options','nosniff');
  });
  fastify.addHook('onResponse', async (req:any, reply:any) => { finishHttpTrace('control-api',req,reply); });
  await app.register(cookie as any);
  await app.listen({ host: '0.0.0.0', port: Number(process.env.PORT || 3002) });
}
main().catch((error) => {console.error(error);process.exit(1);});
