from glob import glob
from setuptools import find_packages, setup

package_name = "swarm_sar_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Swarm SAR Maintainers",
    maintainer_email="maintainer@example.com",
    description="Decentralized exploration and realistic peer transport for Swarm-SAR.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "disaster_scene = swarm_sar_control.disaster_scene:main",
            "waypoint_demo = swarm_sar_control.waypoint_demo:main",
            "demo_views = swarm_sar_control.demo_views:main",
            "demo_camera = swarm_sar_control.demo_views:camera_main",
            "decentralized_agent = swarm_sar_control.decentralized_agent:main",
            "peer_network_bridge = swarm_sar_control.peer_network_bridge:main",
            "survivor_oracle = swarm_sar_control.survivor_oracle:main",
        ]
    },
)
