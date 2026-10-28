# WebGIS Ảnh Vệ Tinh Hà Nội
### Microsoft Planetary Computer + Cloudflare R2 + TiTiler + FastAPI + OpenLayers

Hệ thống WebGIS viễn thám hiện đại phục vụ tìm kiếm, xử lý theo nhu cầu (On-Demand Processing) và trực quan hóa ảnh vệ tinh Sentinel-2 khu vực thành phố Hà Nội. Dữ liệu sau khi xử lý được lưu trữ dưới chuẩn **Cloud-Optimized GeoTIFF (COG)** trên **Cloudflare R2** và phục vụ dynamic tile qua **TiTiler**.

---

## 📑 Tài liệu chi tiết dự án

- 📐 **[Kiến trúc hệ thống chuẩn v2.0 (Architecture v2)](docs/ARCHITECTURE_V2.md)**: Tổng hợp kiến trúc mới nhất, sơ đồ 4 tầng, Docker topology, luồng Cache HIT/MISS, xử lý ghép Mosaic 2 mảnh và Smart Date Picker.
- 📐 **[Kiến trúc hệ thống ban đầu v1.0](docs/ARCHITECTURE.md)**: Bản đặc tả kiến trúc gốc giai đoạn đầu.
- 📋 **[Kế hoạch triển khai 5 giai đoạn (Implementation Plan)](docs/IMPLEMENTATION_PLAN.md)**: Lộ trình từng bước, tiêu chí kiểm thử nghiệm thu.
- 👤 **[Đặc tả yêu cầu & Chức năng người dùng (User Requirements)](docs/USER_REQUIREMENTS.md)**: Chi tiết 5 nhóm chức năng từ góc nhìn người dùng cuối, bố cục wireframe và kịch bản tương tác.

---

## 🌟 Tính năng nổi bật

1. **On-Demand & Zero-Duplication**: Không tải sẵn hàng terabyte dữ liệu. Chỉ tải và tạo COG khi có yêu cầu từ người dùng, sau đó lưu cache vĩnh viễn trên Cloudflare R2.
2. **Microsoft Planetary Computer STAC**: Tự động tra cứu và ký token cho dải phổ Sentinel-2 L2A (10m).
3. **Cắt ảnh theo ranh giới Hà Nội**: Sử dụng GeoJSON ranh giới hành chính Hà Nội để cắt chính xác (Mask/Clip), giảm 80% dung lượng so với lưu cả tile Sentinel-2 gốc.
4. **Cloud-Optimized GeoTIFF (COG)**: Tích hợp sẵn Overviews và Deflate/WebP compression, cho phép TiTiler đọc từng vùng nhỏ qua HTTP Range Requests mà không cần kéo cả file ảnh.
5. **TiTiler Dynamic Tiles**: Cung cấp lát gạch bản đồ chuẩn XYZ trực tiếp cho OpenLayers.
6. **Background Task Queue**: Tác vụ nặng được chạy nền, frontend hiển thị trạng thái và tiến độ xử lý thời gian thực qua polling.

---

## 🚀 Hướng dẫn khởi tạo môi trường (Dành cho Windows)

### 1. Khởi tạo môi trường ảo Python
Mở terminal PowerShell tại thư mục gốc `d:\web-gis`:

```powershell
# Tạo môi trường ảo .venv
python -m venv .venv

# Kích hoạt môi trường ảo
.\.venv\Scripts\Activate.ps1

# Nâng cấp pip lên bản mới nhất
python -m pip install --upgrade pip
```

*(Lưu ý: Nếu gặp lỗi PowerShell chặn script, chạy lệnh: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

### 2. Cài đặt các thư viện cần thiết
```powershell
pip install -r backend/requirements.txt
```

### 3. Cấu hình biến môi trường
Sao chép file `.env.example` thành `.env`:
```powershell
Copy-Item .env.example .env
```
Mở file `.env` và điền thông tin Cloudflare R2:
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME` (ví dụ: `webgis-hanoi`)

---

## 🐳 Khởi chạy bằng Docker (Tùy chọn)

Dự án đã được cấu hình sẵn `Dockerfile` và `docker-compose.yml` có sẵn môi trường GDAL/GEOS:

```bash
# Build và chạy ngầm cả Backend & Frontend
docker compose up -d --build

# Xem log tiến trình
docker compose logs -f backend
```

- Backend API & TiTiler Docs: `http://localhost:8000/docs`
- WebGIS Frontend: `http://localhost:3000`

---

## 📂 Cấu trúc thư mục

```text
webgis-hanoi/
├── backend/
│   ├── app/
│   │   ├── api/             # REST Endpoints (imagery, jobs, tiles)
│   │   ├── core/            # Config, Database engine, Security
│   │   ├── models/          # Schemas (Product, Job)
│   │   ├── services/        # STAC, Raster processing, R2 storage, TiTiler
│   │   ├── tasks/           # Background workers
│   │   └── main.py          # FastAPI application entry point
│   ├── Dockerfile           # Multi-stage Docker image with GDAL
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── index.html           # WebGIS Dashboard
│   ├── styles/              # Dark Glassmorphism CSS
│   └── src/                 # OpenLayers map controllers
├── data/
│   ├── boundaries/          # GeoJSON ranh giới hành chính Hà Nội
│   └── temp/                # Thư mục xử lý COG tạm
├── docs/
│   ├── ARCHITECTURE.md      # Tài liệu kiến trúc chuẩn
│   └── IMPLEMENTATION_PLAN.md # Kế hoạch triển khai 5 giai đoạn
├── .env.example             # Mẫu biến môi trường
├── docker-compose.yml       # Điều phối container
└── README.md
```
