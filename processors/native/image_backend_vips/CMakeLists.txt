cmake_minimum_required(VERSION 3.10)
project(av_imgdata_image_processor_vips LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(av-imgdata-image-processor src/main.cpp)
set_target_properties(av-imgdata-image-processor PROPERTIES
    INSTALL_RPATH "$ORIGIN/../lib"
    BUILD_WITH_INSTALL_RPATH FALSE
)

install(TARGETS av-imgdata-image-processor RUNTIME DESTINATION bin)
