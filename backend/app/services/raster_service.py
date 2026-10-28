import os
import json
import uuid
from typing import Dict, Any, Tuple
import rasterio
from rasterio.mask import mask
import numpy as np
from shapely.geometry import shape
from shapely.ops import transform
import pyproj
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from app.core.config import settings


class RasterService:
    def __init__(self):
        os.makedirs(settings.TEMP_DIR, exist_ok=True)

    def _get_projected_hanoi_geometry(self, target_crs, raster_bounds=None) -> list:
        """Đọc GeoJSON Hà Nội và chuyển đổi CRS từ WGS84 sang CRS của ảnh, cắt chuẩn theo bounds ảnh."""
        with open(settings.HANOI_BOUNDARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            geom_wgs84 = shape(data["features"][0]["geometry"])

        project = pyproj.Transformer.from_crs(
            pyproj.CRS("EPSG:4326"),
            pyproj.CRS(target_crs),
            always_xy=True,
        ).transform

        projected_geom = transform(project, geom_wgs84)
        if raster_bounds is not None:
            from shapely.geometry import box
            raster_box = box(*raster_bounds)
            if projected_geom.intersects(raster_box):
                projected_geom = projected_geom.intersection(raster_box)
        return [projected_geom.__geo_interface__]

    def process_rgb_cog(self, visual_urls: Any, output_filename: str, progress_callback: Any = None) -> Tuple[str, int, list]:
        """
        Đọc asset 'visual' từ MPC qua mạng, cắt theo polygon Hà Nội,
        tự động ghép mảnh đa tile (Bắc 48QWJ + Nam 48QWH) nếu có,
        tạo Cloud-Optimized GeoTIFF (COG) với overviews nội tại.
        Trả về: (local_cog_path, file_size_bytes, bounds_wgs84)
        """
        urls = [visual_urls] if isinstance(visual_urls, str) else visual_urls
        temp_raw_path = os.path.join(settings.TEMP_DIR, f"raw_{uuid.uuid4().hex[:8]}.tif")
        final_cog_path = os.path.join(settings.TEMP_DIR, output_filename)

        masked_tiles = []
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            VSI_CACHE="TRUE",
            VSI_CACHE_SIZE="100000000",
            GDAL_HTTP_TIMEOUT="30",
            GDAL_HTTP_MAX_RETRY="5",
            GDAL_HTTP_RETRY_DELAY="1",
        ):
            total_urls = len(urls)
            for idx, u in enumerate(urls):
                tile_label = "Bắc (T48QWJ)" if idx == 0 else "Nam (T48QWH)"
                if progress_callback:
                    pct = 35 + int((idx / total_urls) * 30)  # 35% -> 50%
                    progress_callback(pct, f"Đang stream dữ liệu phổ 10m mảnh {tile_label} ({idx+1}/{total_urls})...")

                try:
                    with rasterio.open(u) as src:
                        projected_shapes = self._get_projected_hanoi_geometry(src.crs, raster_bounds=src.bounds)
                        img, tr = mask(src, projected_shapes, crop=True, nodata=0)
                        if img.any():
                            masked_tiles.append((img, tr, src.crs, src.meta.copy()))
                except Exception as ex:
                    print(f"Cảnh báo: Không đọc được mảnh ảnh {u}: {ex}")

        if not masked_tiles:
            raise ValueError("Không thể trích xuất dữ liệu ảnh từ các URL được cung cấp")

        if len(masked_tiles) == 1:
            out_image, out_transform, target_crs, out_meta = masked_tiles[0]
        else:
            if progress_callback:
                progress_callback(68, "Đang ghép nối toàn vẹn (Mosaic Bắc - Nam) và khớp ranh giới Hà Nội...")

            from rasterio.io import MemoryFile
            from rasterio.merge import merge

            memfiles = []
            ds_list = []
            for img, tr, crs, meta in masked_tiles:
                mem = MemoryFile()
                m_copy = meta.copy()
                m_copy.update({
                    "driver": "GTiff",
                    "height": img.shape[1],
                    "width": img.shape[2],
                    "transform": tr,
                    "nodata": 0,
                })
                with mem.open(**m_copy) as d:
                    d.write(img)
                memfiles.append(mem)
                ds_list.append(mem.open())

            out_image, out_transform = merge(ds_list, nodata=0)
            target_crs = masked_tiles[0][2]
            out_meta = masked_tiles[0][3].copy()
            for ds in ds_list:
                ds.close()
            for mem in memfiles:
                mem.close()

        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
            "nodata": 0,
        })

        from rasterio.transform import array_bounds
        from rasterio.warp import transform_bounds
        crop_b = array_bounds(out_image.shape[1], out_image.shape[2], out_transform)
        bounds_wgs84 = list(transform_bounds(target_crs, "EPSG:4326", *crop_b))

        with rasterio.open(temp_raw_path, "w", **out_meta) as dest:
            dest.write(out_image)

        if progress_callback:
            progress_callback(80, "Đang xây dựng kim tự tháp đa độ phân giải chuẩn COG...")

        # Chuyển đổi sang chuẩn COG (Cloud-Optimized GeoTIFF)
        output_profile = cog_profiles.get("deflate")
        output_profile.update({
            "blockxsize": 256,
            "blockysize": 256,
        })

        cog_translate(
            temp_raw_path,
            final_cog_path,
            output_profile,
            config={"GDAL_NUM_THREADS": "ALL_CPUS"},
            in_memory=False,
            quiet=True,
        )

        if os.path.exists(temp_raw_path):
            os.remove(temp_raw_path)

        file_size = os.path.getsize(final_cog_path)
        return final_cog_path, file_size, bounds_wgs84

    def process_ndvi_cog(self, b08_urls: Any, b04_urls: Any, output_filename: str, progress_callback: Any = None) -> Tuple[str, int, list]:
        """
        Đọc band 8 (NIR) và band 4 (Red), cắt theo Hà Nội,
        tự động ghép mảnh đa tile (Bắc 48QWJ + Nam 48QWH) nếu có,
        tính toán NDVI = (NIR - RED) / (NIR + RED), lưu COG float32.
        """
        urls_08 = [b08_urls] if isinstance(b08_urls, str) else b08_urls
        urls_04 = [b04_urls] if isinstance(b04_urls, str) else b04_urls

        temp_raw_path = os.path.join(settings.TEMP_DIR, f"ndvi_raw_{uuid.uuid4().hex[:8]}.tif")
        final_cog_path = os.path.join(settings.TEMP_DIR, output_filename)

        ndvi_tiles = []
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            VSI_CACHE="TRUE",
            VSI_CACHE_SIZE="100000000",
            GDAL_HTTP_TIMEOUT="30",
            GDAL_HTTP_MAX_RETRY="5",
            GDAL_HTTP_RETRY_DELAY="1",
        ):
            total_pairs = len(urls_08)
            for idx, (u08, u04) in enumerate(zip(urls_08, urls_04)):
                tile_label = "Bắc (T48QWJ)" if idx == 0 else "Nam (T48QWH)"
                if progress_callback:
                    pct = 35 + int((idx / total_pairs) * 30)
                    progress_callback(pct, f"Đang tính toán NDVI mảnh {tile_label} ({idx+1}/{total_pairs})...")

                try:
                    with rasterio.open(u08) as src_nir, rasterio.open(u04) as src_red:
                        projected_shapes = self._get_projected_hanoi_geometry(src_nir.crs, raster_bounds=src_nir.bounds)
                        nir_masked, transform_nir = mask(src_nir, projected_shapes, crop=True, nodata=0)
                        red_masked, _ = mask(src_red, projected_shapes, crop=True, nodata=0)

                        nir = nir_masked[0].astype(np.float32)
                        red = red_masked[0].astype(np.float32)

                        denominator = nir + red
                        ndvi = np.where(denominator > 0, (nir - red) / denominator, -9999.0)

                        meta = src_nir.meta.copy()
                        ndvi_tiles.append((ndvi, transform_nir, src_nir.crs, meta))
                except Exception as ex:
                    print(f"Cảnh báo: Lỗi tính NDVI cho mảnh {u08}: {ex}")

        if not ndvi_tiles:
            raise ValueError("Không tính toán được NDVI từ các band được cung cấp")

        if len(ndvi_tiles) == 1:
            ndvi, transform_nir, target_crs, out_meta = ndvi_tiles[0]
            out_image = ndvi[np.newaxis, :, :]
        else:
            if progress_callback:
                progress_callback(68, "Đang ghép nối raster NDVI Bắc - Nam và lọc ranh giới...")

            from rasterio.io import MemoryFile
            from rasterio.merge import merge

            memfiles = []
            ds_list = []
            for ndvi_arr, tr, crs, meta in ndvi_tiles:
                mem = MemoryFile()
                m_copy = meta.copy()
                m_copy.update({
                    "driver": "GTiff",
                    "dtype": "float32",
                    "count": 1,
                    "height": ndvi_arr.shape[0],
                    "width": ndvi_arr.shape[1],
                    "transform": tr,
                    "nodata": -9999.0,
                })
                with mem.open(**m_copy) as d:
                    d.write(ndvi_arr[np.newaxis, :, :])
                memfiles.append(mem)
                ds_list.append(mem.open())

            out_image, transform_nir = merge(ds_list, nodata=-9999.0)
            target_crs = ndvi_tiles[0][2]
            out_meta = ndvi_tiles[0][3].copy()
            for ds in ds_list:
                ds.close()
            for mem in memfiles:
                mem.close()

        out_meta.update({
            "driver": "GTiff",
            "dtype": "float32",
            "count": 1,
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": transform_nir,
            "nodata": -9999.0,
        })

        from rasterio.transform import array_bounds
        from rasterio.warp import transform_bounds
        crop_b = array_bounds(out_image.shape[1], out_image.shape[2], transform_nir)
        bounds_wgs84 = list(transform_bounds(target_crs, "EPSG:4326", *crop_b))

        with rasterio.open(temp_raw_path, "w", **out_meta) as dest:
            dest.write(out_image)

        if progress_callback:
            progress_callback(80, "Đang nén dữ liệu chỉ số thực vật sang chuẩn COG...")

        output_profile = cog_profiles.get("deflate")
        output_profile.update({"blockxsize": 256, "blockysize": 256})

        cog_translate(
            temp_raw_path,
            final_cog_path,
            output_profile,
            config={"GDAL_NUM_THREADS": "ALL_CPUS"},
            in_memory=False,
            quiet=True,
        )

        if os.path.exists(temp_raw_path):
            os.remove(temp_raw_path)

        file_size = os.path.getsize(final_cog_path)
        return final_cog_path, file_size, bounds_wgs84


raster_service = RasterService()
