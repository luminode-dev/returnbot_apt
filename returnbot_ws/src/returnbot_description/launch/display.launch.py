"""URDF를 RViz2로 확인하는 launch (Phase 1 완료 검증용).

    ros2 launch returnbot_description display.launch.py
    ros2 launch returnbot_description display.launch.py body_width:=0.65 wheel_separation:=0.5

명세 §7 "실기/시뮬 분기는 launch 인자로만" 원칙에 따라 이 파일에는 시뮬 전용 요소를
넣지 않는다. Gazebo 스폰은 Phase 2의 returnbot_sim 패키지가 담당한다.

차체 치수 기본값은 config/robot_dimensions.yaml 을 읽어 xacro 인자로 넘긴다.
치수 원본이 한 곳(yaml)에 있어야 실험 스크립트와 launch가 갈라지지 않는다.
"""

from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

PACKAGE = "returnbot_description"

#: launch 인자 이름 → robot_dimensions.yaml 경로
DIMENSION_ARGS = {
    "wheel_separation": ("drive", "wheel_separation"),
    "body_width": ("body", "width"),
    "body_depth": ("body", "depth"),
    "body_height": ("body", "height"),
    "wheel_radius": ("drive", "wheel_radius"),
    "wheelbase": ("chassis", "wheelbase"),
    "total_mass": ("chassis", "total_mass"),
}


def load_defaults(share_dir: str) -> dict[str, str]:
    path = Path(share_dir) / "config" / "robot_dimensions.yaml"
    with open(path, encoding="utf-8") as fh:
        dims = yaml.safe_load(fh)
    defaults = {}
    for arg, (section, key) in DIMENSION_ARGS.items():
        defaults[arg] = str(dims[section][key]["value"])
    return defaults


def launch_setup(context, *args, **kwargs):
    share_dir = get_package_share_directory(PACKAGE)
    xacro_file = PathJoinSubstitution([share_dir, "urdf", "returnbot.urdf.xacro"])

    # xacro 명령 인자: "name:=value" 를 인자 개수만큼 이어 붙인다.
    command = ["xacro ", xacro_file]
    for arg in DIMENSION_ARGS:
        command += [" ", f"{arg}:=", LaunchConfiguration(arg)]

    robot_description = ParameterValue(Command(command), value_type=str)

    return [
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": robot_description}],
        ),
        Node(
            package="joint_state_publisher_gui",
            executable="joint_state_publisher_gui",
            condition=IfCondition(LaunchConfiguration("gui")),
        ),
        Node(
            package="rviz2",
            executable="rviz2",
            output="screen",
            arguments=["-d", str(Path(share_dir) / "rviz" / "returnbot.rviz")],
            condition=IfCondition(LaunchConfiguration("rviz")),
        ),
    ]


def generate_launch_description() -> LaunchDescription:
    defaults = load_defaults(get_package_share_directory(PACKAGE))

    declarations = [
        DeclareLaunchArgument(
            arg,
            default_value=defaults[arg],
            description=f"robot_dimensions.yaml 의 {'.'.join(DIMENSION_ARGS[arg])} 를 덮어쓴다",
        )
        for arg in DIMENSION_ARGS
    ]
    declarations += [
        DeclareLaunchArgument("gui", default_value="true",
                              description="joint_state_publisher_gui 실행 여부"),
        DeclareLaunchArgument("rviz", default_value="true", description="RViz2 실행 여부"),
    ]

    return LaunchDescription(declarations + [OpaqueFunction(function=launch_setup)])
