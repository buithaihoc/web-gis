# ==============================================================================
# HANOI SATELLITE WEBGIS - BACKEND DOCKERFILE
# Multi-stage with GDAL / PROJ / GEOS support
# ==============================================================================

FROM python:3.11-slim as base

# Ngăn chặn tạo file .pyc và bật unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Cài đặt các thư viện hệ thống cần thiết cho GDAL & C++ extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập biến môi trường GDAL cho Python bindings
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

# Cài đặt Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# Sao chép mã nguồn ứng dụng
COPY app /app/app

# Tạo thư mục dữ liệu nội bộ
RUN mkdir -p /app/data/temp /app/data/boundaries

# Expose port FastAPI
EXPOSE 8000

# Khởi chạy ứng dụng với Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
