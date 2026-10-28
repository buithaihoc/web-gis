import datetime
from typing import Optional, List, Any
from sqlmodel import SQLModel, Field, JSON, Column


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class ImageryProduct(SQLModel, table=True):
    __tablename__ = "imagery_products"

    id: str = Field(primary_key=True)  # ví dụ: "s2_20261009_hanoi_rgb"
    acquisition_date: str = Field(index=True)  # "2026-10-09"
    collection: str = Field(default="sentinel-2-l2a")
    product_type: str = Field(default="rgb", index=True)  # "rgb", "ndvi", "cir"
    cloud_cover: float = Field(default=0.0)
    source_scenes: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    r2_object_key: str = Field(index=True)  # "imagery/sentinel-2-l2a/2026/10/09/hanoi_rgb.tif"
    bounds: List[float] = Field(default_factory=list, sa_column=Column(JSON))  # [min_lon, min_lat, max_lon, max_lat]
    file_size_bytes: Optional[int] = None
    created_at: datetime.datetime = Field(default_factory=utc_now)


class ProcessingJob(SQLModel, table=True):
    __tablename__ = "processing_jobs"

    job_id: str = Field(primary_key=True)
    product_id: str = Field(index=True)
    acquisition_date: str = Field(index=True)
    product_type: str = Field(default="rgb")
    status: str = Field(default="queued", index=True)  # queued, processing, completed, failed
    progress: int = Field(default=0)  # 0 to 100
    message: str = Field(default="Đang xếp hàng...")
    error: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=utc_now)
    updated_at: datetime.datetime = Field(default_factory=utc_now)
