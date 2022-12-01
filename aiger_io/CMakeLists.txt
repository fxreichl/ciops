project(aiger LANGUAGES C CXX)
cmake_minimum_required(VERSION 3.4...3.18)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

if (CMAKE_SOURCE_DIR STREQUAL CMAKE_BINARY_DIR ) 
  message (FATAL_ERROR
    "In-source builds are not allowed. Please clean your source tree and try again.")  
endif()

# add_compile_options (-O3 -DNDEBUG)

add_library(aiger_library aiger/aiger.h aiger/aiger.c)
target_compile_options(aiger_library PRIVATE -fPIC)

find_package(pybind11 CONFIG)
message(STATUS "Found pybind11 v${pybind11_VERSION}: ${pybind11_INCLUDE_DIRS}")
if (pybind11_FOUND) 
  pybind11_add_module(aiger SHARED aiger_bindings.cc)
  target_link_libraries(aiger PRIVATE aiger_library)
  # target_include_directories(aiger PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/aiger")
  target_include_directories(aiger PUBLIC "aiger")
else ()
  message(SEND_ERROR "pybind11 must be provided")
endif()
