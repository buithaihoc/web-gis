# KẾ HOẠCH TRIỂN KHAI CHI TIẾT (IMPLEMENTATION PLAN)
## DỰ ÁN WEBGIS ẢNH VỆ TINH HÀ NỘI
*(Microsoft Planetary Computer + Cloudflare R2 + TiTiler + FastAPI + OpenLayers)*

---

## 1. TỔNG QUAN LỘ TRÌNH (ROADMAP PHASES)

Dự án được chia thành 5 giai đoạn rõ ràng, tuân thủ nguyên tắc kiểm thử từng phần độc lập trước khi tích hợp toàn diện:

```
[Giai đoạn 1] Chuẩn bị môi trường & Thiết kế khung dự án (Architecture & Setup)
     │
     ▼
[Giai đoạn 2] Dịch vụ tìm kiếm STAC & Ranh giới Hà Nội (STAC & Boundaries)
     │
     ▼
[Giai đoạn 3] Pipeline xử lý ảnh COG & Lưu trữ Cloudflare R2 (Raster & Storage)
     │
     ▼
[Giai đoạn 4] Động cơ hiển thị TiTiler & Tác vụ nền Cache HIT/MISS (TiTiler & Jobs)
     │
     ▼
[Giai đoạn 5] Giao diện WebGIS OpenLayers & Hoàn thiện Container Docker (UI & Docker)
```

---

## 2. CHI TIẾT TỪNG GIAI ĐOẠN

### GIAI ĐOẠN 1: Môi trường ảo, Thư viện và Cấu trúc dự án chuẩn
**Mục tiêu**: Thiết lập môi trường Python sạch, cấu hình biến môi trường và khung thư mục có tính module cao, chuẩn bị sẵn sàng cho Docker sau này.

- **Bước 1.1: Tạo cấu trúc thư mục chuẩn**
  ```text
  d:\web-gis\
  ├── backend/
  │   ├── app/
  │   │   ├── __init__.py
  │   │   ├── main.py                  # Điểm khởi chạy FastAPI
  │   │   ├── core/                    # Cấu hình chung, biến môi trường, bảo mật
  │   │   │   ├── __init__.py
  │   │   │   ├── config.py
  │   │   │   └── database.py          # Kết nối SQLite / SQLAlchemy
  │   │   ├── models/                  # Lược đồ dữ liệu (Product, Job)
  │   │   │   ├── __init__.py
  │   │   │   └── schemas.py
  │   │   ├── services/                # Các dịch vụ độc lập (Clean Architecture)
  │   │   │   ├── __init__.py
  │   │   │   ├── stac_service.py      # Tìm kiếm trên Microsoft Planetary Computer
  │   │   │   ├── raster_service.py    # Cắt ảnh, xử lý phổ, tạo COG
  │   │   │   ├── storage_service.py   # Tương tác Cloudflare R2 (boto3)
  │   │   │   └── tiler_service.py     # Tích hợp TiTiler Dynamic Raster
  │   │   ├── tasks/                   # Quản lý tác vụ nền (Background Queue)
  │   │   │   ├── __init__.py
  │   │   │   └── worker.py
  │   │   └── api/                     # Router API
  │   │       ├── __init__.py
  │   │       ├── imagery.py
  │   │       └── jobs.py
  │   ├── requirements.txt
  │   └── Dockerfile                   # Dockerfile cho Backend
  ├── frontend/                        # Giao diện WebGIS
  │   ├── index.html
  │   ├── styles/
  │   │   └── main.css                 # Giao diện hiện đại Dark Glassmorphic
  │   ├── src/
  │   │   ├── config.js
  │   │   ├── map.js                   # Khởi tạo bản đồ OpenLayers
  │   │   ├── layers.js                # Quản lý layer vệ tinh & ranh giới
  │   │   ├── timeline.js              # Lịch & thanh thời gian chọn ảnh
  │   │   ├── jobs.js                  # Theo dõi tiến trình tải/xử lý ảnh
  │   │   └── app.js                   # Điều phối ứng dụng
  │   └── package.json
  ├── data/
  │   ├── boundaries/
  │   │   └── hanoi.geojson            # Polygon ranh giới Hà Nội (WGS84)
  │   └── temp/                        # Thư mục xử lý tạm thời
  ├── docs/
  │   ├── ARCHITECTURE.md
  │   └── IMPLEMENTATION_PLAN.md
  ├── .env.example
  ├── .gitignore
  └── docker-compose.yml
  ```

