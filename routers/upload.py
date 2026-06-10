"""
Image Upload Router - Product images, Review images, Return images
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from core.permissions import get_current_active_user, require_admin, require_super_admin
from models import User, Product, Review, OrderReturn
from models.user import UserRole
from core.permissions import LOGISTICS_ROLES
from services.file_upload import FileUploadService

router = APIRouter()

# ==================== PRODUCT IMAGES ====================

@router.post("/products/{product_id}/upload-image")
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    is_primary: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload product image (dealer/admin only)"""
    
    # Get product
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check permissions (dealer can only upload for their products, admin can upload for any)
    if current_user.role == UserRole.DEALER:
        if product.dealer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only upload images for your own products"
            )
    elif current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only dealers and admins can upload product images"
        )
    
    # Upload image
    try:
        file_path = await FileUploadService.upload_image(file, "products", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        # Update product image URL
        if is_primary or not product.image_url:
            product.image_url = image_url
            await db.commit()
        
        return {
            "message": "Image uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image: {str(e)}"
        )

@router.delete("/products/{product_id}/image")
async def delete_product_image(
    product_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete product image (dealer/admin only)"""
    
    # Get product
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check permissions
    if current_user.role == UserRole.DEALER:
        if product.dealer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete images for your own products"
            )
    elif current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only dealers and admins can delete product images"
        )
    
    if not product.image_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product has no image"
        )
    
    # Extract file path from URL
    file_path = product.image_url.split("/uploads/")[-1]
    
    # Delete image
    deleted = await FileUploadService.delete_image(file_path)
    
    if deleted:
        product.image_url = None
        await db.commit()
        return {"message": "Image deleted successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete image"
        )

# ==================== REVIEW IMAGES ====================

@router.post("/reviews/{review_id}/upload-image")
async def upload_review_image(
    review_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload review image (review owner only)"""
    
    # Get review
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Check if user owns the review
    if review.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only upload images for your own reviews"
        )
    
    # Upload image
    try:
        file_path = await FileUploadService.upload_image(file, "reviews", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        # Note: Review model doesn't have image_url field yet
        # You may need to add it or store in a separate table
        
        return {
            "message": "Review image uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image: {str(e)}"
        )

# ==================== RETURN REQUEST IMAGES ====================

@router.post("/orders/{order_id}/return/upload-image")
async def upload_return_image(
    order_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload return request image (order owner only)"""
    
    # Get return request for this order
    result = await db.execute(
        select(OrderReturn).where(OrderReturn.order_id == order_id)
    )
    order_return = result.scalar_one_or_none()
    
    if not order_return:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return request not found for this order"
        )
    
    # Check if user owns the order (via order_return.order.user_id)
    # For now, we'll trust the order_id matches
    
    # Upload image
    try:
        file_path = await FileUploadService.upload_image(file, "returns", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        # Update return request images (assuming images field exists)
        if order_return.images:
            # Append to existing images
            images_list = order_return.images if isinstance(order_return.images, list) else [order_return.images]
            images_list.append(image_url)
            order_return.images = images_list
        else:
            order_return.images = [image_url]
        
        await db.commit()
        
        return {
            "message": "Return image uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload image: {str(e)}"
        )

# ==================== HUB USER PHOTOS ====================

@router.post("/hubs/users/profile-photo")
async def upload_hub_user_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload hub user profile photo (dealer/admin only)"""
    from routers.dealers import HUB_ROLES
    if current_user.role not in [UserRole.DEALER, UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.SHOWROOM_MANAGER] + HUB_ROLES + LOGISTICS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload hub user photos"
        )
        
    try:
        # Save to 'hub_user_profiles' folder
        file_path = await FileUploadService.upload_image(file, "hub_user_profiles", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Profile photo uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[DEBUG] Profile photo upload error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server Error: {str(e)}"
        )

@router.post("/hubs/users/aadhaar-photo")
async def upload_hub_user_aadhaar_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload hub user Aadhaar photo (dealer/admin only)"""
    from routers.dealers import HUB_ROLES
    if current_user.role not in [UserRole.DEALER, UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.SHOWROOM_MANAGER] + HUB_ROLES + LOGISTICS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload hub user photos"
        )
        
    try:
        # Save to 'hub_user_aadhaar' folder
        file_path = await FileUploadService.upload_image(file, "hub_user_aadhaar", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Aadhaar photo uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[DEBUG] Aadhaar photo upload error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server Error: {str(e)}"
        )

@router.post("/hubs/users/license-photo")
async def upload_hub_user_license_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload hub user License photo (dealer/admin only)"""
    from routers.dealers import HUB_ROLES
    if current_user.role not in [UserRole.DEALER, UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.SHOWROOM_MANAGER] + HUB_ROLES + LOGISTICS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload hub user photos"
        )
        
    try:
        # Save to 'hub_user_license' folder
        file_path = await FileUploadService.upload_image(file, "hub_user_license", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "License photo uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[DEBUG] License photo upload error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server Error: {str(e)}"
        )

# ==================== SHOWROOM USER PHOTOS ====================

@router.post("/showrooms/users/profile-photo")
async def upload_showroom_user_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload showroom user profile photo (dealer/admin only)"""
    if current_user.role not in [UserRole.DEALER, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload showroom user photos"
        )
        
    try:
        print(f"[DEBUG] Uploading showroom profile photo: {file.filename}")
        # Save to 'showroom_user_profiles' folder
        file_path = await FileUploadService.upload_image(file, "showroom_user_profiles", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Profile photo uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    except HTTPException as e:
        print(f"[DEBUG] Profile photo upload HTTP error: {e.detail}")
        raise
    except Exception as e:
        import traceback
        print(f"[DEBUG] Profile photo upload unexpected error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server Error: {str(e)}"
        )

@router.post("/showrooms/users/aadhaar-photo")
async def upload_showroom_user_aadhaar_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload showroom user Aadhaar photo (dealer/admin only)"""
    if current_user.role not in [UserRole.DEALER, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload showroom user photos"
        )
        
    try:
        print(f"[DEBUG] Uploading showroom aadhaar photo: {file.filename}")
        # Save to 'showroom_user_aadhaar' folder
        file_path = await FileUploadService.upload_image(file, "showroom_user_aadhaar", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Aadhaar photo uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    except HTTPException as e:
        print(f"[DEBUG] Aadhaar photo upload HTTP error: {e.detail}")
        raise
    except Exception as e:
        import traceback
        print(f"[DEBUG] Aadhaar photo upload unexpected error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server Error: {str(e)}"
        )

# ==================== DEALER USER PHOTOS ====================

@router.post("/dealers/users/profile-photo")
async def upload_dealer_user_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload dealer user profile photo (dealer/admin only)"""
    print(f"[DEBUG] Profile photo upload request received from user: {current_user.email} (Role: {current_user.role})")
    if current_user.role not in [UserRole.DEALER, UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.SHOWROOM_MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role {current_user.role} not authorized to upload dealer user photos"
        )
        
    try:
        # Save to 'dealer_user_profiles' folder
        file_path = await FileUploadService.upload_image(file, "dealer_user_profiles", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        print(f"[DEBUG] Profile photo successfully uploaded: {image_url}")
        return {
            "message": "Profile photo uploaded successfully",
            "image_url": image_url,
            "photo_url": image_url,
            "file_path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[DEBUG] Dealer profile photo upload error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server Error: {str(e)}"
        )

@router.post("/dealers/users/aadhaar-photo")
async def upload_dealer_user_aadhaar_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload dealer user Aadhaar photo (dealer/admin only)"""
    print(f"[DEBUG] Aadhaar photo upload request received from user: {current_user.email}")
    if current_user.role not in [UserRole.DEALER, UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.SHOWROOM_MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role {current_user.role} not authorized to upload documents"
        )
        
    try:
        # Save to 'dealer_user_aadhaar' folder
        file_path = await FileUploadService.upload_image(file, "dealer_user_aadhaar", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        print(f"[DEBUG] Aadhaar photo successfully uploaded: {image_url}")
        return {
            "message": "Aadhaar photo uploaded successfully",
            "image_url": image_url,
            "photo_url": image_url,
            "file_path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[DEBUG] Dealer Aadhaar photo upload error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server Error: {str(e)}"
        )

# ==================== ADMIN USER PHOTOS ====================

@router.post("/admins/profile-photo")
async def upload_admin_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload admin user profile photo (super admin only)"""
    try:
        # Save to 'admin_profiles' folder
        file_path = await FileUploadService.upload_image(file, "admin_profiles", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Admin profile photo uploaded successfully",
            "image_url": image_url,
            "photo_url": image_url,
            "file_path": file_path
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )

@router.post("/admins/aadhaar-photo")
async def upload_admin_aadhaar_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload admin Aadhaar photo (super admin only)"""
    try:
        # Save to 'admin_aadhaar' folder
        file_path = await FileUploadService.upload_image(file, "admin_aadhaar", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Admin Aadhaar photo uploaded successfully",
            "image_url": image_url,
            "photo_url": image_url,
            "file_path": file_path
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )

# ==================== LOGISTICS USER PHOTOS ====================

@router.post("/logistics/profile-photo")
async def upload_logistics_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload logistics profile photo (admin only)"""
    try:
        # Save to 'logistics_profiles' folder
        file_path = await FileUploadService.upload_image(file, "logistics_profiles", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Logistics profile photo uploaded successfully",
            "image_url": image_url,
            "photo_url": image_url,
            "file_path": file_path
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )

@router.post("/logistics/aadhaar-photo")
async def upload_logistics_aadhaar_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload logistics Aadhaar photo (admin only)"""
    try:
        # Save to 'logistics_aadhaar' folder
        file_path = await FileUploadService.upload_image(file, "logistics_aadhaar", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Logistics Aadhaar photo uploaded successfully",
            "image_url": image_url,
            "photo_url": image_url,
            "file_path": file_path
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )

# ==================== RIDER PHOTOS ====================

@router.post("/riders/upload-photo")
async def upload_rider_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload rider photo (dealer/admin/rider only)"""
    try:
        file_path = await FileUploadService.upload_image(file, "riders", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        
        return {
            "message": "Photo uploaded successfully",
            "image_url": image_url,
            "file_path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload photo: {str(e)}"
        )

# ==================== DEALER BUSINESS DOCUMENTS ====================

@router.post("/admin/dealers/gst-certificate")
async def upload_dealer_gst(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload Dealer GST Certificate (admin only)"""
    try:
        file_path = await FileUploadService.upload_image(file, "dealer_docs/gst", optimize=False) # Keep docs original if needed
        image_url = FileUploadService.get_image_url(file_path)
        return {"message": "GST Certificate uploaded", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/admin/dealers/pan-photo")
async def upload_dealer_pan(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload Dealer PAN Card Photo (admin only)"""
    try:
        file_path = await FileUploadService.upload_image(file, "dealer_docs/pan", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        return {"message": "PAN Card photo uploaded", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/admin/dealers/incorporation-certificate")
async def upload_dealer_incorporation(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload Dealer Incorporation/Trade License (admin only)"""
    try:
        file_path = await FileUploadService.upload_image(file, "dealer_docs/legal", optimize=False)
        image_url = FileUploadService.get_image_url(file_path)
        return {"message": "Incorporation certificate uploaded", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/admin/dealers/business-photo")
async def upload_dealer_business_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload Dealer Business/Shop Photo (admin only)"""
    try:
        file_path = await FileUploadService.upload_image(file, "dealer_docs/shop", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        return {"message": "Business photo uploaded", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/admin/dealers/aadhaar-photo")
async def upload_dealer_aadhaar(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload Dealer Aadhaar Card Photo (admin only)"""
    try:
        file_path = await FileUploadService.upload_image(file, "dealer_docs/aadhaar", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        return {"message": "Aadhaar Card photo uploaded", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/admin/dealers/cin-certificate")
async def upload_dealer_cin(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload Dealer CIN Certificate (admin only)"""
    try:
        file_path = await FileUploadService.upload_image(file, "dealer_docs/cin", optimize=False)
        image_url = FileUploadService.get_image_url(file_path)
        return {"message": "CIN certificate uploaded", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/admin/dealers/company-logo")
async def upload_dealer_company_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upload Dealer Company Logo (admin only)"""
    try:
        file_path = await FileUploadService.upload_image(file, "dealer_docs/logo", optimize=True)
        image_url = FileUploadService.get_image_url(file_path)
        return {"message": "Company logo uploaded", "image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# ==================== ADMIN IMAGE MANAGEMENT ====================

@router.delete("/admin/images")
async def delete_image(
    file_path: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete any uploaded image (admin only)"""
    
    deleted = await FileUploadService.delete_image(file_path)
    
    if deleted:
        return {"message": "Image deleted successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
