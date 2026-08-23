import { Body, Controller, Get, HttpException, HttpStatus, Module, Param, Post, Query, Req } from '@nestjs/common';
import { Pool } from 'pg';
import Redis from 'ioredis';
import {WebhookSignatureValidator,InvalidWebhookSignatureError} from 'mercadopago';
import {ControlV7Controller} from './v7.controller';
import {ControlMetricsController} from './v8.metrics.controller';

const pool = new Pool({ connectionString: process.env.CONTROL_DATABASE_URL });
const redis = new Redis(process.env.VALKEY_URL || 'redis://localhost:6379/0');
import {CONTROL_VERSION} from './version';
const VERSION=CONTROL_VERSION;

async function requireAdmin(req: any) {
  const sid = req.cookies?.ld_session;
  if (!sid) throw new HttpException('unauthorized', HttpStatus.UNAUTHORIZED);
  const raw = await redis.get(`session:${sid}`);
  if (!raw) throw new HttpException('unauthorized', HttpStatus.UNAUTHORIZED);
  const session = JSON.parse(raw);
  if (!session.roles?.includes('admin')) throw new HttpException('forbidden', HttpStatus.FORBIDDEN);
  return session;
}

@Controller('control/v1')
class ControlController {
  @Get('health')
  health() {
    return { ok: true, service: 'control-api', version: VERSION, recovery: false };
  }

  @Get('metrics/executive')
  async metrics(@Req() req: any) {
    await requireAdmin(req);
    const [tenants, subscriptions, payments, traces, tickets, approvals] = await Promise.all([
      pool.query("select count(*)::int n from tenant.tenant where status='ACTIVE'"),
      pool.query("select count(*)::int n from billing.subscription where status in ('ACTIVE','AUTHORIZED')"),
      pool.query("select coalesce(sum(net_cents),0)::bigint n from billing.payment where status in ('APPROVED','PAID') and created_at >= date_trunc('day',now())"),
      pool.query("select count(*)::int n from ai_ops.trace where created_at >= date_trunc('day',now())"),
      pool.query("select count(*)::int n from support.ticket where status not in ('CLOSED','RESOLVED')"),
      pool.query("select count(*)::int n from admin.approval where status='PENDING'"),
    ]);
    return {
      activeTenants: tenants.rows[0]?.n || 0,
      activeSubscriptions: subscriptions.rows[0]?.n || 0,
      receivedTodayCents: Number(payments.rows[0]?.n || 0),
      aiTracesToday: traces.rows[0]?.n || 0,
      openTickets: tickets.rows[0]?.n || 0,
      pendingApprovals: approvals.rows[0]?.n || 0,
      currency: 'BRL',
      version: VERSION,
    };
  }

  @Get('tenants')
  async tenants(@Req() req: any) {
    await requireAdmin(req);
    return { items: (await pool.query('select id,name,kind,status,platform_organization_id,created_at from tenant.tenant order by created_at desc limit 100')).rows };
  }

  @Post('tenants')
  async createTenant(@Req() req: any, @Body() body: any) {
    const session = await requireAdmin(req);
    const r = await pool.query(
      `insert into tenant.tenant(name,kind,status,platform_organization_id)
       values($1,$2,'ACTIVE',$3) returning id,name,kind,status,platform_organization_id,created_at`,
      [String(body?.name || 'Novo tenant'), String(body?.kind || 'COMPANY'), body?.platformOrganizationId || null],
    );
    await pool.query(
      `insert into admin.audit_event(actor,action,object_type,object_id,after_data,reason)
       values($1,'TENANT_CREATED','tenant',$2,$3::jsonb,$4)`,
      [session.email || session.id, r.rows[0].id, JSON.stringify(r.rows[0]), body?.reason || 'Admin UI'],
    );
    return r.rows[0];
  }

  @Get('billing/summary')
  async billing(@Req() req: any) {
    await requireAdmin(req);
    const r = await pool.query(
      `select t.id tenant_id,t.name,
              s.status subscription_status,pv.code plan_code,pv.name plan_name,pv.monthly_cents,
              coalesce((select sum(le.amount_cents) from billing.ledger_entry le where le.tenant_id=t.id),0)::bigint ledger_cents
         from tenant.tenant t
         left join lateral (select * from billing.subscription bs where bs.tenant_id=t.id order by bs.created_at desc limit 1) s on true
         left join catalog.plan_version pv on pv.id=s.plan_version_id
        order by t.name`,
    );
    return { items: r.rows };
  }

  @Get('cms/pages')
  async cmsPages(@Req() req: any) {
    await requireAdmin(req);
    const r = await pool.query(
      `select p.id,p.slug,p.title,p.status,p.published_version_id,p.created_at,
              (select max(v.version) from cms.page_version v where v.page_id=p.id) latest_version
         from cms.page p order by p.slug`,
    );
    return { items: r.rows };
  }

