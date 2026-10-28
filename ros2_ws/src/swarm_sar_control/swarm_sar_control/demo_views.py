"""Live ROS scan/map views and Gazebo camera controls. No synthetic sensor data."""
import argparse
import math
import subprocess
import time
import tkinter as tk
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rosgraph_msgs.msg import Clock
from rclpy.qos import qos_profile_sensor_data


def camera(preset, robot="rover_0"):
    def gz(args):
        result = subprocess.run(["gz", *args], capture_output=True, text=True, timeout=8)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout.strip()
    if preset == "follow":
        return gz(["topic", "-t", "/gui/track", "-m", "gz.msgs.CameraTrack", "-p",
                   f'track_mode: FOLLOW follow_target {{name: "{robot}"}} follow_offset {{x: -5 y: 0 z: 3}} follow_pgain: 0.08'])
    gz(["topic", "-t", "/gui/track", "-m", "gz.msgs.CameraTrack", "-p", "track_mode: NONE"])
    x, y, z, pitch, yaw = {
        "top": (-1., -8., 32., 1.5707, 0.),
        "side": (-1., -26., 5., 0.12, 1.5708),
        "overview": (21., -32., 24., 0.63, 2.18),
    }[preset]
    cy, sy, cp, sp = math.cos(yaw/2), math.sin(yaw/2), math.cos(pitch/2), math.sin(pitch/2)
    request = "pose {position {x: %f y: %f z: %f} orientation {w: %f x: %f y: %f z: %f}} duration: 1" % (x, y, z, cy*cp, -sy*sp, cy*sp, sy*cp)
    return gz(["service", "-s", "/gui/move_to/pose", "--reqtype", "gz.msgs.GUICamera",
               "--reptype", "gz.msgs.Boolean", "--timeout", "5000", "--req", request])


def camera_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("preset", choices=["top", "side", "overview", "follow"])
    parser.add_argument("--robot", default="rover_0", choices=["rover_0", "drone_0", "drone_1"])
    args = parser.parse_args()
    print(camera(args.preset, args.robot))


