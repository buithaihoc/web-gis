import os
import time
import datetime
import traceback
from sqlmodel import Session, select
from app.core.database import engine
from app.models.schemas import ImageryProduct, ProcessingJob
from app.services.stac_service import stac_service
from app.services.raster_service import raster_service
from app.services.storage_service import storage_service


def update_job_status(job_id: str, status: str, progress: int, message: str, error: str = None):
    """Cập nhật tiến độ Job với cơ chế retry chống khóa file SQLite (Database lock)."""
    for attempt in range(5):
        try:
            with Session(engine) as session:
                job = session.exec(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).first()
                if job:
                    job.status = status
                    job.progress = progress
                    job.message = message
                    job.error = error
                    job.updated_at = datetime.datetime.now(datetime.timezone.utc)
                    session.add(job)
                    session.commit()
            break
        except Exception as ex:
            time.sleep(0.15 * (attempt + 1))
            if attempt == 4:
                print(f"Cảnh báo: Không thể cập nhật trạng thái job {job_id}: {ex}")


def process_imagery_pipeline(job_id: str, date_str: str, product_type: str = "rgb", max_cloud: float = None, force_reprocess: bool = False):
    """
    Quy trình xử lý tác vụ nền chuẩn viễn thám:
    1. Tra cứu Microsoft Planetary Computer STAC (0% -> 25%)
    2. Cắt theo ranh giới Hà Nội & Ghép Mosaic 2 mảnh Bắc - Nam (25% -> 80%)
    3. Đẩy lên Cloudflare R2 với Byte-level progress (80% -> 95%)
    4. Cập nhật Database Metadata & Spatial index (95% -> 100%)
    """
    try:
        # Bước 1: Tra cứu STAC
        update_job_status(job_id, "processing", 10, f"Đang tìm ảnh Sentinel-2 ngày {date_str} trên Microsoft MPC...")
        scenes = stac_service.search_scenes_by_date(date_str, max_cloud=max_cloud)

        if not scenes:
            update_job_status(job_id, "failed", 0, f"Không tìm thấy cảnh ảnh Sentinel-2 phù hợp quanh ngày {date_str}", "No scenes found")
            return

        best_scene = scenes[0]  # Cảnh tối ưu nhất (đã sắp xếp theo smart_sort_key)
        cloud_cover = best_scene.get("cloud_cover", 0.0)
        source_id = best_scene.get("item_id", "")
        actual_date = best_scene.get("date") or date_str
        actual_product_id = f"s2_{actual_date.replace('-', '')}_hanoi_{product_type}"
        date_match_status = best_scene.get("date_match_status", "exact")
        date_diff_days = best_scene.get("date_diff_days", 0)
        date_info_message = best_scene.get("date_info_message", "")
        cloud_warning = best_scene.get("cloud_warning")

        # Kiểm tra xem sản phẩm của ngày thực tế này đã có sẵn trên Cloudflare R2 hay chưa
        if not force_reprocess:
            with Session(engine) as session:
                existing_prod = session.exec(select(ImageryProduct).where(ImageryProduct.id == actual_product_id)).first()
                if existing_prod and storage_service.object_exists(existing_prod.r2_object_key):
                    # Kiểm tra xem ảnh cũ có bị thiếu mảnh phía Nam (Ứng Hòa, Mỹ Đức, Phú Xuyên) không
                    is_incomplete = False
                    if best_scene.get("has_southern_tile"):
                        if len(existing_prod.source_scenes or []) < 2 or (existing_prod.bounds and len(existing_prod.bounds) == 4 and existing_prod.bounds[1] > 20.65):
                            is_incomplete = True

                    if not is_incomplete:
                        job = session.exec(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).first()
                        if job:
                            job.product_id = actual_product_id
                            job.status = "completed"
                            job.progress = 100
                            job.message = f"Đã nạp ảnh Sentinel-2 ngày {actual_date} từ kho lưu trữ Cloudflare R2!"
                            session.add(job)
                            session.commit()
                        return

        if date_match_status == "nearest":
            update_job_status(
                job_id, "processing", 20,
                f"⚠ Ngày {date_str} không có lượt bay. Tìm thấy ảnh gần nhất: {actual_date} (chênh {date_diff_days} ngày, mây {cloud_cover:.1f}%)..."
            )
        else:
            update_job_status(job_id, "processing", 25, f"Đã xác định quỹ đạo vệ tinh ngày {actual_date} (Độ che phủ mây: {cloud_cover:.1f}%). Bắt đầu chuẩn bị dữ liệu...")

        # Bước 2: Xử lý raster & tạo COG
        filename = f"hanoi_{product_type}_{actual_date.replace('-', '')}.tif"
        r2_key = f"imagery/sentinel-2-l2a/{actual_date.replace('-', '/')}/{filename}"

        has_south = best_scene.get("has_southern_tile", False)
        source_scenes = best_scene.get("source_scenes") or [source_id]

        def on_raster_progress(pct: int, msg: str):
            update_job_status(job_id, "processing", pct, msg)

        if product_type == "rgb":
            visual_urls = best_scene.get("visual_hrefs") or ([best_scene.get("visual_href")] if best_scene.get("visual_href") else [])
            if not visual_urls:
                raise ValueError("Không tìm thấy asset 'visual' cho ảnh True Color")

            msg = f"Đang kết nối luồng dữ liệu 10m {'ghép 2 mảnh Bắc - Nam' if has_south else 'đơn mảnh'} ngày {actual_date}..."
            update_job_status(job_id, "processing", 30, msg)
            cog_path, file_size, bounds = raster_service.process_rgb_cog(visual_urls, filename, progress_callback=on_raster_progress)

        elif product_type == "ndvi":
            b08_urls = best_scene.get("b08_hrefs") or ([best_scene.get("b08_href")] if best_scene.get("b08_href") else [])
            b04_urls = best_scene.get("b04_hrefs") or ([best_scene.get("b04_href")] if best_scene.get("b04_href") else [])
            if not b08_urls or not b04_urls:
                raise ValueError("Thiếu band B08 hoặc B04 để tính NDVI")

            msg = f"Đang kết nối luồng dải phổ hồng ngoại (B08) và đỏ (B04) ngày {actual_date}..."
            update_job_status(job_id, "processing", 30, msg)
            cog_path, file_size, bounds = raster_service.process_ndvi_cog(b08_urls, b04_urls, filename, progress_callback=on_raster_progress)
        else:
            raise ValueError(f"Loại sản phẩm không hỗ trợ: {product_type}")

        # Bước 3: Upload lên Cloudflare R2 với Byte-level progress
        mb_total = file_size / (1024 * 1024)
        update_job_status(job_id, "processing", 82, f"Đang truyền tải ảnh COG lên Cloudflare R2 ({mb_total:.1f} MB)...")

        uploaded_bytes = 0
        last_reported_pct = 82

        def upload_callback(chunk_bytes):
            nonlocal uploaded_bytes, last_reported_pct
            uploaded_bytes += chunk_bytes
            pct = 82 + int((uploaded_bytes / max(file_size, 1)) * 14)  # 82% -> 96%
            if pct > last_reported_pct and (pct - last_reported_pct >= 2 or pct >= 96):
                last_reported_pct = pct
                mb_done = uploaded_bytes / (1024 * 1024)
                update_job_status(job_id, "processing", pct, f"Đang tải lên Cloudflare R2 ({mb_done:.1f}/{mb_total:.1f} MB)...")

        storage_service.upload_cog(cog_path, r2_key, progress_callback=upload_callback)

        # Xóa file COG tạm ở ổ đĩa sau khi đã lên R2
        if os.path.exists(cog_path):
            os.remove(cog_path)

        # Bước 4: Lưu vào cơ sở dữ liệu
        update_job_status(job_id, "processing", 98, "Đang đồng bộ cơ sở dữ liệu và chỉ mục không gian...")
        product_id = actual_product_id

        with Session(engine) as session:
            existing = session.exec(select(ImageryProduct).where(ImageryProduct.id == product_id)).first()
            if existing:
                session.delete(existing)
                session.commit()

            product = ImageryProduct(
                id=product_id,
                acquisition_date=actual_date,
                collection="sentinel-2-l2a",
                product_type=product_type,
                cloud_cover=cloud_cover,
                source_scenes=source_scenes,
                r2_object_key=r2_key,
                bounds=bounds,
                file_size_bytes=file_size,
            )
            session.add(product)

            # Cập nhật Job trỏ đúng vào product_id thực tế
            job = session.exec(select(ProcessingJob).where(ProcessingJob.job_id == job_id)).first()
            if job:
                job.product_id = product_id
                job.status = "completed"
                job.progress = 100
                # Thông báo thành công kèm thông tin ngày thực tế
                if date_match_status == "nearest":
                    job.message = f"⚠ Hiển thị ảnh ngày {actual_date} (gần nhất, chênh {date_diff_days} ngày so với {date_str})"
                else:
                    job.message = f"✓ Xử lý thành công ảnh đúng ngày {actual_date}!"
                session.add(job)

            session.commit()


    except Exception as e:
        traceback.print_exc()
        print(f"Lỗi pipeline cho job {job_id}: {e}")
        update_job_status(job_id, "failed", 0, f"Lỗi trong quá trình xử lý: {str(e)}", error=str(e))

