#pragma once

#include <string>
#include <memory>
#include <optional>
#include "types.h"

namespace av_imgdata {
namespace image {

class ImageLoader {
public:
  // Load image from file and return image info
  static std::unique_ptr<uint8_t[]> load_jpeg(const std::string& path, ImageInfo& info);
  
  // Get image dimensions without loading full data
  static std::optional<ImageInfo> get_image_info(const std::string& path);
  
  // Get image format from file
  static ImageFormat detect_format(const std::string& path);

private:
  static ImageFormat detect_format_from_magic(const uint8_t* data, size_t size);
};

} // namespace image
} // namespace av_imgdata
