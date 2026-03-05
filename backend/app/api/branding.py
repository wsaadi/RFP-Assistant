"""Branding API routes for logo, app name, and favicon management."""
import logging
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..models.branding import BrandingSettings
from .deps import get_admin_user

router = APIRouter(prefix="/branding", tags=["Branding"])
audit_log = logging.getLogger("security.audit")

BRANDING_DIR = os.path.join(settings.images_dir, "branding")
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/svg+xml", "image/x-icon", "image/vnd.microsoft.icon", "image/webp"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB


async def _get_or_create_branding(db: AsyncSession) -> BrandingSettings:
    """Get the single branding row, creating it if it doesn't exist."""
    result = await db.execute(select(BrandingSettings).limit(1))
    branding = result.scalar_one_or_none()
    if not branding:
        branding = BrandingSettings()
        db.add(branding)
        await db.commit()
        await db.refresh(branding)
    return branding


@router.get("/settings")
async def get_branding(db: AsyncSession = Depends(get_db)):
    """Get branding settings (public, no auth required)."""
    branding = await _get_or_create_branding(db)
    return {
        "app_name": branding.app_name,
        "has_logo": bool(branding.logo_filename),
        "has_favicon": bool(branding.favicon_filename),
        "primary_color": branding.primary_color,
        "logo_url": f"/api/branding/logo" if branding.logo_filename else "",
        "favicon_url": f"/api/branding/favicon" if branding.favicon_filename else "",
    }


@router.put("/settings")
async def update_branding(
    app_name: str = "",
    primary_color: str = "#1B3A5C",
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update branding text settings (admin only)."""
    branding = await _get_or_create_branding(db)
    if app_name:
        branding.app_name = app_name[:255]
    if primary_color:
        branding.primary_color = primary_color[:20]
    await db.commit()
    await db.refresh(branding)

    audit_log.info("Branding updated: app_name=%s by admin=%s", branding.app_name, admin.email)

    return {
        "app_name": branding.app_name,
        "has_logo": bool(branding.logo_filename),
        "has_favicon": bool(branding.favicon_filename),
        "primary_color": branding.primary_color,
        "logo_url": f"/api/branding/logo" if branding.logo_filename else "",
        "favicon_url": f"/api/branding/favicon" if branding.favicon_filename else "",
    }


@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload application logo (admin only)."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Format d'image non supporté. Utilisez PNG, JPG, SVG ou WebP.")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier est trop volumineux (max 2 Mo).")

    os.makedirs(BRANDING_DIR, exist_ok=True)

    ext = os.path.splitext(file.filename or "logo.png")[1] or ".png"
    filename = f"logo_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(BRANDING_DIR, filename)

    branding = await _get_or_create_branding(db)

    # Remove old logo
    if branding.logo_filename:
        old_path = os.path.join(BRANDING_DIR, branding.logo_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    with open(filepath, "wb") as f:
        f.write(content)

    branding.logo_filename = filename
    await db.commit()

    audit_log.info("Logo uploaded: %s by admin=%s", filename, admin.email)
    return {"message": "Logo mis à jour", "logo_url": "/api/branding/logo"}


@router.post("/favicon")
async def upload_favicon(
    file: UploadFile = File(...),
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload application favicon (admin only)."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Format d'image non supporté. Utilisez PNG, ICO, SVG ou WebP.")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier est trop volumineux (max 2 Mo).")

    os.makedirs(BRANDING_DIR, exist_ok=True)

    ext = os.path.splitext(file.filename or "favicon.ico")[1] or ".ico"
    filename = f"favicon_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(BRANDING_DIR, filename)

    branding = await _get_or_create_branding(db)

    # Remove old favicon
    if branding.favicon_filename:
        old_path = os.path.join(BRANDING_DIR, branding.favicon_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    with open(filepath, "wb") as f:
        f.write(content)

    branding.favicon_filename = filename
    await db.commit()

    audit_log.info("Favicon uploaded: %s by admin=%s", filename, admin.email)
    return {"message": "Favicon mis à jour", "favicon_url": "/api/branding/favicon"}


@router.get("/logo")
async def get_logo(db: AsyncSession = Depends(get_db)):
    """Serve the application logo (public)."""
    branding = await _get_or_create_branding(db)
    if not branding.logo_filename:
        raise HTTPException(status_code=404, detail="Aucun logo configuré")

    filepath = os.path.join(BRANDING_DIR, branding.logo_filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Fichier logo introuvable")

    return FileResponse(filepath, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/favicon")
async def get_favicon(db: AsyncSession = Depends(get_db)):
    """Serve the application favicon (public)."""
    branding = await _get_or_create_branding(db)
    if not branding.favicon_filename:
        raise HTTPException(status_code=404, detail="Aucun favicon configuré")

    filepath = os.path.join(BRANDING_DIR, branding.favicon_filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Fichier favicon introuvable")

    return FileResponse(filepath, headers={"Cache-Control": "public, max-age=3600"})


@router.delete("/logo")
async def delete_logo(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the application logo (admin only)."""
    branding = await _get_or_create_branding(db)
    if branding.logo_filename:
        old_path = os.path.join(BRANDING_DIR, branding.logo_filename)
        if os.path.exists(old_path):
            os.remove(old_path)
        branding.logo_filename = ""
        await db.commit()
    return {"message": "Logo supprimé"}


@router.delete("/favicon")
async def delete_favicon(
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the application favicon (admin only)."""
    branding = await _get_or_create_branding(db)
    if branding.favicon_filename:
        old_path = os.path.join(BRANDING_DIR, branding.favicon_filename)
        if os.path.exists(old_path):
            os.remove(old_path)
        branding.favicon_filename = ""
        await db.commit()
    return {"message": "Favicon supprimé"}
