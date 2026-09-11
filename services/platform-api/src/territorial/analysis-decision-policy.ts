import type {UrbanViabilityStatus} from './urban-viability';

export type AnalysisRunStatus='COMPLETED'|'NEEDS_REVIEW'|'INSUFFICIENT_DATA';

export type AnalysisDecisionSignals={
  viabilityStatus:UrbanViabilityStatus;
  hasRules:boolean;
  hasSpatialEvidence:boolean;
  legalTemporalConflictCount:number;
  legalTemporalUnknownCount:number;
  legalTemporalPendingCount:number;
};

export function deriveAnalysisRunStatus(signals:AnalysisDecisionSignals):AnalysisRunStatus{
  if(signals.legalTemporalConflictCount>0||signals.legalTemporalUnknownCount>0||signals.legalTemporalPendingCount>0)return 'NEEDS_REVIEW';
  if(signals.viabilityStatus==='CONFLICTING'||signals.viabilityStatus==='UNKNOWN')return 'NEEDS_REVIEW';
  if(!signals.hasRules&&!signals.hasSpatialEvidence)return 'INSUFFICIENT_DATA';
  return 'COMPLETED';
}
