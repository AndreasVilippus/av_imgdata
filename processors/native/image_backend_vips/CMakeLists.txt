cmake_minimum_required(VERSION 3.10)
project(av_imgdata_image_processor_vips LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(PkgConfig REQUIRED)
pkg_check_modules(VIPS REQUIRED vips)
find_library(VIPS_SHARED_LIBRARY
    NAMES vips
    PATHS ${VIPS_LIBRARY_DIRS}
    NO_DEFAULT_PATH
)
if(NOT VIPS_SHARED_LIBRARY)
    message(FATAL_ERROR "libvips shared library not found in pkg-config library paths: ${VIPS_LIBRARY_DIRS}")
endif()

set(VIPS_DIRECT_RUNTIME_LIBS "")
foreach(VIPS_LIB ${VIPS_LIBRARIES})
    if(VIPS_LIB MATCHES "^(glib-2.0|gobject-2.0|gio-2.0)$")
        list(APPEND VIPS_DIRECT_RUNTIME_LIBS ${VIPS_LIB})
    endif()
endforeach()

add_executable(av-imgdata-image-processor src/main.cpp)
target_include_directories(av-imgdata-image-processor PRIVATE ${VIPS_INCLUDE_DIRS})
target_compile_options(av-imgdata-image-processor PRIVATE ${VIPS_CFLAGS_OTHER})
target_link_libraries(av-imgdata-image-processor PRIVATE ${VIPS_SHARED_LIBRARY} ${VIPS_DIRECT_RUNTIME_LIBS})
set_target_properties(av-imgdata-image-processor PROPERTIES
    INSTALL_RPATH "$ORIGIN/../lib"
    BUILD_WITH_INSTALL_RPATH FALSE
    LINK_FLAGS "-Wl,--allow-shlib-undefined"
)

install(TARGETS av-imgdata-image-processor RUNTIME DESTINATION bin)
