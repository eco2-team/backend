from domains.image.services.image import ImageService


def get_image_service() -> ImageService:
    return ImageService()
