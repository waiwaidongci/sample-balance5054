from pydantic import BaseModel,Field
class VersionInput(BaseModel):
    code:str=Field(min_length=2,max_length=30,pattern=r'^[a-z0-9-]+$')
    name:str=Field(min_length=2,max_length=60)
    is_current:bool=False
class RatioRowInput(BaseModel):
    from_zone:str=Field(min_length=1,max_length=30)
    to_zone:str=Field(min_length=1,max_length=30)
    ratio:float=Field(gt=0,le=1,allow_inf_nan=False)
class RatioMapInput(BaseModel):
    ratios:list[RatioRowInput]=Field(min_length=1,max_length=200)
class DraftInput(BaseModel):
    from_version_id:int=Field(ge=1)
    to_version_id:int=Field(ge=1)