  @Post('cms/pages/:id/versions')
  async createCmsVersion(@Req() req: any, @Param('id') id: string, @Body() body: any) {
    const session = await requireAdmin(req);
    const page = await pool.query('select id from cms.page where id=$1', [id]);
    if (!page.rowCount) throw new HttpException('cms_page_not_found', 404);
    const r = await pool.query(
      `insert into cms.page_version(page_id,version,blocks,seo)
       select $1,coalesce(max(version),0)+1,$2::jsonb,$3::jsonb from cms.page_version where page_id=$1
       returning id,page_id,version,blocks,seo,created_at`,
      [id, JSON.stringify(body?.blocks || []), JSON.stringify(body?.seo || {})],
    );
    await pool.query(`insert into admin.audit_event(actor,action,object_type,object_id,after_data,reason) values($1,'CMS_VERSION_CREATED','cms.page',$2,$3::jsonb,$4)`, [session.email || session.id,id,JSON.stringify({version:r.rows[0].version}),body?.reason || null]);
    return r.rows[0];
  }

  @Post('cms/pages/:id/publish')
  async publishCms(@Req() req: any, @Param('id') id: string, @Body() body: any) {
    const session = await requireAdmin(req);
    const versionId = String(body?.versionId || '');
    const v = await pool.query('select id,version from cms.page_version where id=$1 and page_id=$2', [versionId,id]);
    if (!v.rowCount) throw new HttpException('cms_version_not_found', 404);
    const r = await pool.query(`update cms.page set published_version_id=$2,status='PUBLISHED' where id=$1 returning id,slug,title,status,published_version_id`, [id,versionId]);
    if (!r.rowCount) throw new HttpException('cms_page_not_found', 404);
    await pool.query(`insert into admin.audit_event(actor,action,object_type,object_id,after_data,reason) values($1,'CMS_PUBLISHED','cms.page',$2,$3::jsonb,$4)`, [session.email || session.id,id,JSON.stringify({version:v.rows[0].version,versionId}),body?.reason || null]);
    return r.rows[0];
  }

  @Get('data-ops/sources')
  async dataOps(@Req() req: any) {
    await requireAdmin(req);
    const base = process.env.PLATFORM_INTERNAL_URL || 'http://platform-api:3001';
    const token = process.env.INTERNAL_API_TOKEN || '';
    try {
      const response = await fetch(`${base}/api/v1/internal/data-ops/sources`, { headers: { 'x-internal-token': token } });
      if (!response.ok) throw new Error(`platform ${response.status}`);
      return await response.json();
    } catch (error: any) {
      return { items: [], degraded: true, message: `Data Plane indisponível: ${error?.message || String(error)}` };
    }
  }

  @Get('ai-ops/traces')
  async traces(@Req() req: any) {
    await requireAdmin(req);
    const r = await pool.query(
      'select trace_id,tenant_id,assistant,model,status,question,evidence,rules,metadata,created_at from ai_ops.trace order by created_at desc limit 100',
    );
    return { items: r.rows };
  }

  @Post('ai-ops/traces')
  async createTrace(@Req() req: any, @Body() body: any) {
    await requireAdmin(req);
    const r = await pool.query(
      `insert into ai_ops.trace(trace_id,tenant_id,assistant,model,status,question,evidence,rules,metadata)
       values($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb)
       on conflict(trace_id) do update set status=excluded.status,evidence=excluded.evidence,rules=excluded.rules,metadata=excluded.metadata
       returning *`,
      [body.traceId, body.tenantId || null, body.assistant || 'cidades', body.model || null, body.status || 'RECORDED', body.question || null, JSON.stringify(body.evidence || []), JSON.stringify(body.rules || []), JSON.stringify(body.metadata || {})],
    );
    return r.rows[0];
  }

  @Get('support/tickets')
  async tickets(@Req() req: any) {
    await requireAdmin(req);
    return { items: (await pool.query('select * from support.ticket order by created_at desc limit 100')).rows };
  }

  @Post('support/tickets')
  async createTicket(@Req() req: any, @Body() body: any) {
    const session = await requireAdmin(req);
    const r = await pool.query(
      `insert into support.ticket(tenant_id,subject,status,priority,created_by)
       values($1,$2,'OPEN',$3,$4) returning *`,
      [body?.tenantId || null, String(body?.subject || 'Solicitação de suporte'), String(body?.priority || 'NORMAL'), session.email || session.id],
    );
    return r.rows[0];
  }

  @Get('approvals')
  async approvals(@Req() req: any) {
    await requireAdmin(req);
    return { items: (await pool.query('select * from admin.approval order by requested_at desc limit 100')).rows };
  }

