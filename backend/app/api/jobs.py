from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.core.database import get_session
from app.models.schemas import ProcessingJob, ImageryProduct
from app.services.storage_service import storage_service

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


@router.get("/{job_id}")
def get_job_status(job_id: str, session: Session = Depends(get_session)):
    """Kiểm tra tiến độ tác vụ xử lý ảnh nền (Polling endpoint cho Frontend)."""
    job = session.exec(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy mã tác vụ")

    response = {
        "job_id": job.job_id,
        "product_id": job.product_id,
        "acquisition_date": job.acquisition_date,
        "product_type": job.product_type,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }

    # Nếu job đã hoàn tất, cung cấp URL tile và metadata ngày thực tế để frontend vẽ lên bản đồ ngay
    if job.status == "completed":
        product = session.exec(select(ImageryProduct).where(ImageryProduct.id == job.product_id)).first()
        if product:
            s3_uri = storage_service.get_s3_uri(product.r2_object_key)
            presigned_url = storage_service.get_public_or_presigned_url(product.r2_object_key)
            extra = "&rescale=-0.1,0.8&colormap_name=rdylgn" if product.product_type == "ndvi" else ""
            response["tile_url_template"] = f"/titiler/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?url={s3_uri}{extra}"
            response["presigned_cog_url"] = presigned_url
            response["bounds"] = product.bounds
            response["cloud_cover"] = product.cloud_cover
            response["actual_date"] = product.acquisition_date

            # Thông tin khớp ngày: so sánh ngày yêu cầu (acquisition_date của job) với ngày thực tế của product
            requested_date = job.acquisition_date
            actual_date = product.acquisition_date
            if requested_date and actual_date and requested_date != actual_date:
                import datetime
                try:
                    req_d = datetime.date.fromisoformat(requested_date)
                    act_d = datetime.date.fromisoformat(actual_date)
                    diff = abs((act_d - req_d).days)
                    direction = "trước" if act_d < req_d else "sau"
                    response["date_match_status"] = "nearest"
                    response["date_diff_days"] = diff
                    response["requested_date"] = requested_date
                    response["date_info_message"] = (
                        f"Không có ảnh ngày {requested_date}. "
                        f"Hiển thị ngày gần nhất: {actual_date} ({diff} ngày {direction})"
                    )
                except ValueError:
                    response["date_match_status"] = "nearest"
            else:
                response["date_match_status"] = "exact"
                response["date_diff_days"] = 0
                response["requested_date"] = requested_date
                response["date_info_message"] = None

    return response
