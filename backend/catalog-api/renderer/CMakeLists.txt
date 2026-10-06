cmake_minimum_required(VERSION 3.16)
project(terento_preview_render LANGUAGES CXX)

# Headless Garmin IMG -> Web Mercator WebP tile renderer for map style
# previews. The IMG decoder and renderer are a vendored subset of GPXSee
# (GPL-3.0); see third_party/gpxsee/VENDORED.md.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Qt6 REQUIRED COMPONENTS Core Gui Concurrent)
find_package(ZLIB REQUIRED)

set(GPXSEE ${CMAKE_CURRENT_SOURCE_DIR}/third_party/gpxsee/src)
file(STRINGS ${CMAKE_CURRENT_SOURCE_DIR}/third_party/gpxsee/FILES VENDORED)
set(GPXSEE_SOURCES)
foreach(f ${VENDORED})
  if(f MATCHES "\\.cpp$")
    list(APPEND GPXSEE_SOURCES ${GPXSEE}/${f})
  endif()
endforeach()

add_executable(terento-preview-render src/main.cpp ${GPXSEE_SOURCES})
target_include_directories(terento-preview-render PRIVATE ${GPXSEE})
target_compile_options(terento-preview-render PRIVATE -w)
target_link_libraries(terento-preview-render PRIVATE
  Qt6::Core Qt6::Gui Qt6::Concurrent ZLIB::ZLIB)
install(TARGETS terento-preview-render RUNTIME DESTINATION bin)
