import {Injectable} from '@nestjs/common';
import Redis from 'ioredis';
import {Pool} from 'pg';
import {randomBytes,createHash} from 'crypto';
import {v7 as uuidv7,v5 as uuidv5,validate as uuidValidate} from 'uuid';

const LOCAL_ORG='0198f001-0000-7000-8000-000000000001';
const SUBJECT_NAMESPACE='d17bd7bc-59cc-4e49-bbba-50f9ce7b23bf';

@Injectable()
export class AuthService{
  redis=new Redis(process.env.VALKEY_URL||'redis://localhost:6379/0');
  pool=new Pool({connectionString:process.env.PLATFORM_DATABASE_URL});
  publicIssuer=process.env.KEYCLOAK_PUBLIC_ISSUER||'';internalIssuer=process.env.KEYCLOAK_INTERNAL_ISSUER||this.publicIssuer;clientId=process.env.OIDC_CLIENT_ID||'lotediretor-app';secret=process.env.OIDC_CLIENT_SECRET||'';redirect=process.env.OIDC_REDIRECT_URI||'http://localhost:8080/api/v1/auth/callback';
  start(returnTo:string){returnTo=(returnTo?.startsWith('/app/')||returnTo?.startsWith('/admin/'))?returnTo:'/app/dashboard';const state=randomBytes(24).toString('base64url');const verifier=randomBytes(48).toString('base64url');const challenge=createHash('sha256').update(verifier).digest('base64url');const u=new URL(this.publicIssuer+'/protocol/openid-connect/auth');u.searchParams.set('client_id',this.clientId);u.searchParams.set('redirect_uri',this.redirect);u.searchParams.set('response_type','code');u.searchParams.set('scope','openid profile email');u.searchParams.set('state',state);u.searchParams.set('code_challenge',challenge);u.searchParams.set('code_challenge_method','S256');return{url:u.toString(),state,verifier,returnTo:returnTo||'/app/dashboard'};}
  async callback(code:string,verifier:string){
    const r=await fetch(this.internalIssuer+'/protocol/openid-connect/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'authorization_code',client_id:this.clientId,client_secret:this.secret,code,redirect_uri:this.redirect,code_verifier:verifier})});if(!r.ok)throw new Error('OIDC token exchange failed '+r.status);const tok:any=await r.json();
    const ur=await fetch(this.internalIssuer+'/protocol/openid-connect/userinfo',{headers:{authorization:`Bearer ${tok.access_token}`}});if(!ur.ok)throw new Error('OIDC userinfo failed');const user:any=await ur.json();let keycloakRoles:string[]=[];try{const payload=JSON.parse(Buffer.from(tok.access_token.split('.')[1],'base64url').toString());keycloakRoles=payload?.realm_access?.roles||[];}catch{}
    const userId=uuidValidate(String(user.sub||''))?String(user.sub):uuidv5(String(user.sub||user.email),SUBJECT_NAMESPACE);
    await this.pool.query(`insert into iam.user_profile(id,email,display_name) values($1,$2,$3) on conflict(id) do update set email=excluded.email,display_name=excluded.display_name,privacy_status='ACTIVE',anonymized_at=null`,[userId,String(user.email||`${userId}@oidc.local`),user.name||user.preferred_username||null]);
    let memberships=(await this.pool.query(`select m.organization_id,m.role,o.status from iam.membership m join iam.organization o on o.id=m.organization_id where m.user_id=$1 and o.status='ACTIVE' order by m.created_at`,[userId])).rows;
    const allowLocal=process.env.ALLOW_LOCAL_AUTO_MEMBERSHIP==='true'||process.env.NODE_ENV!=='production';
    if(!memberships.length&&allowLocal){await this.pool.query(`insert into iam.membership(organization_id,user_id,role) values($1,$2,$3) on conflict(organization_id,user_id) do update set role=excluded.role`,[LOCAL_ORG,userId,keycloakRoles.includes('admin')?'admin':'user']);memberships=[{organization_id:LOCAL_ORG,role:keycloakRoles.includes('admin')?'admin':'user',status:'ACTIVE'}];}
    if(!memberships.length)throw new Error('OIDC user has no active organization membership');
    const organizationId=String(memberships[0].organization_id);const membershipRole=String(memberships[0].role);const ent=(await this.pool.query(`select snapshot from core.entitlement_snapshot where organization_id=$1 and valid_from<=now() and (valid_to is null or valid_to>now()) order by valid_from desc limit 1`,[organizationId])).rows[0]?.snapshot||{tier:'unassigned',modules:[],quotas:{}};
    const roles=Array.from(new Set([...keycloakRoles,membershipRole]));const sid=uuidv7();const session={id:userId,email:user.email,name:user.name||user.preferred_username,roles,organizationId,entitlements:ent,memberships:memberships.map((m:any)=>({organizationId:m.organization_id,role:m.role}))};await this.redis.set(`session:${sid}`,JSON.stringify(session),'EX',60*60*8);return{sid,session};
  }
  async get(sid?:string){if(!sid)return null;const x=await this.redis.get(`session:${sid}`);return x?JSON.parse(x):null;}
  async logout(sid?:string){if(sid)await this.redis.del(`session:${sid}`);}
  async logoutUser(userId:string){
    let cursor='0',revoked=0;
    do{
      const [next,keys]=await this.redis.scan(cursor,'MATCH','session:*','COUNT',200);cursor=next;
      if(keys.length){
        const values=await this.redis.mget(...keys);const doomed:string[]=[];
        for(let i=0;i<keys.length;i++)try{if(JSON.parse(values[i]||'{}')?.id===userId)doomed.push(keys[i]);}catch{}
        if(doomed.length){revoked+=doomed.length;await this.redis.del(...doomed);}
      }
    }while(cursor!=='0');
    return revoked;
  }
}
