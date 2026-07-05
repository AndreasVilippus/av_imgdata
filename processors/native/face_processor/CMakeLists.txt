cmake_minimum_required(VERSION 3.10)
project(av_imgdata_face_processor LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT ONNXRUNTIME_ROOT)
    message(FATAL_ERROR "ONNXRUNTIME_ROOT is required")
endif()
find_path(ONNXRUNTIME_INCLUDE_DIR
    NAMES onnxruntime_c_api.h
    PATHS "${ONNXRUNTIME_ROOT}/include" "${ONNXRUNTIME_ROOT}/include/onnxruntime/core/session"
    NO_DEFAULT_PATH
)
find_library(ONNXRUNTIME_LIBRARY
    NAMES onnxruntime
    PATHS "${ONNXRUNTIME_ROOT}/lib" "${ONNXRUNTIME_ROOT}/lib64"
    NO_DEFAULT_PATH
)
if(NOT ONNXRUNTIME_INCLUDE_DIR OR NOT ONNXRUNTIME_LIBRARY)
    message(FATAL_ERROR "ONNXRuntime C API not found below ONNXRUNTIME_ROOT=${ONNXRUNTIME_ROOT}")
endif()

add_executable(av-imgdata-face-processor src/main.cpp)

find_path(JPEG_INCLUDE_DIR
    NAMES jpeglib.h
    PATHS "${JPEG_ROOT}/include" "${JPEG_ROOT}/usr/include"
)
find_library(JPEG_LIBRARY
    NAMES jpeg
    PATHS "${JPEG_ROOT}/lib" "${JPEG_ROOT}/usr/lib" "${JPEG_ROOT}/usr/lib64"
)
if(NOT JPEG_INCLUDE_DIR OR NOT JPEG_LIBRARY)
    message(FATAL_ERROR "libjpeg not found; set JPEG_ROOT to a sysroot containing jpeglib.h and libjpeg")
endif()
find_path(HEIF_INCLUDE_DIR
    NAMES libheif/heif.h
    PATHS "${HEIF_ROOT}/include" "${HEIF_ROOT}/usr/include" "${JPEG_ROOT}/include" "${JPEG_ROOT}/usr/include"
)
target_include_directories(av-imgdata-face-processor PRIVATE "${ONNXRUNTIME_INCLUDE_DIR}" "${JPEG_INCLUDE_DIR}")
if(HEIF_INCLUDE_DIR)
    set(HEIF_PRIVATE_INCLUDE_DIR "${CMAKE_CURRENT_BINARY_DIR}/heif-include")
    file(MAKE_DIRECTORY "${HEIF_PRIVATE_INCLUDE_DIR}")
    file(COPY "${HEIF_INCLUDE_DIR}/libheif" DESTINATION "${HEIF_PRIVATE_INCLUDE_DIR}")
    target_compile_definitions(av-imgdata-face-processor PRIVATE AV_FACE_PROCESSOR_WITH_HEIF=1)
    target_include_directories(av-imgdata-face-processor PRIVATE "${HEIF_PRIVATE_INCLUDE_DIR}")
endif()
target_link_libraries(av-imgdata-face-processor PRIVATE "${ONNXRUNTIME_LIBRARY}" "${JPEG_LIBRARY}" ${CMAKE_DL_LIBS})
set_target_properties(av-imgdata-face-processor PROPERTIES
    INSTALL_RPATH "$ORIGIN/../lib"
    BUILD_WITH_INSTALL_RPATH FALSE
)

install(TARGETS av-imgdata-face-processor RUNTIME DESTINATION bin)
install(DIRECTORY "${ONNXRUNTIME_ROOT}/lib/" DESTINATION lib
    FILES_MATCHING PATTERN "libonnxruntime.so*"
)
install(FILES "${JPEG_LIBRARY}" DESTINATION lib)
