import os
from titiler.core.factory import TilerFactory
from app.core.config import settings

# Cấu hình môi trường GDAL cho TiTiler để đọc trực tiếp từ S3-compatible Cloudflare R2
if settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID:
    os.environ["AWS_S3_ENDPOINT"] = f"{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    os.environ["AWS_ACCESS_KEY_ID"] = settings.R2_ACCESS_KEY_ID
    os.environ["AWS_SECRET_ACCESS_KEY"] = settings.R2_SECRET_ACCESS_KEY
    os.environ["AWS_REGION"] = "auto"
    os.environ["AWS_VIRTUAL_HOSTING"] = "FALSE"
    os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
    os.environ["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif,.tiff"

# Khởi tạo TiTiler Factory
cog_tiler = TilerFactory()
tiler_router = cog_tiler.router
