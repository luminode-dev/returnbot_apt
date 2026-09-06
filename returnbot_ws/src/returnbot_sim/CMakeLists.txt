cmake_minimum_required(VERSION 3.8)
project(returnbot_sim)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY urdf launch config rviz
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS scripts/drive_mapping_run.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
