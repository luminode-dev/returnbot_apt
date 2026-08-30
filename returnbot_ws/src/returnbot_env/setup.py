from glob import glob

from setuptools import find_packages, setup

package_name = "returnbot_env"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["tests"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        # 생성된 월드는 .gitignore 대상이지만, 빌드 시점에 존재하면 함께 설치한다.
        ("share/" + package_name + "/worlds", glob("worlds/*.sdf")),
    ],
    install_requires=["setuptools", "PyYAML"],
    zip_safe=True,
    maintainer="luminode",
    maintainer_email="luminode00@gmail.com",
    description="한국 아파트 공용부 파라메트릭 월드 생성기 (Gazebo SDF + 평면도 SVG)",
    license="TODO",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "generate_world = returnbot_env.cli:main",
        ],
    },
)
