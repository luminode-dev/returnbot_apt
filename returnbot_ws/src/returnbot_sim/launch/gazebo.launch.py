"""Gazebo Fortress에 리턴봇을 띄운다 (명세 §6 Phase 2).

    ros2 launch returnbot_sim gazebo.launch.py                  # 유형 A, GUI
    ros2 launch returnbot_sim gazebo.launch.py apt_type:=B
    ros2 launch returnbot_sim gazebo.launch.py headless:=true   # 서버만
    ros2 launch returnbot_sim gazebo.launch.py body_width:=0.65 # 차체폭 스윕

월드는 returnbot_env 생성기가 만든 SDF를 쓴다. 없으면 여기서 생성한다
(생성 산출물이라 저장소에 커밋하지 않기 때문).

표준 토픽 (명세 Phase 2): /cmd_vel /scan /odom /imu /joint_states
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

SIM_PKG = "returnbot_sim"
DESC_PKG = "returnbot_description"

#: description 에서 물려받는 차체 치수 인자 → robot_dimensions.yaml 경로
DIMENSION_ARGS = {
    "wheel_separation": ("drive", "wheel_separation"),
    "body_width": ("body", "width"),
    "body_depth": ("body", "depth"),
    "body_height": ("body", "height"),
    "wheel_radius": ("drive", "wheel_radius"),
    "wheelbase": ("chassis", "wheelbase"),
    "total_mass": ("chassis", "total_mass"),
}


def dimension_defaults() -> dict:
    path = Path(get_package_share_directory(DESC_PKG)) / "config" / "robot_dimensions.yaml"
    with open(path, encoding="utf-8") as fh:
        dims = yaml.safe_load(fh)
    return {arg: str(dims[s][k]["value"]) for arg, (s, k) in DIMENSION_ARGS.items()}


def spawn_pose(apt_type: str) -> dict:
    path = Path(get_package_share_directory(SIM_PKG)) / "config" / "spawn_poses.yaml"
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)[apt_type.upper()]


def ensure_world(apt_type: str, world_dir: Path) -> Path:
    """월드 SDF가 없으면 returnbot_env 생성기로 만든다.

    worlds/*.sdf 는 .gitignore 대상(생성 산출물)이라 클론 직후에는 없다.
    """
    world = world_dir / f"apt_type_{apt_type.lower()}.sdf"
    if world.exists():
        return world
    world_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "returnbot_env.cli",
         "--type", apt_type.upper(), "--flavor", "fortress", "--out", str(world_dir)],
        check=True,
    )
    return world


def launch_setup(context, *args, **kwargs):
    apt_type = LaunchConfiguration("apt_type").perform(context).upper()
    headless = LaunchConfiguration("headless").perform(context).lower() == "true"

    sim_share = Path(get_package_share_directory(SIM_PKG))
    world = ensure_world(apt_type, Path(LaunchConfiguration("world_dir").perform(context)))
    pose = spawn_pose(apt_type)

    # -r: 시작하자마자 물리를 돌린다. -s: 서버만(헤드리스).
    #
    # --render-engine: gpu_lidar 는 헤드리스에서도 오프스크린 렌더링을 한다. WSLg의
    # GL3Plus 드라이버는 ogre2(ogre-next)가 쓰는 텍스처 복사를 구현하지 않아
    # `Ogre::UnimplementedException ... GL3PlusTextureGpu::copyTo` 로 서버가 죽는다.
    # ogre(v1) 엔진은 같은 기능을 다른 경로로 처리해 WSL에서 동작한다.
    # 네이티브 리눅스 + 실 GPU 라면 ogre2 가 품질·성능 모두 낫다.
    render_engine = LaunchConfiguration("render_engine").perform(context)
    gz_args = f"-r {'-s ' if headless else ''}--render-engine {render_engine} {world}"

    gz = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(Path(get_package_share_directory("ros_gz_sim")) / "launch" / "gz_sim.launch.py")
        ),
        launch_arguments={"gz_args": gz_args}.items(),
    )

    xacro_file = sim_share / "urdf" / "returnbot_gz.urdf.xacro"
    command = ["xacro ", str(xacro_file)]
    for arg in DIMENSION_ARGS:
        command += [" ", f"{arg}:=", LaunchConfiguration(arg)]
    robot_description = ParameterValue(Command(command), value_type=str)

    # Gazebo가 joint_states 를 발행하므로 여기서는 robot_state_publisher 만 띄운다.
    rsp = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[{"robot_description": robot_description, "use_sim_time": True}],
    )

    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-topic", "robot_description",
            "-name", "returnbot",
            "-x", str(pose["x"]), "-y", str(pose["y"]), "-z", str(pose["z"]),
            "-Y", str(pose["yaw"]),
        ],
    )

    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        output="screen",
        arguments=[
            # ROS -> GZ
            "/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist",
            # GZ -> ROS
            "/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry",
            "/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V",
            "/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan",
            "/imu@sensor_msgs/msg/Imu[gz.msgs.IMU",
            "/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model",
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
        ],
        parameters=[{"use_sim_time": True}],
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        output="screen",
        arguments=["-d", str(sim_share / "rviz" / "returnbot_sim.rviz")],
        parameters=[{"use_sim_time": True}],
        condition=IfCondition(LaunchConfiguration("rviz")),
    )

    return [gz, rsp, spawn, bridge, rviz]


def generate_launch_description() -> LaunchDescription:
    defaults = dimension_defaults()
    default_world_dir = str(
        Path(get_package_share_directory("returnbot_env")) / "worlds"
    )

    args = [
        DeclareLaunchArgument("apt_type", default_value="A",
                              choices=["A", "B", "C", "a", "b", "c"],
                              description="아파트 유형 (A 편복도 / B 중복도 / C 홀형)"),
        DeclareLaunchArgument("headless", default_value="false",
                              description="true 면 Gazebo GUI 없이 서버만 실행"),
        DeclareLaunchArgument("rviz", default_value="true", description="RViz2 실행 여부"),
        DeclareLaunchArgument("render_engine", default_value="ogre",
                              choices=["ogre", "ogre2"],
                              description="ign-rendering 엔진. WSL에서는 ogre2가 "
                                          "gpu_lidar 렌더링 중 죽으므로 ogre 가 기본. "
                                          "네이티브 GPU 환경이면 ogre2 권장"),
        DeclareLaunchArgument("world_dir", default_value=default_world_dir,
                              description="월드 SDF 디렉터리. 없으면 생성기가 만든다"),
    ]
    args += [
        DeclareLaunchArgument(arg, default_value=defaults[arg],
                              description=f"robot_dimensions.yaml 의 {'.'.join(p)} 를 덮어쓴다")
        for arg, p in DIMENSION_ARGS.items()
    ]
    return LaunchDescription(args + [OpaqueFunction(function=launch_setup)])
