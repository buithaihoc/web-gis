import datetime
from typing import List, Dict, Any, Optional
import json
import planetary_computer
from pystac_client import Client
from app.core.config import settings


class STACService:
    def __init__(self):
        self.stac_url = settings.MPC_STAC_URL
        self._catalog = None

    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = Client.open(
                self.stac_url,
                modifier=planetary_computer.sign_inplace,
            )
        return self._catalog

    def get_hanoi_geometry(self) -> Dict[str, Any]:
        """Đọc GeoJSON ranh giới hành chính Hà Nội."""
        with open(settings.HANOI_BOUNDARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Lấy geometry của feature đầu tiên
            return data["features"][0]["geometry"]

    def _fetch_items_with_retry(self, search, max_retries: int = 3) -> list:
        """Thực thi truy vấn STAC với cơ chế tự động thử lại khi gặp upstream timeout từ Microsoft MPC."""
        import time
        last_exc = None
        for attempt in range(max_retries):
            try:
                return list(search.items())
            except Exception as exc:
                last_exc = exc
                wait_time = 1.0 * (attempt + 1)
                print(f"Cảnh báo: MPC STAC request timeout (lần {attempt + 1}/{max_retries}): {exc}. Đang thử lại sau {wait_time}s...")
                time.sleep(wait_time)
        raise last_exc

    def search_scenes_by_date(
        self,
        target_date: str,  # "YYYY-MM-DD"
        max_cloud: Optional[float] = None,
        search_window_days: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Tìm kiếm các cảnh ảnh Sentinel-2 L2A bao quanh Hà Nội vào ngày chỉ định.

        Logic tìm kiếm thông minh:
        - Ưu tiên ảnh ĐÚNG ngày + ít mây nhất.
        - Nếu không có ảnh đúng ngày, mở rộng tìm kiếm trong ±search_window_days.
        - Cân bằng giữa khoảng cách ngày (Sentinel-2 chu kỳ ~5 ngày) và độ che phủ mây.
        - Trả về date_match_status: 'exact' hoặc 'nearest' cùng metadata chi tiết.

        Args:
            target_date: Ngày mục tiêu (YYYY-MM-DD)
            max_cloud: Độ che phủ mây tối đa cho phép (0-100)
            search_window_days: Số ngày mở rộng tìm kiếm mỗi hướng nếu không có ảnh đúng ngày
        """
        max_cloud = max_cloud if max_cloud is not None else settings.MAX_CLOUD_COVER
        parsed_date = datetime.date.fromisoformat(target_date)
        bbox = json.loads(settings.HANOI_BBOX) if isinstance(settings.HANOI_BBOX, str) else settings.HANOI_BBOX

        # --- Bước 1: Tìm đúng ngày trước ---
        start_exact = parsed_date
        end_exact = parsed_date + datetime.timedelta(days=1)
        search_exact = self.catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=f"{start_exact.isoformat()}T00:00:00Z/{end_exact.isoformat()}T23:59:59Z",
            max_items=30,
        )
        items_exact = self._fetch_items_with_retry(search_exact)

        # Lọc đúng ngày theo mây
        exact_filtered = [
            it for it in items_exact
            if it.properties.get("eo:cloud_cover", 100) <= max_cloud
        ]

        # --- Bước 2: Nếu không có hoặc mây quá nhiều, mở rộng window ---
        # Lấy tất cả items trong cửa sổ ±search_window_days để so sánh
        start_wide = parsed_date - datetime.timedelta(days=search_window_days)
        end_wide = parsed_date + datetime.timedelta(days=search_window_days)
        search_wide = self.catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=f"{start_wide.isoformat()}T00:00:00Z/{end_wide.isoformat()}T23:59:59Z",
            max_items=100,
        )
        items_wide = self._fetch_items_with_retry(search_wide)

        # Gộp items (ưu tiên items chính xác ngày)
        all_items_by_id = {}
        for it in items_wide:
            all_items_by_id[it.id] = it
        for it in items_exact:
            all_items_by_id[it.id] = it
        all_items = list(all_items_by_id.values())

        # Hàm kiểm tra cảnh có bao trùm trung tâm Hà Nội (105.8342°E, 21.0278°N) không
        def covers_hanoi_center(it):
            b = getattr(it, "bbox", None)
            return bool(b and (b[0] <= 105.8342 <= b[2]) and (b[1] <= 21.0278 <= b[3]))

        # --- Bước 3: Hàm xếp hạng thông minh: ưu tiên đúng ngày, sau đó ít mây ---
        def smart_sort_key(it):
            it_date = it.datetime.date() if it.datetime else parsed_date
            diff_days = abs((it_date - parsed_date).days)
            cloud = it.properties.get("eo:cloud_cover", 100)
            is_center = 0 if covers_hanoi_center(it) else 1

            # Logic xếp hạng:
            # - Ngay đúng ngày (diff=0): ưu tiên rất cao, chỉ bị ảnh hưởng bởi mây
            # - Ngày lân cận: 1 ngày chênh = tương đương ~10% mây thêm
            # Trọng số: mỗi ngày chênh lệch ~ penalty 10% mây
            adjusted_cloud_score = cloud + (diff_days * 10)

            return (is_center, adjusted_cloud_score)

        # Tất cả items đã lọc mây (hoặc fallback nếu max_cloud quá chặt)
        filtered_all = [it for it in all_items if it.properties.get("eo:cloud_cover", 100) <= max_cloud]

        # Nếu không có ảnh nào trong window thỏa mây, fallback lấy ít mây nhất dù vượt threshold
        if not filtered_all:
            filtered_all = all_items

        sorted_items = sorted(filtered_all, key=smart_sort_key)

        def get_asset_href(item_obj, key):
            if not item_obj:
                return None
            asset = item_obj.assets.get(key)
            if asset is not None:
                return getattr(asset, "href", None) or (asset.get("href") if isinstance(asset, dict) else None)
            return None

        results = []
        for item in sorted_items:
            item_date = item.datetime.date() if item.datetime else None
            orbit = item.properties.get("sat:relative_orbit")
            item_cloud = item.properties.get("eo:cloud_cover", 0.0)

            # Xác định date_match_status
            if item_date == parsed_date:
                date_match_status = "exact"
                date_diff_days = 0
            else:
                date_match_status = "nearest"
                date_diff_days = abs((item_date - parsed_date).days) if item_date else None

            # Tìm mảnh ảnh phía Nam (48QWH) từ cùng lượt bay để ghép toàn vẹn 100% Hà Nội
            south_item = next(
                (
                    s_it for s_it in all_items
                    if s_it.id != item.id
                    and (s_it.datetime.date() if s_it.datetime else None) == item_date
                    and s_it.properties.get("sat:relative_orbit") == orbit
                    and ("QWH" in s_it.id or s_it.properties.get("s2:mgrs_tile") == "48QWH")
                ),
                None
            )

            visual_hrefs = [h for h in [get_asset_href(item, "visual"), get_asset_href(south_item, "visual")] if h]
            b08_hrefs = [h for h in [get_asset_href(item, "B08"), get_asset_href(south_item, "B08")] if h]
            b04_hrefs = [h for h in [get_asset_href(item, "B04"), get_asset_href(south_item, "B04")] if h]

            source_scenes = [item.id]
            if south_item:
                source_scenes.append(south_item.id)

            # Thông báo chi tiết cho người dùng
            if date_match_status == "exact":
                date_info_message = f"Ảnh đúng ngày {item_date} (mây {item_cloud:.1f}%)"
            else:
                direction = "trước" if (item_date < parsed_date) else "sau"
                date_info_message = (
                    f"Không có ảnh ngày {parsed_date}, hiển thị ngày gần nhất: "
                    f"{item_date} ({date_diff_days} ngày {direction}, mây {item_cloud:.1f}%)"
                )

            # Cảnh báo nếu mây vượt threshold
            cloud_warning = None
            if item_cloud > max_cloud:
                cloud_warning = f"Mây {item_cloud:.1f}% vượt ngưỡng yêu cầu {max_cloud:.0f}% (không có ảnh nào tốt hơn trong ±{search_window_days} ngày)"

            results.append({
                "item_id": item.id,
                "datetime": item.datetime.isoformat() if item.datetime else None,
                "date": item.datetime.strftime("%Y-%m-%d") if item.datetime else None,
                "requested_date": target_date,
                "date_match_status": date_match_status,   # "exact" | "nearest"
                "date_diff_days": date_diff_days,          # 0 nếu exact
                "date_info_message": date_info_message,
                "cloud_warning": cloud_warning,
                "cloud_cover": round(item_cloud, 2),
                "max_cloud_requested": max_cloud,
                "platform": item.properties.get("platform", "Sentinel-2"),
                "bbox": item.bbox,
                "thumbnail_url": get_asset_href(item, "rendered_preview") or get_asset_href(item, "thumbnail"),
                "visual_href": visual_hrefs[0] if visual_hrefs else None,
                "visual_hrefs": visual_hrefs,
                "b04_href": b04_hrefs[0] if b04_hrefs else None,
                "b04_hrefs": b04_hrefs,
                "b03_href": get_asset_href(item, "B03"),
                "b02_href": get_asset_href(item, "B02"),
                "b08_href": b08_hrefs[0] if b08_hrefs else None,
                "b08_hrefs": b08_hrefs,
                "source_scenes": source_scenes,
                "has_southern_tile": bool(south_item),
            })

        return results

    def get_available_dates_in_month(
        self,
        year: int,
        month: int,
        max_cloud: float = 50.0,
    ) -> List[Dict[str, Any]]:
        """
        Tìm danh sách tất cả các ngày trong một tháng có ảnh vệ tinh Sentinel-2 bay qua Hà Nội.
        Dùng để tô màu/đánh dấu trên Lịch giao diện WebGIS.
        """
        import calendar
        _, last_day = calendar.monthrange(year, month)
        start_str = f"{year:04d}-{month:02d}-01T00:00:00Z"
        end_str = f"{year:04d}-{month:02d}-{last_day:02d}T23:59:59Z"

        bbox = json.loads(settings.HANOI_BBOX) if isinstance(settings.HANOI_BBOX, str) else settings.HANOI_BBOX

        search = self.catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=f"{start_str}/{end_str}",
            max_items=100,
        )

        dates_map = {}
        for item in self._fetch_items_with_retry(search):
            cloud = item.properties.get("eo:cloud_cover", 100)
            if item.datetime:
                d_str = item.datetime.strftime("%Y-%m-%d")
                if d_str not in dates_map or cloud < dates_map[d_str]["cloud_cover"]:
                    dates_map[d_str] = {
                        "date": d_str,
                        "cloud_cover": round(cloud, 2),
                        "item_id": item.id,
                        "within_cloud_limit": cloud <= max_cloud,
                    }

        sorted_dates = sorted(dates_map.values(), key=lambda x: x["date"])
        return sorted_dates


stac_service = STACService()
