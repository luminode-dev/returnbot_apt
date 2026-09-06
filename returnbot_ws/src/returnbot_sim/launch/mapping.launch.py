"""Gazebo + slam_toolbox 맵핑 (명세 §6 Phase 2).

    ros2 launch returnbot_sim mapping.launch.py apt_type:=A
    ros2 launch returnbot_sim mapping.launch.py apt_type:=B headless:=true rviz:=false

주행은 별도로 돌린다:
    ros2 run returnbot_sim drive_mapping_run.py --ros-args -p apt_type:=A   # 자동(재현 가능)
    ros2 launch returnbot_sim teleop.launch.py                              # 손으로

맵 저장:
    ros2 run nav2_map_server map_saver_cli -f <경로>/apt_type_a
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

SIM_PKG = "returnbot_sim"


def generate_launch_description() -> LaunchDescription:
    sim_share = Path(get_package_share_directory(SIM_PKG))

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(sim_share / "launch" / "gazebo.launch.py")),
        launch_arguments={
            "apt_type": LaunchConfiguration("apt_type"),
            "headless": LaunchConfiguration("headless"),
            "rviz": LaunchConfiguration("rviz"),
            "software_rendering": LaunchConfiguration("software_rendering"),
            "render_engine": LaunchConfiguration("render_engine"),
            "fire_door": LaunchConfiguration("fire_door"),
        }.items(),
    )

    slam = Node(
        package="slam_toolbox",
        executable="async_slam_toolbox_node",
        name="slam_toolbox",
        output="screen",
        parameters=[
            str(sim_share / "config" / "slam_toolbox.yaml"),
            {"use_sim_time": True},
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument("apt_type", default_value="A",
                              choices=["A", "B", "C", "a", "b", "c"],
                              description="아파트 유형"),
        DeclareLaunchArgument("headless", default_value="false",
                              description="Gazebo GUI 없이 서버만"),
        DeclareLaunchArgument("rviz", default_value="true", description="RViz2 실행 여부"),
        DeclareLaunchArgument("software_rendering", default_value="true",
                              choices=["true", "false"],
                              description="WSL에서는 켜야 gpu_lidar 가 동작한다"),
        DeclareLaunchArgument("render_engine", default_value="ogre2",
                              choices=["ogre", "ogre2"], description="ign-rendering 엔진"),
        DeclareLaunchArgument("fire_door", default_value="closed",
                              choices=["closed", "open"],
                              description="방화문 상태. 기준 맵은 closed 로 만든다"),
        gazebo,
        slam,
    ])
