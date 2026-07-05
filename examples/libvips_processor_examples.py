#!/usr/bin/env python3
"""
Example usage of NativeImageProcessorVipsService.

This demonstrates how to use the libvips image processor for common operations.
"""

from pathlib import Path
from services.config_service import ConfigService
from services.native_image_processor_vips_service import (
    NativeImageProcessor,
    NativeImageProcessorVipsService,
)


def example_basic_status():
    """Example: Check processor availability."""
    config_service = ConfigService("/etc/av_imgdata/config.json")
    service = NativeImageProcessorVipsService(config_service)
    
    status = service.status()
    print(f"Processor available: {status['available']}")
    print(f"Backend: {status['backend']}")
    print(f"Version: {status.get('version')}")
    print(f"Supported formats: {status['formats']}")


def example_resize():
    """Example: Resize an image."""
    config_service = ConfigService("/etc/av_imgdata/config.json")
    service = NativeImageProcessorVipsService(config_service)
    
    image_path = Path("/var/photos/sample.jpg")
    
    # Resize to 640x480
    result = service.resize_image(
        image_path=image_path,
        width=640,
        height=480,
        output_format="jpeg",
        quality=95
    )
    
    if result['success']:
        print(f"Image resized to {result['width']}x{result['height']}")
        print(f"Output: {result['output_path']}")
    else:
        print(f"Error: {result['error']}")


def example_auto_orient():
    """Example: Auto-orient image based on EXIF metadata."""
    config_service = ConfigService("/etc/av_imgdata/config.json")
    service = NativeImageProcessorVipsService(config_service)
    
    image_path = Path("/var/photos/camera.jpg")
    
    result = service.auto_orient_image(image_path)
    if result['success']:
        print("Image auto-oriented successfully")
    else:
        print(f"Error: {result['error']}")


def example_batch_processing():
    """Example: Process multiple images."""
    config_service = ConfigService("/etc/av_imgdata/config.json")
    service = NativeImageProcessorVipsService(config_service)
    
    image_files = list(Path("/var/photos").glob("*.jpg"))[:10]  # First 10 JPGs
    
    # Resize all images
    results = service.batch_process_images(
        image_paths=image_files,
        operation="resize",
        options={"width": 800, "height": 600},
        output_format="jpeg"
    )
    
    successful = sum(1 for r in results if r['success'])
    failed = len(results) - successful
    print(f"Processed {len(results)} images: {successful} successful, {failed} failed")


def example_processor_interface():
    """Example: Use high-level processor interface."""
    config_service = ConfigService("/etc/av_imgdata/config.json")
    service = NativeImageProcessorVipsService(config_service)
    
    image_path = Path("/var/photos/sample.jpg")
    
    # Create processor instance
    processor = NativeImageProcessor(
        service=service,
        image_path=image_path,
        output_format="jpeg",
        quality=90
    )
    
    if processor.is_available:
        # Get image info
        info = processor.info()
        print(f"Image size: {info['width']}x{info['height']}")
        
        # Resize
        result = processor.resize(640, 480)
        if result['success']:
            print("Resized successfully")
        
        # Auto-orient
        result = processor.auto_orient()
        if result['success']:
            print("Auto-oriented successfully")
        
        # Rotate
        result = processor.rotate(90)
        if result['success']:
            print("Rotated 90 degrees")
        
        # Convert to PNG
        result = processor.convert("png")
        if result['success']:
            print("Converted to PNG")
    else:
        print("Processor not available")


def example_error_handling():
    """Example: Handle common errors."""
    config_service = ConfigService("/etc/av_imgdata/config.json")
    service = NativeImageProcessorVipsService(config_service)
    
    # Non-existent image
    result = service.resize_image(
        Path("/nonexistent/image.jpg"),
        640, 480
    )
    if not result['success']:
        print(f"Error: {result['error']}")
    
    # Invalid rotation angle
    result = service.rotate_image(
        Path("/var/photos/sample.jpg"),
        45  # Invalid - must be 90, 180, or 270
    )
    if not result['success']:
        print(f"Error: {result['error']}")
    
    # Unsupported format (if not configured)
    result = service.convert_image(
        Path("/var/photos/sample.jpg"),
        "unsupported_format"
    )
    if not result['success']:
        print(f"Error: {result['error']}")


def example_format_conversion():
    """Example: Convert between formats."""
    config_service = ConfigService("/etc/av_imgdata/config.json")
    service = NativeImageProcessorVipsService(config_service)
    
    image_path = Path("/var/photos/sample.jpg")
    
    # Convert JPEG to PNG (lossless)
    result = service.convert_image(
        image_path,
        output_format="png"
    )
    
    # Convert to WebP (modern format, good compression)
    result = service.convert_image(
        image_path,
        output_format="webp",
        options={"quality": 85}
    )
    
    if result['success']:
        print(f"Converted to {result['format']}")


def example_get_image_info():
    """Example: Get image metadata."""
    config_service = ConfigService("/etc/av_imgdata/config.json")
    service = NativeImageProcessorVipsService(config_service)
    
    image_path = Path("/var/photos/sample.jpg")
    
    info = service.get_image_info(image_path)
    if info['success']:
        print(f"Format: {info.get('format')}")
        print(f"Dimensions: {info.get('width')}x{info.get('height')}")
        print(f"EXIF Orientation: {info.get('orientation')}")
        print(f"Color Space: {info.get('color_space')}")
        print(f"Has Alpha: {info.get('has_alpha')}")


if __name__ == "__main__":
    print("=== libvips Native Image Processor Examples ===\n")
    
    print("1. Basic Status Check")
    try:
        example_basic_status()
    except Exception as e:
        print(f"   (Example requires configuration: {e})\n")
    
    print("\n2. Resize Image")
    try:
        example_resize()
    except Exception as e:
        print(f"   (Example requires configuration: {e})\n")
    
    print("\n3. Auto-Orient Image")
    try:
        example_auto_orient()
    except Exception as e:
        print(f"   (Example requires configuration: {e})\n")
    
    print("\n4. Batch Processing")
    try:
        example_batch_processing()
    except Exception as e:
        print(f"   (Example requires configuration: {e})\n")
    
    print("\n5. High-Level Processor Interface")
    try:
        example_processor_interface()
    except Exception as e:
        print(f"   (Example requires configuration: {e})\n")
    
    print("\n6. Error Handling")
    try:
        example_error_handling()
    except Exception as e:
        print(f"   (Example requires configuration: {e})\n")
    
    print("\n7. Format Conversion")
    try:
        example_format_conversion()
    except Exception as e:
        print(f"   (Example requires configuration: {e})\n")
    
    print("\n8. Get Image Metadata")
    try:
        example_get_image_info()
    except Exception as e:
        print(f"   (Example requires configuration: {e})\n")
