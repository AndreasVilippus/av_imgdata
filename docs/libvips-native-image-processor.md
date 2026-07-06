# Native libvips Image Processor

## Overview

The native libvips image processor provides a high-performance image processing backend for the AV_ImgData package. It handles image resizing, rotation, format conversion, and metadata extraction using the efficient libvips library.

## Architecture

### Components

1. **NativeImageProcessorVipsService** - Main service adapter for the libvips processor
2. **NativeImageProcessor** - High-level processor interface for individual images
3. **NativeImageProcessorVipsUnavailable** - Exception for processor unavailability

### Service Responsibilities

- Binary availability and health checking
- Configuration management
- Subprocess communication with the native processor
- Error handling and logging
- Format support validation

## Configuration

Configure the libvips processor in your config.json:

```json
{
  "native_processors": {
    "IMAGE_PROCESSOR_VIPS": {
      "ENABLED": true,
      "PATH": "bin/av-imgdata-image-processor",
      "PREFERRED": true,
      "ALLOW_FALLBACK_TO_DEFAULT": true,
      "TIMEOUT_SECONDS": 120,
      "SUPPORTED_FORMATS": ["jpeg", "jpg", "png", "webp", "tiff"]
    }
  }
}
```

### Configuration Options

- **ENABLED**: Enable/disable the processor (default: false)
- **PATH**: Path to the processor binary (default: bin/av-imgdata-image-processor)
- **PREFERRED**: Mark as preferred image backend (default: true)
- **ALLOW_FALLBACK_TO_DEFAULT**: Fall back to default backend if processor fails (default: true)
- **TIMEOUT_SECONDS**: Subprocess timeout in seconds (default: 120, min: 1, max: 3600)
- **SUPPORTED_FORMATS**: List of supported image formats (default: jpeg, jpg, png, webp, tiff)

## Usage

### Basic Usage with Service

```python
from services.native_image_processor_vips_service import NativeImageProcessorVipsService
from pathlib import Path

# Initialize service
service = NativeImageProcessorVipsService(config_service)

# Check status
status = service.status()
if status['available']:
    # Process image
    result = service.resize_image(
        Path("input.jpg"),
        width=640,
        height=480,
        output_format="jpeg",
        quality=95
    )
    if result['success']:
        print(f"Image processed successfully")
```

### High-Level Processor Interface

```python
from services.native_image_processor_vips_service import NativeImageProcessor

# Create processor instance
processor = NativeImageProcessor(
    service=service,
    image_path=Path("input.jpg"),
    output_format="jpeg",
    quality=95
)

# Use processor methods
if processor.is_available:
    # Resize image
    result = processor.resize(640, 480)
    
    # Auto-orient based on EXIF
    result = processor.auto_orient()
    
    # Rotate image
    result = processor.rotate(90)
    
    # Convert format
    result = processor.convert("png")
    
    # Get image info
    info = processor.info()
```

## Available Operations

### Image Resizing

```python
result = service.resize_image(
    image_path=Path("input.jpg"),
    width=640,
    height=480,
    output_format="jpeg",
    quality=95
)
```

**Parameters:**

- `image_path`: Path to input image (required)
- `width`: Target width in pixels (required)
- `height`: Target height in pixels (required)
- `output_format`: Output format (default: jpeg)
- `quality`: JPEG/WebP quality 1-100 (default: 95)

### Image Rotation

```python
result = service.rotate_image(
    image_path=Path("input.jpg"),
    angle=90,  # Only 90, 180, 270 allowed
    output_format="jpeg"
)
```

**Parameters:**

- `image_path`: Path to input image (required)
- `angle`: Rotation angle - 90, 180, or 270 (required)
- `output_format`: Output format (default: jpeg)

### Auto-Orientation

```python
result = service.auto_orient_image(
    image_path=Path("input.jpg"),
    output_format="jpeg"
)
```

Applies EXIF orientation metadata to correct image rotation automatically.

### Format Conversion

```python
result = service.convert_image(
    image_path=Path("input.jpg"),
    output_format="png",
    options={"quality": 95}
)
```

**Parameters:**

- `image_path`: Path to input image (required)
- `output_format`: Target format (required)
- `options`: Format-specific options (optional)

### Custom Operations

```python
result = service.process_image(
    image_path=Path("input.jpg"),
    operation="custom-op",
    options={"param1": "value1"},
    output_format="jpeg"
)
```

### Batch Processing

```python
results = service.batch_process_images(
    image_paths=[Path("img1.jpg"), Path("img2.jpg"), Path("img3.jpg")],
    operation="resize",
    options={"width": 640, "height": 480},
    output_format="jpeg"
)

# Results contain path and success/error for each image
for result in results:
    print(f"{result['path']}: {result['success']}")
```

### Image Information

```python
info = service.get_image_info(Path("input.jpg"))
if info['success']:
    print(f"Dimensions: {info['width']}x{info['height']}")
    print(f"Format: {info['format']}")
    print(f"Orientation: {info.get('orientation')}")
```

## Status Checks

Query processor availability:

