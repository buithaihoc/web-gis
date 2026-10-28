import os
from typing import Optional, Any
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from app.core.config import settings


class StorageService:
    def __init__(self):
        self.endpoint_url = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        self.bucket = settings.R2_BUCKET_NAME
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def object_exists(self, key: str) -> bool:
        """Kiểm tra xem object (COG) đã tồn tại trên Cloudflare R2 hay chưa."""
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            # Nếu là lỗi quyền hoặc kết nối thì raise để ghi nhận
            raise exc

    def upload_cog(self, local_path: str, key: str, content_type: str = "image/tiff; application=geotiff", progress_callback: Optional[Any] = None) -> str:
        """Tải file COG từ local lên Cloudflare R2 với callback tiến độ truyền tải byte."""
        extra_args = {"ContentType": content_type}
        kwargs = {
            "Filename": local_path,
            "Bucket": self.bucket,
            "Key": key,
            "ExtraArgs": extra_args,
        }
        if progress_callback:
            kwargs["Callback"] = progress_callback

        self.s3_client.upload_file(**kwargs)
        return key

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Tạo Presigned URL cho TiTiler hoặc Client đọc dữ liệu (mặc định hết hạn sau 1h)."""
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def get_public_or_presigned_url(self, key: str) -> str:
        """Trả về public URL nếu cấu hình R2_PUBLIC_URL, ngược lại trả về Presigned URL."""
        if settings.R2_PUBLIC_URL:
            base = settings.R2_PUBLIC_URL.rstrip("/")
            return f"{base}/{key}"
        return self.get_presigned_url(key)

    def get_s3_uri(self, key: str) -> str:
        """Trả về định dạng URI s3://bucket/key cho TiTiler đọc nội bộ."""
        return f"s3://{self.bucket}/{key}"

    def ensure_bucket_exists(self) -> bool:
        """Kiểm tra hoặc thông báo kết nối bucket."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
            return True
        except ClientError as exc:
            # Nếu bucket chưa có, thử tạo bucket
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchBucket"):
                self.s3_client.create_bucket(Bucket=self.bucket)
                return True
            raise exc


# Singleton instance
storage_service = StorageService()
