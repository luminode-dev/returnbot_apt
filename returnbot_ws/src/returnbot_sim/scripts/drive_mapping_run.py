#!/usr/bin/env python3
"""맵핑용 자동 주행 (명세 §6 Phase 2 "텔레옵 주행 → slam_toolbox 맵 저장").

손으로 텔레옵을 하면 매번 다른 맵이 나와 Phase 3의 기준 맵으로 쓸 수 없다.
같은 인자로 항상 같은 경로를 주행해 재현 가능한 맵을 만든다.
사람이 직접 몰아보는 텔레옵은 `teleop.launch.py` 로 따로 제공한다.

    ros2 run returnbot_sim drive_mapping_run.py --ros-args -p apt_type:=A

/odom 피드백으로 거리·각도를 닫아 제어하므로 시뮬 실시간 배율에 영향받지 않는다.
표준 토픽만 쓴다 (/cmd_vel, /odom) — 명세 §7 "측정 코드는 표준 토픽만 구독".
"""

import math
import sys

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy


def yaw_from_quaternion(q) -> float:
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


def wrap(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


class MappingDriver(Node):
    """복도를 왕복하거나 홀을 한 바퀴 돌며 LiDAR가 벽을 고루 보게 만든다."""

    def __init__(self) -> None:
        super().__init__("drive_mapping_run")

        self.declare_parameter("apt_type", "A")
        self.declare_parameter("linear_speed", 0.3)   # 맵 품질 우선 (운용속도 0.6보다 느리게)
        self.declare_parameter("angular_speed", 0.5)
        self.declare_parameter("forward_distance", 15.0)
        self.declare_parameter("settle_seconds", 3.0)

        self.apt_type = self.get_parameter("apt_type").value.upper()
        self.v = float(self.get_parameter("linear_speed").value)
        self.w = float(self.get_parameter("angular_speed").value)
        self.forward = float(self.get_parameter("forward_distance").value)
        self.settle = float(self.get_parameter("settle_seconds").value)

        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)
        odom_qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self.create_subscription(Odometry, "odom", self._on_odom, odom_qos)

        self.x = self.y = self.yaw = None

    # ------------------------------------------------------------------ 콜백
    def _on_odom(self, msg: Odometry) -> None:
        self.x = msg.pose.pose.position.x
        self.y = msg.pose.pose.position.y
        self.yaw = yaw_from_quaternion(msg.pose.pose.orientation)

    # ------------------------------------------------------------- 기본 동작
    def _spin_once(self) -> None:
        rclpy.spin_once(self, timeout_sec=0.05)

    def _now(self) -> float:
        """경과 시간 기준 [s].

        반복 횟수 x 0.05 로 시간을 세면 안 된다. spin_once 는 메시지가 이미 와 있으면
        곧바로 반환하므로, odom 50 Hz 에서는 루프가 훨씬 빨리 돌아 '180초 타임아웃'이
        실제로는 3.5초 만에 걸린다. 실제로 그 버그로 3 m 주행이 0.98 m 에서 잘렸다.
        use_sim_time 이 켜져 있으면 ROS 클럭이 /clock(시뮬 시간)을 따라간다.
        """
        return self.get_clock().now().nanoseconds / 1e9

    def wait_for_odom(self, timeout: float = 30.0) -> bool:
        deadline = self._now() + timeout
        while rclpy.ok() and self.x is None and self._now() < deadline:
            self._spin_once()
        if self.x is None:
            self.get_logger().error("/odom 을 받지 못했다. 브릿지와 diff_drive 플러그인 확인 필요")
            return False
        self.get_logger().info(f"odom 수신: x={self.x:.2f} y={self.y:.2f} yaw={self.yaw:.2f}")
        return True

    def publish(self, linear: float, angular: float) -> None:
        msg = Twist()
        msg.linear.x = linear
        msg.angular.z = angular
        self.cmd_pub.publish(msg)

    def stop(self, seconds: float = 1.0) -> None:
        deadline = self._now() + seconds
        while rclpy.ok() and self._now() < deadline:
            self.publish(0.0, 0.0)
            self._spin_once()

    def drive_distance(self, distance: float, timeout: float = 180.0) -> float:
        """직진. 실제 이동 거리를 돌려준다 (문턱·경사로에서 밀리면 여기서 드러난다)."""
        x0, y0 = self.x, self.y
        travelled = 0.0
        deadline = self._now() + timeout
        timed_out = False
        sign = 1.0 if distance >= 0 else -1.0
        while rclpy.ok() and travelled < abs(distance):
            if self._now() >= deadline:
                timed_out = True
                break
            self.publish(sign * self.v, 0.0)
            self._spin_once()
            travelled = math.hypot(self.x - x0, self.y - y0)
        self.stop(0.5)
        if timed_out:
            self.get_logger().warn(
                f"직진 타임아웃: 목표 {abs(distance):.2f} m 중 {travelled:.2f} m 만 이동"
            )
        return travelled

    def rotate(self, angle: float, timeout: float = 120.0) -> float:
        """제자리 회전. 명세 Phase 3의 rotate-in-place 정책과 같은 동작이다."""
        turned = 0.0
        previous = self.yaw
        deadline = self._now() + timeout
        timed_out = False
        sign = 1.0 if angle >= 0 else -1.0
        while rclpy.ok() and turned < abs(angle):
            if self._now() >= deadline:
                timed_out = True
                break
            self.publish(0.0, sign * self.w)
            self._spin_once()
            turned += abs(wrap(self.yaw - previous))
            previous = self.yaw
        self.stop(0.5)
        if timed_out:
            self.get_logger().warn(f"회전 타임아웃: {math.degrees(turned):.0f}도만 회전")
        return turned

    # --------------------------------------------------------------- 시나리오
    def run(self) -> int:
        if not self.wait_for_odom():
            return 1

        self.get_logger().info(f"유형 {self.apt_type} 맵핑 주행 시작")
        # slam_toolbox 가 첫 스캔을 받고 자리를 잡을 시간을 준다.
        self.stop(self.settle)

        if self.apt_type == "C":
            self._run_hall()
        else:
            self._run_corridor()

        self.stop(2.0)
        self.get_logger().info(
            f"주행 완료: 최종 위치 x={self.x:.2f} y={self.y:.2f} yaw={math.degrees(self.yaw):.0f}도"
        )
        return 0

    def _run_corridor(self) -> None:
        """복도 왕복. 편복도는 개방측 난간 때문에 한쪽 반사가 약해 왕복이 특히 중요하다."""
        out = self.drive_distance(self.forward)
        self.get_logger().info(f"전진 {out:.2f} m (목표 {self.forward:.2f} m)")
        self.rotate(math.pi)
        back = self.drive_distance(self.forward)
        self.get_logger().info(f"복귀 {back:.2f} m")
        self.rotate(math.pi)

    def _run_hall(self) -> None:
        """홀은 좁아 왕복이 무의미하다. 제자리 360도 + 짧은 전후진으로 벽을 고루 훑는다."""
        self.rotate(2 * math.pi)
        self.drive_distance(1.0)
        self.rotate(2 * math.pi)
        self.drive_distance(-1.0)


def main() -> int:
    rclpy.init()
    node = MappingDriver()
    try:
        return node.run()
    except KeyboardInterrupt:
        node.stop(0.5)
        return 130
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