def main():
    rclpy.init()
    node = rclpy.create_node("demo_sensor_views")
    root = tk.Tk()
    root.title("Swarm-SAR | Live rectangular occupancy map")
    root.geometry("1000x800")
    root.configure(bg="#101923")
    selected = tk.StringVar(value="rover_0")
    show_tracks = tk.BooleanVar(value=False)
    controls = tk.Frame(root)
    controls.pack(fill="x")
    tk.OptionMenu(controls, selected, "rover_0", "drone_0", "drone_1").pack(side="left")
    tk.Checkbutton(controls, text="Show vehicle trails", variable=show_tracks).pack(side="left")
    status = tk.StringVar(value="Waiting for live occupancy map")
    pool = ThreadPoolExecutor(max_workers=1)
    pending = []
    for preset in ("top", "side", "overview", "follow"):
        tk.Button(controls, text=f"Gazebo: {preset}",
                  command=lambda p=preset: pending.append(pool.submit(camera, p, selected.get()))).pack(side="left")
    tk.Label(root, textvariable=status, bg="#101923", fg="white").pack(fill="x")
    canvas = tk.Canvas(root, bg="#101923", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    maps, poses, traces, subscriptions = {}, {}, {}, []
    sim_time = [None]
    rendered = {"key": None, "image": None}
    colors = {"rover_0": "#e89a00", "drone_0": "#007eaa", "drone_1": "#9642c9"}

    def odom(robot, msg):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        poses[robot] = (p.x, p.y, p.z, yaw)
        traces.setdefault(robot, deque(maxlen=400)).append((p.x, p.y))

    def occupancy(robot, msg):
        if msg.info.width <= 0 or msg.info.height <= 0 or len(msg.data) != msg.info.width*msg.info.height:
            return
        if robot not in maps:
            node.get_logger().info(f"Displaying live /{robot}/private_map: {msg.info.width} x {msg.info.height} cells")
        maps[robot] = (msg, time.monotonic())

    def clock(msg):
        now = msg.clock.sec+msg.clock.nanosec*1e-9
        if sim_time[0] is not None and now < sim_time[0]:
            maps.clear()
            poses.clear()
            traces.clear()
            rendered["key"] = None
        sim_time[0] = now
    subscriptions.append(node.create_subscription(Clock, "/clock", clock, qos_profile_sensor_data))
    for robot in colors:
        subscriptions.append(node.create_subscription(OccupancyGrid, f"/{robot}/private_map",
                            lambda msg, r=robot: occupancy(r, msg), 1))
        subscriptions.append(node.create_subscription(Odometry, f"/{robot}/odom",
                            lambda msg, r=robot: odom(r, msg), qos_profile_sensor_data))

    def update():
        for _ in range(25):
            rclpy.spin_once(node, timeout_sec=0)
        for future in pending[:]:
            if future.done():
                try:
                    future.result()
                except Exception as error:
                    node.get_logger().warning(str(error))
                pending.remove(future)
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        robot = selected.get()
        if robot not in maps:
            status.set(f"Waiting for /{robot}/private_map — start the simulation")
            canvas.create_text(width/2, height/2, text="Waiting for live map data", fill="white", font=("Sans", 16))
            root.after(100, update)
            return
        grid, arrival = maps[robot]
        cols, rows = grid.info.width, grid.info.height
        zoom = max(1, int(min((width-110)/cols, (height-95)/rows)))
        key = (robot, grid.header.stamp.sec, grid.header.stamp.nanosec, zoom)
        if rendered["key"] != key:
            # Flip rows for north-up display. Unknown gray, free white, occupied dark.
            palette = [bytes((round(240-2.12*v),)*3) for v in range(101)]
            pixels = b"".join(
                bytes((112, 123, 136)) if value < 0 else palette[min(value, 100)]
                for row in range(rows-1, -1, -1)
                for value in grid.data[row*cols:(row+1)*cols]
            )
            ppm = f"P6\n{cols} {rows}\n255\n".encode()+pixels
            rendered["image"] = tk.PhotoImage(data=ppm, format="PPM").zoom(zoom)
            rendered["key"] = key
        image_width, image_height = cols*zoom, rows*zoom
        left, top = (width-image_width)/2, (height-image_height)/2
        resolution = grid.info.resolution
        origin = grid.info.origin.position
        scale = zoom/resolution
        def pixel(x, y):
            return left+(x-origin.x)*scale, top+image_height-(y-origin.y)*scale

        canvas.create_image(left, top, image=rendered["image"], anchor="nw")
        # Cartesian metre grid: no circular scan or radar rings.
        x0, x1 = origin.x, origin.x+cols*resolution
        y0, y1 = origin.y, origin.y+rows*resolution
        for x in range(math.ceil(x0/5)*5, math.floor(x1/5)*5+1, 5):
            px, _ = pixel(x, y0)
            canvas.create_line(px, top, px, top+image_height, fill="#a4b0b9", stipple="gray25")
            canvas.create_text(px, top+image_height+14, text=f"{x} m", fill="white", font=("Sans", 9))
        for y in range(math.ceil(y0/5)*5, math.floor(y1/5)*5+1, 5):
            _, py = pixel(x0, y)
            canvas.create_line(left, py, left+image_width, py, fill="#a4b0b9", stipple="gray25")
            canvas.create_text(left-8, py, text=f"{y} m", fill="white", anchor="e", font=("Sans", 9))
        for name, pose in poses.items():
            x, y, z, yaw = pose
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            if show_tracks.get() and len(traces[name]) > 1:
                points = [v for point in traces[name] for v in pixel(*point)]
                canvas.create_line(*points, fill=colors[name], width=2)
            px, py = pixel(x, y)
            canvas.create_polygon(px+10*math.cos(yaw), py-10*math.sin(yaw),
                                  px+7*math.cos(yaw+2.5), py-7*math.sin(yaw+2.5),
                                  px+7*math.cos(yaw-2.5), py-7*math.sin(yaw-2.5),
                                  fill=colors[name], outline="#101923")
            canvas.create_text(px+12, py-12, text=f"{name}  {z:.1f} m", fill=colors[name], anchor="w", font=("Sans", 10, "bold"))
        canvas.create_text(width/2, 16, text=f"{robot} occupancy map | North up | frame: {grid.header.frame_id}",
                           fill="white", font=("Sans", 12, "bold"))
        canvas.create_text(width/2, height-12, text="White: free space    Dark: obstacles    Gray: not observed",
                           fill="white", font=("Sans", 11))
        stale = time.monotonic()-arrival > 5
        status.set(f"Live /{robot}/private_map | {cols} × {rows} cells | {resolution:.2f} m/cell | " +
                   ("STALE — simulation may be paused" if stale else f"Simulation time {sim_time[0] or 0:.1f} s"))
        root.after(100, update)
    root.after(100, update)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.destroy()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        node.destroy_node()
        rclpy.try_shutdown()
