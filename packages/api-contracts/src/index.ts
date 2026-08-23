export type ApiError={code:string;message:string;fields?:Record<string,unknown>;trace_id:string|null;retryable:boolean};
export type CursorPage<T>={items:T[];nextCursor?:string|null;hasMore?:boolean};
export type JobStatus='QUEUED'|'PROCESSING'|'COMPLETED'|'FAILED'|'CANCELLED'|'REJECTED'|string;
export type JobSnapshot={id:string;kind:string;status:JobStatus;progress?:number|null;artifactKey?:string|null;updatedAt?:string|null};
export type JobSseEvent={type:'job'|'error';data:JobSnapshot|ApiError};
export type IdempotencyMeta={replayed:boolean;key:string|null};
export type SourceConfidence='CONFIRMADO'|'CALCULADO'|'INFERIDO'|'PENDENTE'|'CONFLITANTE'|'NÃO DISPONÍVEL';
