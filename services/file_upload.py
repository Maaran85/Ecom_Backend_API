"""
File Upload Service - Image validation, upload, and optimization
"""
import os
import uuid
from typing import Optional, Tuple
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile, HTTPException, status
from PIL import Image
import io

class FileUploadService:
    """Service for handling file uploads with validation and optimization"""
    
    # Configuration
    MAX_FILE_SIZE_MB = 10
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    MIN_DIMENSION = 200
    MAX_DIMENSION = 4000
    
    # Upload directory
    UPLOAD_DIR = Path("uploads")
    
    @classmethod
    def _ensure_upload_dir(cls, folder: str) -> Path:
        """Ensure upload directory exists"""
        upload_path = cls.UPLOAD_DIR / folder
        upload_path.mkdir(parents=True, exist_ok=True)
        return upload_path
    
    @classmethod
    async def validate_image(cls, file: UploadFile) -> Tuple[bool, Optional[str]]:
        """
        Validate uploaded image file
        Returns: (is_valid, error_message)
        """
        # Check file extension
        filename = file.filename or ""
        print(f"[DEBUG] Validating file: '{filename}'")
        file_ext = Path(filename).suffix.lower()
        if not file_ext or file_ext not in cls.ALLOWED_EXTENSIONS:
            return False, f"Invalid file format. Allowed: {', '.join(cls.ALLOWED_EXTENSIONS)}"
        
        # Read file content
        content = await file.read()
        await file.seek(0)  # Reset file pointer
        
        # Check file size
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > cls.MAX_FILE_SIZE_MB:
            return False, f"File size ({file_size_mb:.1f}MB) exceeds {cls.MAX_FILE_SIZE_MB}MB limit"
        
        # Validate image dimensions
        try:
            print(f"[DEBUG] Validating image: {file.filename}")
            image = Image.open(io.BytesIO(content))
            width, height = image.size
            
            if width < cls.MIN_DIMENSION or height < cls.MIN_DIMENSION:
                print(f"[DEBUG] Image dimensions too small: {width}x{height}")
                return False, f"Image dimensions too small. Minimum: {cls.MIN_DIMENSION}x{cls.MIN_DIMENSION}"
            
            if width > cls.MAX_DIMENSION or height > cls.MAX_DIMENSION:
                print(f"[DEBUG] Image dimensions too large: {width}x{height}")
                return False, f"Image dimensions too large. Maximum: {cls.MAX_DIMENSION}x{cls.MAX_DIMENSION}"
            
        except Exception as e:
            print(f"[DEBUG] Image validation error: {str(e)}")
            return False, f"Invalid image file: {str(e)}"
        
        return True, None
    
    @classmethod
    async def upload_image(
        cls,
        file: UploadFile,
        folder: str,
        optimize: bool = True
    ) -> str:
        """
        Upload and optionally optimize image
        Returns: relative file path
        """
        # Validate image
        is_valid, error_message = await cls.validate_image(file)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message
            )
        
        # Generate unique filename
        file_ext = Path(file.filename).suffix.lower()
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        
        # Ensure upload directory exists
        upload_path = cls._ensure_upload_dir(folder)
        file_path = upload_path / unique_filename
        
        # Ensure file pointer is at start
        await file.seek(0)
        
        # Read file content
        content = await file.read()
        
        if optimize:
            # Optimize image
            try:
                image = Image.open(io.BytesIO(content))
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot open image: {str(e)}"
                )
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            
            # Resize if too large (max 1920px on longest side)
            max_size = 1920
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Save optimized image
            image.save(file_path, quality=85, optimize=True)
        else:
            # Save original file
            with open(file_path, "wb") as f:
                f.write(content)
        
        # Return relative path
        return (Path(folder) / unique_filename).as_posix()
    
    @classmethod
    async def delete_image(cls, file_path: str) -> bool:
        """Delete uploaded image"""
        try:
            full_path = cls.UPLOAD_DIR / file_path
            if full_path.exists():
                full_path.unlink()
                return True
            return False
        except Exception:
            return False
    
    @classmethod
    def get_image_url(cls, file_path: str) -> str:
        """Get full URL for uploaded image"""
        from core.config import settings
        return f"{settings.BASE_URL}/uploads/{file_path}"
