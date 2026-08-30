cmake_minimum_required(VERSION 3.8)
project(returnbot_description)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY urdf launch rviz config
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  # tests/ 는 ROS 없이도 도는 순수 파이썬 검증이다 (xacro 렌더 + 순기구학).
  ament_add_pytest_test(urdf_tests tests
    TIMEOUT 120
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  )
endif()

ament_package()