- **Bước 1.2: Tạo môi trường ảo Python & Cài đặt thư viện**
  - Khởi tạo `.venv` bằng PowerShell:
    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```
  - Cài đặt `requirements.txt`:
    - `fastapi`, `uvicorn[standard]`
    - `pystac-client`, `planetary-computer`
    - `rasterio`, `rioxarray`, `shapely`, `geopandas`
    - `boto3`, `botocore`
    - `titiler.core`, `rio-cogeo`
    - `sqlmodel` hoặc `sqlalchemy`

- **Bước 1.3: Cấu hình file `.env`**
  - Chứa thông tin Cloudflare R2 (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`).
  - Đường dẫn GeoJSON ranh giới Hà Nội.

---

### GIAI ĐOẠN 2: Dịch vụ tìm kiếm STAC (Microsoft Planetary Computer) & Ranh giới Hà Nội
**Mục tiêu**: Xây dựng module tìm kiếm cảnh ảnh Sentinel-2 L2A quanh khu vực Hà Nội theo ngày và lọc tỷ lệ mây.

- **Bước 2.1: Chuẩn hóa file ranh giới `data/boundaries/hanoi.geojson`**
  - Bounding box mở rộng Hà Nội: `[105.25, 20.55, 106.02, 21.45]`.
  - Polygon GeoJSON chi tiết ranh giới thành phố Hà Nội để phục vụ cắt ảnh (clip) chính xác.
- **Bước 2.2: Viết `stac_service.py`**
  - Kết nối tới `https://planetarycomputer.microsoft.com/api/stac/v1` có ký token tự động với `planetary_computer.sign_inplace`.
  - Hàm tìm kiếm ảnh theo khoảng ngày (`start_date` đến `end_date`), bbox Hà Nội, lọc collection `sentinel-2-l2a`.
  - Xếp hạng cảnh theo độ phủ mây `eo:cloud_cover`.
  - API endpoint: `GET /api/imagery/available-dates` (liệt kê danh sách các ngày trong tháng có ảnh vệ tinh đạt tiêu chuẩn mây).

---

### GIAI ĐOẠN 3: Pipeline xử lý Raster & Lưu trữ Cloudflare R2
**Mục tiêu**: Tải các band cần thiết từ MPC qua HTTP Range stream, cắt theo ranh giới Hà Nội, tạo file chuẩn COG và tải lên R2.

- **Bước 3.1: Viết `storage_service.py` (Boto3 Cloudflare R2 Client)**
  - Khởi tạo S3 Client tương thích endpoint Cloudflare R2: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
  - Hàm kiểm tra file tồn tại `object_exists(key)`.
  - Hàm tải file lên `upload_cog(local_path, key)`.
  - Hàm tạo presigned URL có hạn sử dụng (1 giờ).
- **Bước 3.2: Viết `raster_service.py` (Xử lý ảnh viễn thám)**
  - Tận dụng khả năng đọc trực tiếp từ xa (`vsicurl` của GDAL/Rasterio) trên signed URL của MPC mà không cần tải nguyên file JP2 500MB về đĩa.
  - Đọc 3 dải phổ: `B04` (Red), `B03` (Green), `B02` (Blue) ở độ phân giải 10m.
  - Cắt (mask/clip) theo Polygon ranh giới Hà Nội.
  - Chuẩn hóa giá trị phản xạ (Reflectance scaling 0 - 10000 -> 0 - 255 RGB 8-bit) kèm cân bằng độ tương phản (Histogram stretch) giúp ảnh hiển thị đẹp tự nhiên.
  - Xuất ra định dạng **Cloud-Optimized GeoTIFF (COG)** bằng `rio-cogeo` hoặc `rasterio` với cấu hình chuẩn:
    - `TILED=YES`, `BLOCKXSIZE=256`, `BLOCKYSIZE=256`
    - `COMPRESS=DEFLATE` hoặc `WEBP`
    - Overviews đa tầng (2, 4, 8, 16, 32).

---

### GIAI ĐOẠN 4: Động cơ TiTiler & Cơ chế Cache HIT / MISS với Tác vụ nền
**Mục tiêu**: Phục vụ lát gạch bản đồ XYZ từ R2 và đảm bảo trải nghiệm người dùng mượt mà với hàng đợi xử lý nền.

- **Bước 4.1: Tích hợp TiTiler Router trong FastAPI**
  - Mount TiTiler router vào FastAPI app tại `/titiler`.
  - Cấu hình thông tin xác thực AWS/S3 trong môi trường GDAL để TiTiler có thể đọc trực tiếp các COG riêng tư từ R2.
  - Endpoint lấy Tile: `/titiler/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=s3://webgis-hanoi/imagery/.../hanoi_rgb.tif`.
