import os
from fastapi import UploadFile
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", ""),
    api_key = os.getenv("CLOUDINARY_API_KEY", ""),
    api_secret = os.getenv("CLOUDINARY_API_SECRET", ""),
    secure = True
)

async def upload_image_to_cloudinary(file: UploadFile, folder: str = "smafit/avatars") -> str:
    """
    Uploads an image to Cloudinary and returns the public secure URL.
    """
    try:
        file_data = await file.read()
        result = cloudinary.uploader.upload(
            file_data, 
            folder=folder,
            resource_type="image"
        )
        
        return result["secure_url"]
        
    except Exception as e:
        print(f"Error uploading to Cloudinary: {e}")
        raise Exception("Failed to upload image to Cloudinary")
    finally:
        await file.seek(0)
