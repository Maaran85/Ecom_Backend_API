"""
Dealer Documents Router - Specialized handling for dealer business documents
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.permissions import require_admin
from models.user import User
from models.dealer import Dealer
from services.file_upload import FileUploadService

router = APIRouter()

DOC_TYPE_MAPPING = {
    "gst_certificate": "gst_certificate_url",
    "incorporation_certificate": "incorporation_certificate_url",
    "pan_photo": "pan_photo_url",
    "aadhaar_photo": "aadhaar_photo_url",
    "company_photo": "company_photo_url",
    "cin_certificate": "cin_certificate_url",
    "company_logo": "company_logo_url"
}

@router.post("/{dealer_id}/documents/{doc_type}")
async def upload_dealer_document(
    dealer_id: int,
    doc_type: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Specialized API for uploading dealer documents"""
    print(f"DEBUG: upload_dealer_document hit for dealer={dealer_id}, doc_type={doc_type}, file={file.filename}")
    if doc_type not in DOC_TYPE_MAPPING:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Allowed: {list(DOC_TYPE_MAPPING.keys())}")
        
    res = await db.execute(select(Dealer).where(Dealer.id == dealer_id))
    dealer = res.scalar_one_or_none()
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
        
    try:
        print(f"DEBUG: Processing upload for {doc_type}...")
        folder = f"dealer_docs/{doc_type}"
        optimize = doc_type in ["company_photo", "company_logo"] 
        
        try:
            file_path = await FileUploadService.upload_image(file, folder, optimize=optimize)
            print(f"DEBUG: File saved to {file_path}")
        except Exception as e:
            print(f"DEBUG: FileUploadService failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"File service error: {str(e)}")

        image_url = FileUploadService.get_image_url(file_path)
        
        try:
            field_name = DOC_TYPE_MAPPING[doc_type]
            print(f"DEBUG: Setting {field_name} = {image_url}")
            setattr(dealer, field_name, image_url)
            await db.commit()
            print("DEBUG: DB commit successful")
        except Exception as e:
            await db.rollback()
            print(f"DEBUG: DB update failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Database update error: {str(e)}")
        
        return {
            "message": f"{doc_type.replace('_', ' ').capitalize()} uploaded successfully",
            "url": image_url,
            "field": DOC_TYPE_MAPPING[doc_type]
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.delete("/{dealer_id}/documents/{doc_type}")
async def delete_dealer_document(
    dealer_id: int,
    doc_type: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a dealer document and the associated file"""
    if doc_type not in DOC_TYPE_MAPPING:
        raise HTTPException(status_code=400, detail=f"Invalid document type")

    res = await db.execute(select(Dealer).where(Dealer.id == dealer_id))
    dealer = res.scalar_one_or_none()
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
        
    doc_field = DOC_TYPE_MAPPING[doc_type]
    image_url = getattr(dealer, doc_field)
    
    if not image_url:
        return {"message": "No document to delete"}
        
    try:
        # Extract file path from URL
        if "/uploads/" in image_url:
            file_path = image_url.split("/uploads/")[-1]
            await FileUploadService.delete_image(file_path)
            
        # Update dealer record
        setattr(dealer, doc_field, None)
        await db.commit()
        
        return {"message": f"{doc_type.replace('_', ' ').capitalize()} deleted successfully"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")
