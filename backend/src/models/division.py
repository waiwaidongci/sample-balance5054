from datetime import datetime
from sqlalchemy import String,Float,Boolean,Integer,ForeignKey,UniqueConstraint,JSON,DateTime
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class DivisionVersion(Base):
    __tablename__='division_versions'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(30),unique=True)
    name:Mapped[str]=mapped_column(String(60))
    is_current:Mapped[bool]=mapped_column(Boolean,default=False)
class DivisionRatio(Base):
    __tablename__='division_ratios'
    __table_args__=(UniqueConstraint('from_version_id','to_version_id','from_zone','to_zone',name='uq_ratio'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    from_version_id:Mapped[int]=mapped_column(ForeignKey('division_versions.id'))
    to_version_id:Mapped[int]=mapped_column(ForeignKey('division_versions.id'))
    from_zone:Mapped[str]=mapped_column(String(30))
    to_zone:Mapped[str]=mapped_column(String(30))
    ratio:Mapped[float]=mapped_column(Float)
    revision:Mapped[int]=mapped_column(Integer,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class ConversionDraft(Base):
    __tablename__='conversion_drafts'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('sample_batches.id'))
    from_version_id:Mapped[int]=mapped_column(ForeignKey('division_versions.id'))
    to_version_id:Mapped[int]=mapped_column(ForeignKey('division_versions.id'))
    status:Mapped[str]=mapped_column(String(20),default='draft')
    fingerprint:Mapped[str]=mapped_column(String(64))
    payload:Mapped[dict]=mapped_column(JSON,default=dict)
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    published_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
