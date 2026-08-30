"""ROS 워크스페이스 밖에서도 pytest가 패키지를 찾도록 경로를 잡아준다."""

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
