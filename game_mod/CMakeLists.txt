cmake_minimum_required(VERSION 3.21)
project(CamLinkFreeCam LANGUAGES CXX)

if(NOT WIN32)
  message(FATAL_ERROR "CamLinkFreeCam is a Windows-only DLL.")
endif()

add_library(CamLinkFreeCam SHARED CamLinkFreeCam.cpp CamLinkFreeCam.h)
target_compile_features(CamLinkFreeCam PRIVATE cxx_std_17)
target_compile_definitions(CamLinkFreeCam PRIVATE CAMLINK_FREECAM_BUILD)
target_link_libraries(CamLinkFreeCam PRIVATE ws2_32)
set_target_properties(CamLinkFreeCam PROPERTIES OUTPUT_NAME "CamLinkFreeCam")

add_library(CamLinkXInputProxy SHARED XInputProxy.cpp XInputProxy.def)
target_compile_features(CamLinkXInputProxy PRIVATE cxx_std_17)
target_link_libraries(CamLinkXInputProxy PRIVATE user32)
set_target_properties(CamLinkXInputProxy PROPERTIES OUTPUT_NAME "xinput1_3")