  @Post('approvals/:id/approve')
  async approve(@Req() req: any, @Param('id') id: string, @Body() body: any) {
    const session = await requireAdmin(req);const actor=session.email||session.id;
    const c=await pool.connect();
    try{
      await c.query('BEGIN');
      const current=await c.query('select * from admin.approval where id=$1 for update',[id]);
      if(!current.rowCount)throw new HttpException('approval_not_found',404);
      const a=current.rows[0];if(a.requested_by===actor)throw new HttpException('maker_checker_violation',409);if(a.status!=='PENDING')throw new HttpException('approval_not_pending',409);
      let effect:any=null;
      if(a.action==='ACTIVATE_PLAN'&&a.object_type==='catalog.plan_version'){
        const plan=await c.query('select id,code,version from catalog.plan_version where id=$1',[a.object_id]);if(!plan.rowCount)throw new HttpException('plan_not_found',404);
        await c.query(`update catalog.plan_version set status='INACTIVE' where code=$1 and status='ACTIVE' and id<>$2`,[plan.rows[0].code,a.object_id]);
        effect=(await c.query(`update catalog.plan_version set status='ACTIVE' where id=$1 returning id,code,version,status`,[a.object_id])).rows[0];
      }else if(a.action==='PROMOTE_DEPLOYMENT'&&a.object_type==='release.deployment'){
        effect=(await c.query(`update release.deployment set status='APPROVED',approved_by=$2 where id=$1 and status in ('BUILT','TESTED','STAGING') returning id,environment,status,artifact_digest,approved_by`,[a.object_id,actor])).rows[0]||null;
        if(!effect)throw new HttpException('deployment_not_promotable',409);
      }
      const approved=(await c.query(`update admin.approval set status='APPROVED',approved_by=$2,reason=$3,decided_at=now() where id=$1 returning *`,[id,actor,body?.reason||a.reason||null])).rows[0];
      await c.query(`insert into admin.audit_event(actor,action,object_type,object_id,after_data,reason) values($1,'APPROVAL_EXECUTED',$2,$3,$4::jsonb,$5)`,[actor,a.object_type,a.object_id,JSON.stringify({approval:approved,effect}),body?.reason||null]);
      await c.query('COMMIT');return{approval:approved,effect};
    }catch(e){await c.query('ROLLBACK');throw e}finally{c.release()}
  }

  @Get('releases')
  async releases(@Req() req: any) {
    await requireAdmin(req);
    return { items: (await pool.query('select version,environment,status,artifact_digest,created_at from release.release order by created_at desc')).rows };
  }
}

@Controller('control/internal/v1')
class InternalController {
  private authorize(req: any) {
    const expected = process.env.INTERNAL_API_TOKEN || '';
    if (!expected || req.headers?.['x-internal-token'] !== expected) throw new HttpException('forbidden', 403);
  }

  @Post('ai-traces')
  async aiTrace(@Req() req: any, @Body() body: any) {
    this.authorize(req);
    const r = await pool.query(
      `insert into ai_ops.trace(trace_id,tenant_id,assistant,model,status,question,evidence,rules,metadata)
       values($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb)
       on conflict(trace_id) do update set status=excluded.status,evidence=excluded.evidence,rules=excluded.rules,metadata=excluded.metadata
       returning trace_id,status,created_at`,
      [body.traceId, body.tenantId || null, body.assistant || 'cidades', body.model || null, body.status || 'RECORDED', body.question || null, JSON.stringify(body.evidence || []), JSON.stringify(body.rules || []), JSON.stringify(body.metadata || {})],
    );
    return r.rows[0];
  }
}



@Controller('control/public/v1')
class PublicController {
  @Get('cms/pages/:slug')
  async cms(@Param('slug') slug:string){const r=await pool.query(`select p.slug,p.title,p.status,v.version,v.blocks,v.seo from cms.page p join cms.page_version v on v.id=p.published_version_id where p.slug=$1 and p.status='PUBLISHED'`,[slug]);if(!r.rowCount)throw new HttpException('page_not_found',404);return r.rows[0]}

  @Post('billing/mercadopago/webhook')
  async mercadoPagoWebhook(@Req() req:any,@Query('data.id') queryDataId:string,@Body() body:any){const secret=process.env.MERCADO_PAGO_WEBHOOK_SECRET||'';if(!secret)throw new HttpException('mercadopago_webhook_secret_not_configured',503);const xSignature=String(req.headers?.['x-signature']||'');const xRequestId=String(req.headers?.['x-request-id']||'');const dataId=String(queryDataId||body?.data?.id||'');if(!xSignature||!xRequestId||!dataId)throw new HttpException('missing_webhook_signature_fields',400);try{WebhookSignatureValidator.validate({xSignature,xRequestId,dataId,secret})}catch(err){if(err instanceof InvalidWebhookSignatureError)throw new HttpException('invalid_webhook_signature',401);throw err}const topic=String(body?.type||'unknown');const eventKey=String(body?.id||`${topic}:${dataId}:${xRequestId}`);await pool.query(`insert into billing.webhook_event(provider,event_key,payload,verified,request_id,resource_id,topic) values('MERCADO_PAGO',$1,$2::jsonb,true,$3,$4,$5) on conflict(provider,event_key) do update set payload=excluded.payload,verified=true,request_id=excluded.request_id,resource_id=excluded.resource_id,topic=excluded.topic`,[eventKey,JSON.stringify(body||{}),xRequestId,dataId,topic]);return{ok:true}}
}

@Module({ controllers: [ControlController, InternalController, PublicController, ControlV7Controller, ControlMetricsController] })
export class AppModule {}
