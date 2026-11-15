"""区划版本、拆并比例与换算草案的持久化与并发控制。

草案指纹覆盖换算用到的全部比例行（含修订号）：修订任一中间比例后，依赖它的
草案立即失效；发布前在行锁内重算指纹，保证发布与修订并发时不混用新旧比例。
"""
import hashlib,json
from datetime import datetime
from sqlalchemy import select,delete,update,and_,or_
from fastapi import HTTPException
from src.models import DivisionVersion,DivisionRatio,ConversionDraft,MarginTarget
from src.constants.enums import DraftStatus,Dimension
from src.utils.serializers import serialize
from .batch_service import get_batch
from .unit_service import list_units
from .raking_algorithm import validate_targets
from .division_math import convert_populations,ConversionError

def _version_names(db):return {v.id:v.name for v in db.scalars(select(DivisionVersion))}

def _edge_maps(db):
    edges={}
    for row in db.scalars(select(DivisionRatio)):
        edges.setdefault((row.from_version_id,row.to_version_id),{}).setdefault(row.from_zone,{})[row.to_zone]=row.ratio
    return edges

def _edge_rows(db,edge_pairs,lock=False):
    if not edge_pairs:return []
    condition=or_(*[and_(DivisionRatio.from_version_id==f,DivisionRatio.to_version_id==t) for f,t in edge_pairs])
    statement=select(DivisionRatio).where(condition).order_by(DivisionRatio.from_version_id,DivisionRatio.to_version_id,DivisionRatio.from_zone,DivisionRatio.to_zone)
    if lock:statement=statement.with_for_update()
    return list(db.scalars(statement))

def _fingerprint(rows):
    payload=[[r.from_version_id,r.to_version_id,r.from_zone,r.to_zone,repr(r.ratio),r.revision] for r in rows]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def _get_version(db,version_id):
    row=db.get(DivisionVersion,version_id)
    if not row:raise HTTPException(404,'区划版本不存在')
    return row

def list_versions(db):
    zones={}
    for row in db.scalars(select(DivisionRatio)):
        zones.setdefault(row.from_version_id,set()).add(row.from_zone)
        zones.setdefault(row.to_version_id,set()).add(row.to_zone)
    out=[]
    for v in db.scalars(select(DivisionVersion).order_by(DivisionVersion.id)):
        data=serialize(v);data['zones']=sorted(zones.get(v.id,set()));out.append(data)
    return out

def create_version(db,data):
    if db.scalar(select(DivisionVersion).where(DivisionVersion.code==data.code)):raise HTTPException(409,'版本编码已存在')
    if data.is_current:db.execute(update(DivisionVersion).values(is_current=False))
    row=DivisionVersion(**data.model_dump());db.add(row);db.flush();return row

def _edge_view(db,from_id,to_id,rows,versions):
    problems=[]
    totals={}
    for r in rows:totals[r.from_zone]=totals.get(r.from_zone,0)+r.ratio
    for zone,total in sorted(totals.items()):
        if abs(total-1)>1e-9:problems.append('%s 合计 %.6f ≠ 1'%(zone,total))
    frm,to=versions.get(from_id),versions.get(to_id)
    return {'from_version_id':from_id,'to_version_id':to_id,'from_code':frm.code if frm else '?','from_name':frm.name if frm else '?','to_code':to.code if to else '?','to_name':to.name if to else '?','revision':max((r.revision for r in rows),default=0),'rows':[{'from_zone':r.from_zone,'to_zone':r.to_zone,'ratio':r.ratio} for r in rows],'problems':problems}

def list_edges(db):
    versions={v.id:v for v in db.scalars(select(DivisionVersion))}
    grouped={}
    for row in db.scalars(select(DivisionRatio).order_by(DivisionRatio.from_version_id,DivisionRatio.to_version_id,DivisionRatio.from_zone,DivisionRatio.to_zone)):
        grouped.setdefault((row.from_version_id,row.to_version_id),[]).append(row)
    return [_edge_view(db,f,t,rows,versions) for (f,t),rows in sorted(grouped.items())]

def revise_map(db,from_id,to_id,data):
    if from_id==to_id:raise HTTPException(422,'版本不能映射到自身')
    _get_version(db,from_id);_get_version(db,to_id)
    seen=set()
    for row in data.ratios:
        key=(row.from_zone,row.to_zone)
        if key in seen:raise HTTPException(422,'同一对区划的比例重复')
        seen.add(key)
    existing=_edge_rows(db,[(from_id,to_id)],lock=True)
    revision=max((r.revision for r in existing),default=0)+1
    for row in existing:db.delete(row)
    db.flush()
    for row in data.ratios:db.add(DivisionRatio(from_version_id=from_id,to_version_id=to_id,from_zone=row.from_zone,to_zone=row.to_zone,ratio=row.ratio,revision=revision))
    db.flush()
    _sweep_stale(db,(from_id,to_id))
    versions={v.id:v for v in db.scalars(select(DivisionVersion))}
    return _edge_view(db,from_id,to_id,_edge_rows(db,[(from_id,to_id)]),versions)

