#!/usr/bin/env bash
set -u

release="$(lsb_release -rs 2>/dev/null || true)"
echo "Ubuntu: ${release:-unknown}"
echo "ROS_DISTRO: ${ROS_DISTRO:-unset}"
command -v ros2 >/dev/null && ros2 --help >/dev/null && echo "ros2: available" || echo "ros2: MISSING"
if command -v gz >/dev/null; then
  gz sim --version
elif command -v ign >/dev/null; then
  ign gazebo --version
elif command -v gazebo >/dev/null; then
  gazebo --version
else
  echo "Gazebo: MISSING"
fi
if command -v glxinfo >/dev/null; then
  glxinfo -B 2>/dev/null | grep -E "OpenGL vendor|OpenGL renderer" || echo "OpenGL renderer: unavailable"
else
  echo "glxinfo: MISSING (install mesa-utils)"
fi

case "$release" in
  24.04) echo "Supported profile: ROS 2 Jazzy + Gazebo Harmonic" ;;
  22.04) echo "Supported profile: ROS 2 Humble + Gazebo Fortress" ;;
  26.04)
    if [ "${ROS_DISTRO:-}" = "lyrical" ]; then
      echo "Supported profile: ROS 2 Lyrical + Gazebo Sim 10"
    else
      echo "Ubuntu 26.04 detected; source /opt/ros/lyrical/setup.bash first."
      exit 2
    fi
    ;;
  *)
    echo "UNSUPPORTED native binary profile. Use an Ubuntu 24.04 VM for this workspace."
    exit 2
    ;;
esac
