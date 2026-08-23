export type ModuleCode =
  | 'imovel360' | 're-rural' | 'condominio' | 'energia-solar' | 'ai-tec' | 'prefeitura' | 'relatorios';
export type FindingStatus = 'CONFIRMADO'|'CALCULADO'|'INFERIDO'|'PENDENTE'|'CONFLITANTE'|'NAO_DISPONIVEL';
export type AiDecision = 'PERMITIDO'|'PROIBIDO'|'CONDICIONADO'|'NAO_DETERMINADO'|'CONFLITO';
export interface ModuleNavItem { code: ModuleCode; label: string; href: string; icon: string; }
export interface EntitlementSnapshot { modules: ModuleCode[]; quotas: Record<string, number>; tier: string; }
export interface UserSession { id:string; email:string; name?:string; roles:string[]; organizationId:string; entitlements:EntitlementSnapshot; }