def _sweep_stale(db,revised_edge):
    """修订或新增映射后：用到该边的草案、以及起止版本间路径集已改变的草案全部失效。"""
    edges=_edge_maps(db);names=_version_names(db)
    drafts=list(db.scalars(select(ConversionDraft).where(ConversionDraft.status==DraftStatus.DRAFT)))
    for draft in drafts:
        stored={tuple(e) for e in draft.payload.get('used_edges',[])}
        if revised_edge in stored:draft.status=DraftStatus.STALE;continue
        try:current={tuple(e) for e in convert_populations(edges,draft.from_version_id,draft.to_version_id,draft.payload.get('source',{}),names)['used_edges']}
        except ConversionError:draft.status=DraftStatus.STALE;continue
        if current!=stored:draft.status=DraftStatus.STALE

def _draft_view(db,draft,versions=None):
    versions=versions or {v.id:v for v in db.scalars(select(DivisionVersion))}
    data=serialize(draft)
    frm,to=versions.get(draft.from_version_id),versions.get(draft.to_version_id)
    data['from_label']=frm.name if frm else '?';data['to_label']=to.name if to else '?'
    return data

def list_drafts(db,batch_id):
    get_batch(db,batch_id)
    versions={v.id:v for v in db.scalars(select(DivisionVersion))}
    return [_draft_view(db,d,versions) for d in db.scalars(select(ConversionDraft).where(ConversionDraft.batch_id==batch_id).order_by(ConversionDraft.id.desc()))]

def create_draft(db,batch_id,data,user):
    get_batch(db,batch_id)
    if data.from_version_id==data.to_version_id:raise HTTPException(422,'起止版本不能相同')
    _get_version(db,data.from_version_id);_get_version(db,data.to_version_id)
    zone_targets=list(db.scalars(select(MarginTarget).where(and_(MarginTarget.batch_id==batch_id,MarginTarget.dimension==Dimension.ZONE)).order_by(MarginTarget.category)))
    if not zone_targets:raise HTTPException(422,'该批次还没有分区目标，请先在目标边际页登记旧区口径')
    populations={t.category:t.population for t in zone_targets}
    try:result=convert_populations(_edge_maps(db),data.from_version_id,data.to_version_id,populations,_version_names(db))
    except ConversionError as e:raise HTTPException(422,detail={'message':str(e),'reason':e.reason,'involved':e.involved})
    fingerprint=_fingerprint(_edge_rows(db,[tuple(e) for e in result['used_edges']]))
    draft=ConversionDraft(batch_id=batch_id,from_version_id=data.from_version_id,to_version_id=data.to_version_id,status=DraftStatus.DRAFT,fingerprint=fingerprint,payload={**result,'source':populations},created_by=user.id)
    db.add(draft);db.flush();return draft

def publish_draft(db,draft_id):
    draft=db.get(ConversionDraft,draft_id)
    if not draft:raise HTTPException(404,'换算草案不存在')
    edge_pairs=[tuple(e) for e in draft.payload.get('used_edges',[])]
    rows=_edge_rows(db,edge_pairs,lock=True)
    draft=db.get(ConversionDraft,draft_id,populate_existing=True,with_for_update=True)
    if draft.status!=DraftStatus.DRAFT:raise HTTPException(409,'草案已失效或已发布，请重新生成换算草案')
    if _fingerprint(rows)!=draft.fingerprint:
        draft.status=DraftStatus.STALE;db.flush()
        raise HTTPException(409,'换算比例已修订，该草案不再有效，请重新生成')
    others=list(db.scalars(select(MarginTarget).where(and_(MarginTarget.batch_id==draft.batch_id,MarginTarget.dimension!=Dimension.ZONE))))
    targets=[{'dimension':Dimension.ZONE,'category':zone,'population':population} for zone,population in sorted(draft.payload['converted'].items())]
    targets+=[{'dimension':t.dimension,'category':t.category,'population':t.population} for t in others]
    try:validate_targets(list_units(db,draft.batch_id),targets)
    except ValueError as e:raise HTTPException(422,'换算结果与现样本对不上：'+str(e))
    db.execute(delete(MarginTarget).where(MarginTarget.batch_id==draft.batch_id))
    for t in targets:db.add(MarginTarget(batch_id=draft.batch_id,**t))
    draft.status=DraftStatus.PUBLISHED;draft.published_at=datetime.utcnow()
    siblings=db.scalars(select(ConversionDraft).where(and_(ConversionDraft.batch_id==draft.batch_id,ConversionDraft.status==DraftStatus.DRAFT,ConversionDraft.id!=draft.id)))
    for sibling in siblings:sibling.status=DraftStatus.STALE
    return draft
