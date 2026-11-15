from fastapi import HTTPException
from src.services import division_service
from src.services.target_service import list_targets
from src.utils.audit import record
from src.utils.serializers import serialize

def create_version(db,data,user):
    row=division_service.create_version(db,data);record(db,user,'create_division_version',row.code);db.commit();return serialize(row)

def revise(db,from_id,to_id,data,user):
    edge=division_service.revise_map(db,from_id,to_id,data);record(db,user,'revise_division_ratio','%s->%s#%s'%(edge['from_code'],edge['to_code'],edge['revision']));db.commit();return edge

def create_draft(db,batch_id,data,user):
    draft=division_service.create_draft(db,batch_id,data,user);record(db,user,'create_conversion_draft','%s:%s'%(batch_id,draft.id));db.commit();return division_service._draft_view(db,draft)

def publish(db,draft_id,user):
    try:draft=division_service.publish_draft(db,draft_id)
    except HTTPException as e:
        if e.status_code==409:db.commit()
        raise
    record(db,user,'publish_conversion_draft','%s->batch %s'%(draft_id,draft.batch_id));db.commit()
    return {'draft':division_service._draft_view(db,draft),'targets':list_targets(db,draft.batch_id)}
