import uuid
import datetime
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlmodel import Session, select
from app.core.database import get_session
from app.core.config import settings
from app.models.schemas import ImageryProduct, ProcessingJob
from app.services.stac_service import stac_service
from app.services.storage_service import storage_service
from app.tasks.worker import process_imagery_pipeline

router = APIRouter(prefix="/imagery", tags=["Satellite Imagery"])


class PrepareRequest(BaseModel):
    date: str  # YYYY-MM-DD
    product_type: str = "rgb"  # "rgb" hoặc "ndvi"
    force_reprocess: bool = False
    max_cloud: Optional[float] = None
    search_window_days: int = 5  # Số ngày mở rộng tìm kiếm mỗi hướng khi không có ảnh đúng ngày


@router.get("/boundary")
def get_hanoi_boundary():
    """Cung cấp GeoJSON ranh giới hành chính Hà Nội cho lớp Vector của OpenLayers."""
    if not settings.HANOI_BOUNDARY_PATH:
        raise HTTPException(status_code=404, detail="Chưa cấu hình file ranh giới")
    try:
        with open(settings.HANOI_BOUNDARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc ranh giới: {str(e)}")


@router.get("/dates")
def get_available_dates(
    year: int = Query(default=datetime.datetime.now(datetime.timezone.utc).year),
    month: int = Query(default=datetime.datetime.now(datetime.timezone.utc).month),
    max_cloud: float = Query(default=50.0),
    session: Session = Depends(get_session),
):
    """
    Lấy danh sách các ngày trong tháng có ảnh vệ tinh Sentinel-2.
    Đồng thời đối chiếu với database để gắn cờ 'is_cached' (Cache HIT hay MISS).
    Trả thêm 'within_cloud_limit' để UI biết ngày nào thỏa mây người dùng yêu cầu.
    """
    # 1. Tìm trên Microsoft Planetary Computer STAC (trả tất cả ngày có ảnh bất kể mây)
    stac_dates = stac_service.get_available_dates_in_month(year, month, max_cloud=100.0)

    # 2. Lấy danh sách đã cache từ database
    db_products = session.exec(
        select(ImageryProduct).where(
            ImageryProduct.acquisition_date.like(f"{year:04d}-{month:02d}%")
        )
    ).all()
    cached_dates_map = {p.acquisition_date: p for p in db_products}

    results = []
    seen_dates = set()

    for item in stac_dates:
        d = item["date"]
        seen_dates.add(d)
        item_cloud = item["cloud_cover"]
        is_cached = d in cached_dates_map
        within_cloud_limit = item_cloud <= max_cloud

        # Lấy thông tin product_type đã cache nếu có
        cached_products_for_date = [
            {"product_id": p.id, "product_type": p.product_type}
            for p in db_products if p.acquisition_date == d
        ]

        results.append({
            "date": d,
            "cloud_cover": item_cloud,
            "within_cloud_limit": within_cloud_limit,
            "is_cached": is_cached,
            "product_id": cached_dates_map[d].id if is_cached else None,
            "cached_products": cached_products_for_date,
        })

    # Bổ sung các ngày có trong DB mà STAC có thể bỏ lỡ do filter
    for d, prod in cached_dates_map.items():
        if d not in seen_dates:
            results.append({
                "date": d,
                "cloud_cover": prod.cloud_cover,
                "within_cloud_limit": prod.cloud_cover <= max_cloud,
                "is_cached": True,
                "product_id": prod.id,
                "cached_products": [{"product_id": prod.id, "product_type": prod.product_type}],
            })

    results.sort(key=lambda x: x["date"], reverse=True)
    return {
        "year": year,
        "month": month,
        "max_cloud_filter": max_cloud,
        "total": len(results),
        "dates": results,
    }


@router.get("/search")
def search_scenes(
    date: str = Query(..., description="Ngày chụp YYYY-MM-DD"),
    max_cloud: float = Query(default=60.0),
    search_window_days: int = Query(default=5, description="Số ngày tìm kiếm mở rộng mỗi hướng"),
):
    """Tìm kiếm chi tiết các cảnh ảnh Sentinel-2 quanh ngày được chọn từ STAC."""
    scenes = stac_service.search_scenes_by_date(date, max_cloud=max_cloud, search_window_days=search_window_days)
    return {
        "requested_date": date,
        "max_cloud": max_cloud,
        "search_window_days": search_window_days,
        "total_scenes": len(scenes),
        "scenes": scenes,
    }


@router.post("/prepare")
def prepare_imagery(
    payload: PrepareRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    ENDPOINT CỐT LÕI (Cache HIT / MISS):
    - Kiểm tra nếu ảnh đã có trong Cloudflare R2 -> Trả về kết quả ngay (Cache HIT).
    - Nếu chưa có -> Tạo tác vụ nền (Job) để tải cắt và lưu COG (Cache MISS).

    Lưu ý:
    - date_match_status: "exact" hoặc "nearest" (ngày thực tế có thể khác ngày yêu cầu do Sentinel-2 ~5 ngày/chu kỳ)
    - date_info_message: Thông báo chi tiết cho người dùng về ngày ảnh
    """
    max_cloud = payload.max_cloud if payload.max_cloud is not None else settings.MAX_CLOUD_COVER
    product_id = f"s2_{payload.date.replace('-', '')}_hanoi_{payload.product_type}"

    # 1. Kiểm tra trong Database & Cloudflare R2 (Cache HIT cho đúng ngày)
    if not payload.force_reprocess:
        existing_product = session.exec(
            select(ImageryProduct).where(ImageryProduct.id == product_id)
        ).first()

        # Kiểm tra xem ảnh đã có đầy đủ toàn vẹn không (tránh cache ảnh cũ bị cắt thiếu phía Nam)
        is_legacy_cut = False
        if existing_product and existing_product.bounds and len(existing_product.bounds) == 4:
            if existing_product.bounds[1] > 20.65:  # Vĩ độ Nam Hà Nội phải tới ~20.55
                is_legacy_cut = True

        if existing_product and not is_legacy_cut:
            # Xác nhận file vật lý còn trên R2
            try:
                if storage_service.object_exists(existing_product.r2_object_key):
                    s3_uri = storage_service.get_s3_uri(existing_product.r2_object_key)
                    presigned_url = storage_service.get_public_or_presigned_url(existing_product.r2_object_key)
                    return {
                        "status": "ready",
                        "cache_status": "HIT",
                        "product_id": existing_product.id,
                        "requested_date": payload.date,
                        "actual_date": existing_product.acquisition_date,
                        "date_match_status": "exact",   # Cache HIT luôn là exact vì key đã encode ngày
                        "date_diff_days": 0,
                        "date_info_message": None,
                        "cloud_warning": None,
                        "product_type": existing_product.product_type,
                        "cloud_cover": existing_product.cloud_cover,
                        "bounds": existing_product.bounds,
                        "tile_url_template": f"/titiler/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?url={s3_uri}" + ("&rescale=-0.1,0.8&colormap_name=rdylgn" if existing_product.product_type == "ndvi" else ""),
                        "presigned_cog_url": presigned_url,
                        "file_size_bytes": existing_product.file_size_bytes,
                    }
            except Exception:
                pass  # Nếu lỗi kết nối R2 thì tiếp tục tạo job xử lý lại

    # 2. Pre-search STAC để biết trước ngày thực tế (giúp UI hiển thị thông báo sớm)
    #    và kiểm tra xem ngày thực tế đã được cache chưa
    pre_search_info = None
    actual_product_id_pre = None
    try:
        scenes_preview = stac_service.search_scenes_by_date(
            payload.date, max_cloud=max_cloud,
            search_window_days=payload.search_window_days
        )
        if scenes_preview:
            best = scenes_preview[0]
            pre_search_info = {
                "actual_date": best.get("date"),
                "date_match_status": best.get("date_match_status", "exact"),
                "date_diff_days": best.get("date_diff_days", 0),
                "date_info_message": best.get("date_info_message"),
                "cloud_warning": best.get("cloud_warning"),
                "cloud_cover": best.get("cloud_cover"),
            }
            actual_date_pre = best.get("date") or payload.date
            actual_product_id_pre = f"s2_{actual_date_pre.replace('-', '')}_hanoi_{payload.product_type}"

            # Kiểm tra xem ngày thực tế (nearest) đã có cache chưa
            if not payload.force_reprocess and actual_product_id_pre and actual_product_id_pre != product_id:
                existing_actual = session.exec(
                    select(ImageryProduct).where(ImageryProduct.id == actual_product_id_pre)
                ).first()
                if existing_actual:
                    is_incomplete_act = False
                    if existing_actual.bounds and len(existing_actual.bounds) == 4:
                        if existing_actual.bounds[1] > 20.65:
                            is_incomplete_act = True
                    if not is_incomplete_act:
                        try:
                            if storage_service.object_exists(existing_actual.r2_object_key):
                                s3_uri = storage_service.get_s3_uri(existing_actual.r2_object_key)
                                presigned_url = storage_service.get_public_or_presigned_url(existing_actual.r2_object_key)
                                return {
                                    "status": "ready",
                                    "cache_status": "HIT",
                                    "product_id": existing_actual.id,
                                    "requested_date": payload.date,
                                    "actual_date": existing_actual.acquisition_date,
                                    "date_match_status": pre_search_info["date_match_status"],
                                    "date_diff_days": pre_search_info["date_diff_days"],
                                    "date_info_message": pre_search_info["date_info_message"],
                                    "cloud_warning": pre_search_info["cloud_warning"],
                                    "product_type": existing_actual.product_type,
                                    "cloud_cover": existing_actual.cloud_cover,
                                    "bounds": existing_actual.bounds,
                                    "tile_url_template": f"/titiler/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?url={s3_uri}" + ("&rescale=-0.1,0.8&colormap_name=rdylgn" if existing_actual.product_type == "ndvi" else ""),
                                    "presigned_cog_url": presigned_url,
                                    "file_size_bytes": existing_actual.file_size_bytes,
                                }
                        except Exception:
                            pass
    except Exception as pre_err:
        print(f"Pre-search STAC lỗi (không nghiêm trọng): {pre_err}")

    # 3. Kiểm tra xem có Job nào đang chạy cho ngày này không (Chống duplicate job)
    if not payload.force_reprocess:
        existing_job = session.exec(
            select(ProcessingJob).where(
                ProcessingJob.product_id == product_id,
                ProcessingJob.status.in_(["queued", "processing"]),
            )
        ).first()

        if existing_job:
            job_updated = existing_job.updated_at or existing_job.created_at
            if job_updated.tzinfo is None:
                job_updated = job_updated.replace(tzinfo=datetime.timezone.utc)
            diff_sec = (datetime.datetime.now(datetime.timezone.utc) - job_updated).total_seconds()
            if diff_sec < 180:  # Đang chạy bình thường trong vòng 3 phút
                return {
                    "status": "processing",
                    "cache_status": "MISS",
                    "job_id": existing_job.job_id,
                    "product_id": product_id,
                    "requested_date": payload.date,
                    "progress": existing_job.progress,
                    "message": existing_job.message,
                    **(pre_search_info or {}),
                }
            else:
                existing_job.status = "failed"
                existing_job.error = "Tác vụ trước đó bị timeout, đang khởi động lại..."
                session.add(existing_job)
                session.commit()

    # 4. Tạo Job mới và kích hoạt tác vụ nền
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    new_job = ProcessingJob(
        job_id=job_id,
        product_id=product_id,
        acquisition_date=payload.date,
        product_type=payload.product_type,
        status="queued",
        progress=5,
        message="Đã tiếp nhận yêu cầu, đang khởi tạo pipeline...",
    )
    session.add(new_job)
    session.commit()

    import threading
    thread = threading.Thread(
        target=process_imagery_pipeline,
        args=(job_id, payload.date, payload.product_type, max_cloud, payload.force_reprocess),
        daemon=True,
        name=f"worker-{job_id}",
    )
    thread.start()

    response = {
        "status": "processing",
        "cache_status": "MISS",
        "job_id": job_id,
        "product_id": product_id,
        "requested_date": payload.date,
        "progress": 5,
        "message": "Đang bắt đầu xử lý ảnh trên đám mây...",
    }

    # Đính kèm pre-search info nếu có (giúp UI hiển thị ngày dự kiến ngay từ đầu)
    if pre_search_info:
        response.update(pre_search_info)

    return response


@router.get("/r2-catalog")
def list_r2_catalog(
    product_type: Optional[str] = Query(default=None, description="Lọc theo loại: rgb, ndvi"),
    session: Session = Depends(get_session),
):
    """
    Danh sách toàn bộ ảnh COG đã lưu trữ trên Cloudflare R2 của hệ thống.
    Mỗi item bao gồm tile URL template để load trực tiếp lên bản đồ không cần xử lý lại.
    """
    query = select(ImageryProduct).order_by(ImageryProduct.acquisition_date.desc())
    if product_type:
        query = select(ImageryProduct).where(
            ImageryProduct.product_type == product_type
        ).order_by(ImageryProduct.acquisition_date.desc())

    products = session.exec(query).all()

    items = []
    for p in products:
        try:
            s3_uri = storage_service.get_s3_uri(p.r2_object_key)
            presigned_url = storage_service.get_public_or_presigned_url(p.r2_object_key)
            extra = "&rescale=-0.1,0.8&colormap_name=rdylgn" if p.product_type == "ndvi" else ""
            tile_url = f"/titiler/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?url={s3_uri}{extra}"

            items.append({
                "product_id": p.id,
                "acquisition_date": p.acquisition_date,
                "product_type": p.product_type,
                "cloud_cover": p.cloud_cover,
                "collection": p.collection,
                "source_scenes": p.source_scenes,
                "bounds": p.bounds,
                "file_size_bytes": p.file_size_bytes,
                "file_size_mb": round(p.file_size_bytes / (1024 * 1024), 1) if p.file_size_bytes else None,
                "tile_url_template": tile_url,
                "presigned_cog_url": presigned_url,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })
        except Exception as e:
            # Nếu không lấy được URL (lỗi R2) vẫn trả metadata
            items.append({
                "product_id": p.id,
                "acquisition_date": p.acquisition_date,
                "product_type": p.product_type,
                "cloud_cover": p.cloud_cover,
                "collection": p.collection,
                "bounds": p.bounds,
                "file_size_bytes": p.file_size_bytes,
                "file_size_mb": round(p.file_size_bytes / (1024 * 1024), 1) if p.file_size_bytes else None,
                "tile_url_template": None,
                "presigned_cog_url": None,
                "error": str(e),
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })

    return {
        "total": len(items),
        "product_type_filter": product_type,
        "items": items,
    }


@router.get("/products")
def list_products(session: Session = Depends(get_session)):
    """Danh sách tất cả các sản phẩm ảnh vệ tinh Hà Nội đã được lưu trữ trong R2."""
    products = session.exec(select(ImageryProduct).order_by(ImageryProduct.acquisition_date.desc())).all()
    return {
        "total": len(products),
        "products": products,
    }


@router.get("/{product_id}/download-url")
def get_download_url(product_id: str, session: Session = Depends(get_session)):
    """Lấy link tải trực tiếp file COG (GeoTIFF) về máy tính."""
    product = session.exec(select(ImageryProduct).where(ImageryProduct.id == product_id)).first()
    if not product:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm ảnh")

    download_url = storage_service.get_presigned_url(product.r2_object_key, expires_in=7200)
    return {
        "product_id": product.id,
        "filename": f"{product.id}.tif",
        "download_url": download_url,
        "file_size_bytes": product.file_size_bytes,
    }