```python
status = service.status()

print(f"Available: {status['available']}")
print(f"Reason: {status['reason']}")
print(f"Backend: {status['backend']}")
print(f"Version: {status.get('version')}")
print(f"Supported formats: {status['formats']}")

if status['available']:
    print("Processor is ready for use")
else:
    print(f"Processor not available: {status['reason']}")
    print(f"Last error: {status.get('last_error')}")
```

### Status Reasons

- **vips_disabled** - Processor is disabled in configuration
- **vips_binary_missing** - Processor binary not found at configured path
- **vips_binary_not_executable** - Binary exists but is not executable
- **vips_version_failed** - Unable to query version from processor
- **vips_probe_failed** - Processor probe failed (libvips not linked)
- **vips_ready** - Processor is ready for use

## Result Format

All operations return a result dictionary:

```python
{
    "success": true,  # bool - Operation success
    "error": None,    # str or None - Error message if failed
    "image_path": "...",  # For batch operations
    "output_path": "...",  # If available
    "format": "jpeg",  # Output format
    "width": 640,  # Output dimensions
    "height": 480,
    "timestamp": 1234567890.5  # Operation timestamp
}
```

### Success Response Example

```python
{
    "success": true,
    "contract_version": "1.0",
    "operation": "resize",
    "output_path": "/tmp/output.jpg",
    "format": "jpeg",
    "width": 640,
    "height": 480,
    "timestamp": 1234567890.5
}
```

### Error Response Example

```python
{
    "success": false,
    "error": "image_not_found"
}
```

## Error Handling

Common error codes:

- **processor_disabled** - Processor is disabled
- **vips_unavailable** - Processor not available
- **image_not_found** - Input image does not exist
- **unsupported_format** - Output format not supported
- **invalid_rotation_angle** - Rotation angle must be 90, 180, or 270
- **processor_error** - General processor error
- **invalid_result_json** - Invalid JSON response from processor

## Native Processor Binary Interface

The native processor binary implements the following commands:

### Version Command

```bash
av-imgdata-image-processor version
```

Output: `av-imgdata-image-processor 0.2.0 libvips 8.x.x`

### Probe Command

```bash
av-imgdata-image-processor probe
```

Output (JSON):

```json
{
  "contract_version": "1.0",
  "backend": "libvips",
  "available": true,
  "reason": "vips_ready",
  "formats": {
    "jpeg": true,
    "png": true,
    "webp": true,
    "tiff": true
  }
}
```

### Process Command

```bash
av-imgdata-image-processor process \
  --input job-input.json \
  --output processor-result.json \
  --workdir /tmp/workdir
```

Input file format (job-input.json):

```json
{
  "contract_version": "1.0",
  "image_path": "/path/to/input.jpg",
  "operation": "resize",
  "output_format": "jpeg",
  "options": {
    "width": 640,
    "height": 480,
    "quality": 95
  },
  "timestamp": 1234567890.5
}
```

Output file format (processor-result.json):

```json
{
  "success": true,
  "contract_version": "1.0",
  "operation": "resize",
  "output_path": "/tmp/workdir/output.jpg",
  "format": "jpeg",
  "width": 640,
  "height": 480,
  "timestamp": 1234567890.5
}
```

### Info Command

```bash
av-imgdata-image-processor info \
  --input job-input.json \
  --output processor-result.json \
  --workdir /tmp/workdir
```

Returns image metadata without modifying the image.

## Performance Considerations

1. **Quality Settings**: Higher quality values (85-95) produce better results but larger file sizes
2. **Format Selection**:
   - JPEG: Smallest file size, good for photos
   - PNG: Lossless, larger files, better for graphics
   - WebP: Modern format, better compression than JPEG
3. **Timeout**: Adjust `TIMEOUT_SECONDS` based on image size and system performance
4. **Batch Processing**: Process multiple images in parallel for better throughput

## Testing

Run tests:

```bash
python3 -m pytest tests/unit/services/test_native_image_processor_vips_service.py -v
```

## Fallback Behavior

When `ALLOW_FALLBACK_TO_DEFAULT` is enabled and the native processor fails:

1. Service operation returns error result
2. Caller application decides whether to retry with default backend
3. No automatic fallback occurs at service level
4. Allows precise error tracking and logging

## Logging and Debugging

Enable debug logging:

```python
service.set_debug_logger(lambda event, **fields: 
    print(f"[{event}] {fields}")
)

# Operations will log debug events
```

Logged events:

- `native_image_processor_vips_run_failed` - Command execution failure
- `native_image_processor_vips_run_command` - Command execution (with sanitized output)

## Limitations

1. Processor runs in separate process (security boundary)
2. Each operation creates temporary work directory
3. File I/O overhead for large batches
4. Maximum file size limited by available disk space
5. Concurrent operation safety depends on temporary directory isolation

## Future Enhancements

Planned features:

1. Worker pool for concurrent processing
2. Output caching for frequently processed images
3. Streaming support for large images
4. Additional format support (HEIF, AVIF)
5. Advanced filtering operations
6. Metadata preservation options
7. Parallel batch processing with thread pool

## License

libvips is provided under LGPL 2.1+. Ensure license compliance when building and distributing the native processor binary.
