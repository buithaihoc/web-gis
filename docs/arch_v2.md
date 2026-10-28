# KIẾN TRÚC HỆ THỐNG WEBGIS ẢNH VỆ TINH HÀ NỘI (PHIÊN BẢN 2.0)

> Tài liệu kiến trúc hoàn chỉnh đã được lưu trữ tại: **[ARCHITECTURE_V2.md](file:///d:/web-gis/docs/ARCHITECTURE_V2.md)**

Vui lòng xem file chính thức tại liên kết trên để đọc đầy đủ các sơ đồ Mermaid:
1. Sơ đồ kiến trúc tổng thể 4 tầng (Client, Reverse Proxy Nginx, FastAPI + TiTiler, Cloud Infrastructure).
2. Sơ đồ điều phối Docker & Mạng Container (Port 3000 & Port 8000).
3. Sơ đồ luồng dữ liệu chi tiết Cache HIT và Cache MISS / On-Demand Pipeline.
4. Thiết kế Smart Date Picker & STAC Flyover Sync.
5. Cấu trúc CSDL SQLite & Lưu trữ Cloudflare R2.
