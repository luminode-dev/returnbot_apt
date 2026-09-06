"""키보드 텔레옵 (명세 §6 Phase 2 "텔레옵 주행").

    ros2 launch returnbot_sim teleop.launch.py

teleop_twist_keyboard 는 키 입력을 받아야 해서 **자기 터미널이 필요하다.**
launch 에서 띄우면 stdin 이 붙지 않아 먹통이 되므로, 이 launch 는 별도 터미널을
띄우는 대신 실행 방법을 안내한다. 맵을 만들 목적이라면 재현 가능한
`drive_mapping_run.py` 쪽을 쓰는 것이 낫다.

속도 기본값은 명세 §3을 따른다 — 운용 0.6 m/s, 최고 1.0 m/s.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument("speed", default_value="0.6",
                              description="직진 속도 [m/s] (명세 §3 운용속도)"),
        DeclareLaunchArgument("turn", default_value="0.8",
                              description="회전 속도 [rad/s]"),
        # xterm 이 있으면 새 터미널에서 띄운다. 없으면 아래 안내대로 직접 실행.
        ExecuteProcess(
            cmd=[
                "xterm", "-fa", "Monospace", "-fs", "11", "-e",
                "ros2", "run", "teleop_twist_keyboard", "teleop_twist_keyboard",
                "--ros-args",
                "-p", ["speed:=", LaunchConfiguration("speed")],
                "-p", ["turn:=", LaunchConfiguration("turn")],
                "-r", "__ns:=/",
            ],
            output="screen",
            shell=False,
            on_exit=[],
        ),
    ])
