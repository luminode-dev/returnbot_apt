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
import time

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
        # 선회 속도는 맵 품질에 직접 영향을 준다. 제자리 선회 중 캐스터 구형 근사로
        # 자세 오차가 생기는데, 20 m 복도에서 12 m LiDAR 의 전후방 광선은 inf 라
        # 그 오차가 벽을 관통하는 대각선 자유공간으로 찍힌다(부채꼴 아티팩트).
        # 편도 주행만 하면 아티팩트가 전혀 없는 것으로 원인을 확인했다.
        self.declare_parameter("angular_speed", 0.3)
        self.declare_parameter("forward_distance", 15.0)
        self.declare_parameter("settle_seconds", 3.0)
        # 왕복 대신 편도만. 180도 선회가 맵 아티팩트에 관여하는지 가르는 실험용.
        self.declare_parameter("round_trip", True)

        self.apt_type = self.get_parameter("apt_type").value.upper()
        self.v = float(self.get_parameter("linear_speed").value)
        self.w = float(self.get_parameter("angular_speed").value)
        self.forward = float(self.get_parameter("forward_distance").value)
        self.settle = float(self.get_parameter("settle_seconds").value)
        self.round_trip = bool(self.get_parameter("round_trip").value)

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

    def wait_for_clock(self, timeout: float = 60.0) -> bool:
        """use_sim_time 이면 첫 /clock 을 받기 전까지 ROS 시계가 0 에 머문다.

        그 상태에서 deadline 을 계산하면(0 + 30) 시계가 시뮬 경과시간으로 튀는 순간
        곧바로 타임아웃 판정이 난다. 실제로 그 때문에 주행이 통째로 건너뛰어졌다.
        여기서는 시계가 살아날 때까지 **벽시계**로 기다린다.
        """
        if not self.get_parameter("use_sim_time").value:
            return True
        started = time.monotonic()
        while rclpy.ok() and time.monotonic() - started < timeout:
            self._spin_once()
            if self._now() > 0.0:
                self._spin_once()
                self.get_logger().info(f"시뮬 시계 동기화됨 (t={self._now():.1f}s)")
                return True
        self.get_logger().error("/clock 을 받지 못했다. 브릿지의 clock 매핑 확인 필요")
        return False

    def wait_for_odom(self, timeout: float = 60.0) -> bool:
        # 벽시계 기준. 시뮬 시계는 위에서 이미 동기화했지만, 브링업 지연은
        # 시뮬 시간이 아니라 실제 시간으로 재는 것이 맞다.
        started = time.monotonic()
        while rclpy.ok() and self.x is None and time.monotonic() - started < timeout:
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
        if not self.wait_for_clock():
            return 1
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
        """전진 후 **후진**으로 복귀한다. 복도에서는 제자리 선회를 하지 않는다.

        왜 선회하지 않는가 (실측으로 확정한 결론):

          - 20 m 복도에서 LD19 의 사거리는 12 m 라 복도 축 방향 광선은 항상 inf 다.
            slam_toolbox 는 inf 광선을 최대사거리까지 '자유공간'으로 레이트레이싱한다.
          - 제자리 선회 중에는 캐스터 구형 근사 탓에 자세 오차가 생긴다.
            그 순간의 inf 광선이 벽을 관통하는 대각선 자유공간으로 찍혀 부채꼴
            아티팩트가 남는다.
          - 대조 실험: 편도 주행(선회 없음) 맵은 20.20 x 1.45 m 로 복도 그 자체이며
            아티팩트가 전혀 없다. 경사로를 없애도(ramp_grade=0) 아티팩트는 그대로였다.
            유형 C(홀)는 360도 회전을 두 번 하는데도 깨끗한데, 홀이 좁아 모든 광선이
            벽에 닿아 inf 가 없기 때문이다.

        LiDAR 가 360도라 후진해도 관측 범위 손실이 없다. 선회 성능 자체(명세 §1
        검증항목 3의 피벗턴 경로 밀림)는 Phase 3 주행 평가에서 따로 다룬다.
        """
        out = self.drive_distance(self.forward)
        self.get_logger().info(f"전진 {out:.2f} m (목표 {self.forward:.2f} m)")
        if not self.round_trip:
            self.get_logger().info("round_trip=false — 복귀 생략")
            return
        self.stop(2.0)
        back = self.drive_distance(-self.forward)
        self.get_logger().info(f"후진 복귀 {back:.2f} m")

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