- **Bước 4.2: Xây dựng Bộ điều phối Cache & Job Worker (`worker.py`)**
  - Database SQLite lưu lịch sử sản phẩm (`imagery_products`) và trạng thái tác vụ (`processing_jobs`).
  - Khi người dùng gửi yêu cầu:
    - **Cache HIT**: Trả về ngay URL tile template và metadata, frontend hiển thị tức thì.
    - **Cache MISS**: Tạo `job_id`, đẩy tác vụ xử lý ảnh vào `FastAPI.BackgroundTasks` (hoặc luồng riêng), trả ngay `job_id` cho frontend.
    - Cập nhật tiến độ `progress` (0% -> 25% Đọc ảnh -> 50% Cắt ranh giới -> 75% Tạo COG -> 90% Upload R2 -> 100% Hoàn thành).
  - API endpoint:
    - `POST /api/imagery/prepare` (kèm tham số date, product_type)
    - `GET /api/jobs/{job_id}` (kiểm tra tiến độ)

---

### GIAI ĐOẠN 5: Giao diện WebGIS OpenLayers & Docker hóa
**Mục tiêu**: Xây dựng giao diện WebGIS bản đồ chuyên nghiệp, trực quan và đóng gói toàn bộ dự án vào Docker.

- **Bước 5.1: Giao diện WebGIS OpenLayers (Theo chi tiết tại [docs/USER_REQUIREMENTS.md](file:///d:/web-gis/docs/USER_REQUIREMENTS.md))**
  - Khởi tạo Map OpenLayers với tâm tại Hà Nội `[105.8342, 21.0278]`, zoom mức 10.
  - Lớp ranh giới Hà Nội (VectorLayer GeoJSON viền neon nổi bật).
  - Lớp ảnh vệ tinh `ol/layer/Tile` kết nối tới endpoint TiTiler.
  - Bảng điều khiển:
    - Chọn ngày chụp vệ tinh có hiển thị trạng thái (Đã lưu trong R2 / Chưa xử lý).
    - Thanh trượt độ trong suốt (Opacity 0 - 100%).
    - Thanh trượt lọc mây (Cloud Coverage Slider).
    - Chuyển đổi tổ hợp màu (True Color RGB, NDVI thực vật, False Color CIR).
    - Hộp thông báo trạng thái xử lý thời gian thực (Progress bar, phần trăm, thông điệp).
    - Thước tỷ lệ, tọa độ chuột, nút Fullscreen, nút Reset về toàn cảnh Hà Nội.
    - Nút tải trực tiếp GeoTIFF (COG) về máy tính.
- **Bước 5.2: Docker hóa (Containerization)**
  - `backend/Dockerfile`: Base image Python với GDAL/GEOS/PROJ cài đặt sẵn.
  - `docker-compose.yml`: Chạy đồng bộ Backend FastAPI + TiTiler + Frontend Nginx (hoặc phục vụ tĩnh qua FastAPI) chỉ với 1 lệnh `docker compose up -d`.

---

## 3. CHECKLIST KIỂM THỬ TỪNG BƯỚC

| Giai đoạn | Tiêu chí nghiệm thu (Pass criteria) |
| :--- | :--- |
| **Giai đoạn 1** | Môi trường ảo kích hoạt thành công; các thư viện `fastapi`, `pystac-client`, `rasterio`, `boto3` import không lỗi. |
| **Giai đoạn 2** | Chạy thử `stac_service.py` trả về danh sách các cảnh Sentinel-2 đúng tọa độ Hà Nội và ngày đã chọn. |
| **Giai đoạn 3** | Tạo thành công 1 file COG `hanoi_rgb.tif` đã cắt theo ranh giới, upload lên Cloudflare R2 và kiểm tra HEAD object thành công. |
| **Giai đoạn 4** | TiTiler đọc được file COG từ R2 và xuất ra tile PNG `{z}/{x}/{y}` hợp lệ; Job background cập nhật tiến độ chuẩn xác từ 0 đến 100%. |
| **Giai đoạn 5** | Mở trình duyệt WebGIS, chọn ngày -> nếu đã có thì hiện ngay ảnh; nếu chưa có thì hiện thanh tiến trình, sau khi hoàn thành ảnh hiển thị mượt mà trên bản đồ. |
