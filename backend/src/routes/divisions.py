from fastapi import APIRouter,Depends
from src.config.database import session
from src.middlewares.auth import current_user,require
from src.schemas.division import VersionInput,RatioMapInput,DraftInput
from src.services import division_service
from src.controllers import division_controller
router=APIRouter(tags=['divisions'])
@router.get('/division-versions')
def versions(db=Depends(session),user=Depends(current_user)):return division_service.list_versions(db)
@router.post('/division-versions',status_code=201)
def creating(data:VersionInput,db=Depends(session),user=Depends(require('admin'))):return division_controller.create_version(db,data,user)
@router.get('/division-ratios')
def ratios(db=Depends(session),user=Depends(current_user)):return division_service.list_edges(db)
@router.put('/division-ratios/{from_version_id}/{to_version_id}')
def revising(from_version_id:int,to_version_id:int,data:RatioMapInput,db=Depends(session),user=Depends(require('admin'))):return division_controller.revise(db,from_version_id,to_version_id,data,user)
@router.get('/batches/{batch_id}/conversion-drafts')
def drafts(batch_id:int,db=Depends(session),user=Depends(current_user)):return division_service.list_drafts(db,batch_id)
@router.post('/batches/{batch_id}/conversion-drafts',status_code=201)
def creating_draft(batch_id:int,data:DraftInput,db=Depends(session),user=Depends(require('admin'))):return division_controller.create_draft(db,batch_id,data,user)
@router.post('/conversion-drafts/{draft_id}/publish')
def publishing(draft_id:int,db=Depends(session),user=Depends(require('admin'))):return division_controller.publish(db,draft_id,user)
