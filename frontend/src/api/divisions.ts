import{request}from './client';import type{DivisionVersion,RatioEdge,RatioRow,ConversionDraft,Target}from '../types/domain';
export const getVersions=()=>request<DivisionVersion[]>('/division-versions');
export const createVersion=(data:unknown)=>request<DivisionVersion>('/division-versions',{method:'POST',body:JSON.stringify(data)});
export const getRatioEdges=()=>request<RatioEdge[]>('/division-ratios');
export const saveRatioMap=(from:number,to:number,rows:RatioRow[])=>request<RatioEdge>(`/division-ratios/${from}/${to}`,{method:'PUT',body:JSON.stringify({ratios:rows})});
export const getDrafts=(batchId:number)=>request<ConversionDraft[]>(`/batches/${batchId}/conversion-drafts`);
export const createDraft=(batchId:number,from_version_id:number,to_version_id:number)=>request<ConversionDraft>(`/batches/${batchId}/conversion-drafts`,{method:'POST',body:JSON.stringify({from_version_id,to_version_id})});
export const publishDraft=(id:number)=>request<{draft:ConversionDraft;targets:Target[]}>(`/conversion-drafts/${id}/publish`,{method:'POST'});
