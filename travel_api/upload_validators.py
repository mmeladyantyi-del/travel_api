"""Reusable size and content checks for uploaded travel documents and images."""

from pathlib import Path

from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

MAX_PDF_SIZE = 10 * 1024 * 1024
MAX_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def validate_pdf_upload(upload):
    """Require a small PDF file with a PDF header and a .pdf filename."""
    if upload.size > MAX_PDF_SIZE:
        raise serializers.ValidationError('PDF must be 10 MB or smaller.')
    if Path(upload.name).suffix.lower() != '.pdf':
        raise serializers.ValidationError('Only .pdf files are accepted.')
    # MIME headers can be forged, so also require the file's PDF signature.
    upload.seek(0)
    header = upload.read(1024)
    upload.seek(0)
    if b'%PDF-' not in header:
        raise serializers.ValidationError('The uploaded file is not a valid PDF document.')
    if upload.content_type not in {'application/pdf', 'application/octet-stream'}:
        raise serializers.ValidationError('The uploaded content type must be application/pdf.')
    return upload


def validate_image_upload(upload):
    """Require a small JPEG, PNG, or WebP image verified by Pillow."""
    if upload.size > MAX_IMAGE_SIZE:
        raise serializers.ValidationError('Image must be 5 MB or smaller.')
    if Path(upload.name).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise serializers.ValidationError('Use a .jpg, .jpeg, .png, or .webp image.')
    if upload.content_type not in {
        'image/jpeg', 'image/png', 'image/webp', 'application/octet-stream',
    }:
        raise serializers.ValidationError('Unsupported image content type.')
    upload.seek(0)
    try:
        # Pillow decodes the image header and checks for truncated or malformed content.
        with Image.open(upload) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise serializers.ValidationError('Only JPEG, PNG, and WebP images are accepted.')
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise serializers.ValidationError('The uploaded file is not a valid image.') from exc
    finally:
        upload.seek(0)
    return upload
