import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.core.database import init_db
from app.api import imagery, jobs
from app.services.tiler_service import tiler_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Hệ thống WebGIS ảnh vệ tinh Hà Nội với Microsoft Planetary Computer và Cloudflare R2",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    # Dọn dẹp các tác vụ mồ côi nếu server bị restart giữa chừng
    try:
        from sqlmodel import Session, select
        from app.core.database import engine
        from app.models.schemas import ProcessingJob
        with Session(engine) as session:
            orphan_jobs = session.exec(select(ProcessingJob).where(ProcessingJob.status.in_(["queued", "processing"]))).all()
            for j in orphan_jobs:
                j.status = "failed"
                j.error = "Tác vụ bị hủy do máy chủ khởi động lại."
                session.add(j)
            session.commit()
    except Exception as ex:
        print(f"Lỗi dọn dẹp job khi startup: {ex}")


# Đăng ký các API Routers
app.include_router(imagery.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")

# Đăng ký TiTiler Dynamic Raster COG Router
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
app.include_router(tiler_router, prefix="/titiler", tags=["TiTiler COG Engine"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)


@app.get("/api/health", tags=["System"])
def health_check():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


# Phục vụ giao diện tĩnh Frontend nếu thư mục frontend tồn tại
frontend_candidates = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend")),
    "/frontend",
    "/app/frontend",
]
frontend_dir = next((p for p in frontend_candidates if os.path.exists(p)), None)

if frontend_dir:
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    def serve_frontend_index():
        index_file = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Hanoi Satellite WebGIS Backend is running. Frontend index.html not found yet."}
