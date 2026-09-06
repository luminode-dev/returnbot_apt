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
from launch.actions import DeclareLaunchArgument, ExecuteProcess, OpaqueFunction
from launch.conditions import IfCondition
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


def ensure_world(
    apt_type: str,
    world_dir: Path,
    fire_door_closed: bool,
    clutter: bool,
    ramp_grade: float,
    threshold: float,
) -> Path:
    """월드 SDF를 returnbot_env 생성기로 만든다.

    worlds/*.sdf 는 .gitignore 대상(생성 산출물)이라 클론 직후에는 없다.
    인자에 따라 지오메트리가 달라지므로 파일명에 전 조건을 인코딩해 섞이지 않게 한다.
    (명세 Phase 2: "월드 3종 x 문턱 15 mm x 경사로 8% 구성")
    """
    parts = [
        f"apt_type_{apt_type.lower()}",
        "fdclosed" if fire_door_closed else "fdopen",
        "clutter" if clutter else "noclutter",
        f"r{round(ramp_grade * 1000):03d}",   # 경사로 구배 x1000 (0.08 -> r080)
        f"t{round(threshold * 1000):03d}",    # 문턱 높이 mm (0.015 -> t015)
    ]
    name = "_".join(parts)
    world = world_dir / f"{name}.sdf"
    if world.exists():
        return world
    world_dir.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "returnbot_env.cli",
           "--type", apt_type.upper(), "--flavor", "fortress",
           "--name", name, "--out", str(world_dir),
           "--ramp-grade", str(ramp_grade), "--threshold", str(threshold)]
    if fire_door_closed:
        cmd.append("--fire-door-closed")
    if not clutter:
        cmd.append("--no-clutter")
    subprocess.run(cmd, check=True)
    return world


def launch_setup(context, *args, **kwargs):
    apt_type = LaunchConfiguration("apt_type").perform(context).upper()
    headless = LaunchConfiguration("headless").perform(context).lower() == "true"

    sim_share = Path(get_package_share_directory(SIM_PKG))
    fire_door_closed = LaunchConfiguration("fire_door").perform(context) == "closed"
    clutter = LaunchConfiguration("clutter").perform(context).lower() == "true"
    world = ensure_world(
        apt_type, Path(LaunchConfiguration("world_dir").perform(context)),
        fire_door_closed, clutter,
        float(LaunchConfiguration("ramp_grade").perform(context)),
        float(LaunchConfiguration("threshold").perform(context)),
    )
    pose = spawn_pose(apt_type)

    render_engine = LaunchConfiguration("render_engine").perform(context)
    software_gl = LaunchConfiguration("software_rendering").perform(context).lower() == "true"

    # gpu_lidar 는 헤드리스에서도 오프스크린 렌더링을 한다. WSLg의 기본 GL 드라이버
    # (d3d12 백엔드)는 여기서 필요한 기능이 빠져 있어 두 가지로 망가진다:
    #   - ogre2: `Ogre::UnimplementedException ... GL3PlusTextureGpu::copyTo` 로 서버가 죽음
    #   - ogre1: 죽지는 않지만 전 방향이 range_min(0.05 m)으로 나오는 쓰레기 스캔
    # llvmpipe(소프트웨어 래스터라이저)로 강제하면 두 엔진 모두 정상 동작한다.
    # 실 GPU가 있는 네이티브 리눅스에서는 software_rendering:=false 로 끄는 것이 빠르다.
    #
    # Gazebo 프로세스에만 적용한다. RViz 는 하드웨어 GL 로 두는 편이 훨씬 부드럽다.
    gz_env = {"LIBGL_ALWAYS_SOFTWARE": "1"} if software_gl else {}

    gz_cmd = ["ign", "gazebo", "-r"]
    if headless:
        gz_cmd.append("-s")          # 서버만
    gz_cmd += ["--render-engine", render_engine, str(world)]

    gz = ExecuteProcess(cmd=gz_cmd, output="screen", additional_env=gz_env)

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
        DeclareLaunchArgument("render_engine", default_value="ogre2",
                              choices=["ogre", "ogre2"],
                              description="ign-rendering 엔진"),
        DeclareLaunchArgument("software_rendering", default_value="true",
                              choices=["true", "false"],
                              description="Gazebo 를 llvmpipe(소프트웨어 GL)로 실행. "
                                          "WSL에서는 켜야 gpu_lidar 가 동작한다. "
                                          "실 GPU 환경이면 false 가 훨씬 빠르다"),
        DeclareLaunchArgument("fire_door", default_value="closed",
                              choices=["closed", "open"],
                              description="복도/홀 끝 방화문 상태 (명세 §2.2의 두 상태). "
                                          "기본이 closed 인 이유: 열어 두면 문 너머가 빈 공간이라 "
                                          "LiDAR 광선이 새어나가 맵에 부채꼴 허위 자유공간이 "
                                          "생긴다. 문 너머 계단실을 월드에 만들기 전까지는 "
                                          "닫힌 상태가 기준 맵에 맞다"),
        DeclareLaunchArgument("clutter", default_value="false",
                              choices=["true", "false"],
                              description="세대 앞 적치물 배치 여부. 기본이 false 인 이유: "
                                          "기준 맵에는 구조물만 들어가야 한다. 적치물은 "
                                          "이동 가능한 물체라 Nav2 코스트맵의 동적 장애물로 "
                                          "다루는 것이 맞고, 맵에 구워 넣으면 안 된다. "
                                          "적치물 시나리오는 Phase 3 평가 주행에서 켠다"),
        DeclareLaunchArgument("ramp_grade", default_value="0.08",
                              description="복도 경사로 구배 (명세 §2.2의 8%). "
                                          "0 이면 경사로 없는 평탄 복도"),
        DeclareLaunchArgument("threshold", default_value="0.015",
                              description="세대문 앞 문턱 높이 [m] (명세 §2.2의 15 mm 기본)"),
        DeclareLaunchArgument("world_dir", default_value=default_world_dir,
                              description="월드 SDF 디렉터리. 없으면 생성기가 만든다"),
    ]
    args += [
        DeclareLaunchArgument(arg, default_value=defaults[arg],
                              description=f"robot_dimensions.yaml 의 {'.'.join(p)} 를 덮어쓴다")
        for arg, p in DIMENSION_ARGS.items()
    ]
    return LaunchDescription(args + [OpaqueFunction(function=launch_setup)])
