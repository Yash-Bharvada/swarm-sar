#!/usr/bin/env python3
"""Generate an honest validation report from saved observations and original PNGs."""
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Preformatted
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVuBold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/2026-10-28"
OUTPUT = ROOT / "docs/reports/engineering_validation_report.pdf"
styles = getSampleStyleSheet()
styles.add(ParagraphStyle("Cover", fontSize=25, leading=32, textColor=colors.HexColor("#17324d"), spaceAfter=22))
styles.add(ParagraphStyle("Note", fontSize=10, leading=15, spaceAfter=10))
styles["Heading1"].textColor = colors.HexColor("#17324d")
styles["BodyText"].leading = 15
for name in ("Note", "BodyText", "Normal"):
    styles[name].fontName = "DejaVu"
for name in ("Cover", "Heading1"):
    styles[name].fontName = "DejaVuBold"
story = []

def p(text, style="Note"):
    story.append(Paragraph(escape(text), styles[style]))

def title(text):
    p(text, "Heading1")

def footer(canvas, doc):
    canvas.setFont("DejaVu", 8)
    canvas.setFillColor(colors.HexColor("#536577"))
    canvas.drawString(42, 26, "SWARM-SAR  |  Engineering validation  |  28 October 2026")
    canvas.drawRightString(A4[0]-42, 26, str(doc.page))

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
p("ROS 2 & Gazebo Simulation", "Cover")
p("Engineering Validation and Demonstration Report", "Heading1")
p("Swarm-SAR | ubuntu_simulations")
p("Ubuntu 26.04.1 | ROS 2 Lyrical | Gazebo Sim 10.5.0")
p("Validation date: 28 October 2026")
screenshots = sorted((EVIDENCE / "screenshots").glob("*.png"))
p(f"Evidence status: {len(screenshots)} original PNG screenshots supplied; target is 10.")
p("This report separates observed results from implementation claims. It is not a competition-readiness certificate. Missing evidence and failed tests are retained explicitly.")
story.append(Spacer(1, 24))
title("Executive summary")
p("The existing four-package architecture was retained. Configurable robot scenarios, optional GUIs, reduced sensor workloads and filtered bridges make smaller demonstrations possible. Runtime testing found an OpenGL failure, missing IMU publication and double-applied drone spawn offsets; the latter two were corrected and retested.")
p("The first run failed in Ogre rendering. A software-rendered pair ran with real scans, camera images, odometry and peer traffic. The first software test lacked IMU data and showed incorrect drone altitude. See the corrected observations below for the final measured state.")
story.append(PageBreak())
title("Architecture and engineering changes")
p("Gazebo physics and sensor plugins -> ROS/Gazebo bridge -> each robot's decentralized agent. Agents publish velocity commands through the bridge back to Gazebo. The RF transport delivers peer state with range, loss and delay. The survivor oracle emits synthetic, noisy evidence. It is a simulation proxy, not a real thermal vision detector.")
p("Namespaces remain rover_0, rover_1, drone_0 and drone_1 to preserve compatibility. The pair scenario starts rover_0 and drone_0 simultaneously. Rover odometry is spawn-relative; drone odometry is world-relative. Map transforms and agent/radio/oracle offsets now reflect that distinction.")
p("Drone TF follows map -> drone_0/odom -> drone_0/base_footprint -> drone_0/base_link -> sensor_link. Three-dimensional drone odometry enables altitude feedback. The IMU world system now updates IMU sensors.")
p("Low-resource mode uses 180 LiDAR rays at 5 Hz and a 320 x 240 camera at 3 Hz; full sensor settings are selectable. RViz is disabled by default. Headless mode retains rendering for GPU LiDAR/camera sensors, so it still needs a usable EGL/OpenGL implementation.")
story.append(PageBreak())
title("Validation results")
p("Build: all four packages passed. Existing checks: five static integration tests and three helper tests passed. Xacro expansion confirmed 720 rays/10 Hz versus 180 rays/5 Hz for the rover.")
p("Initial headless launch: FAIL (OpenGL context failure). First software pair: PARTIAL (sensors and movement observed, IMU missing, drone offset bug). Shutdown of that bounded run required SIGKILL after its grace period: FAIL for clean shutdown.")
p("Corrected GUI shutdown: all ROS nodes exited cleanly after terminal Ctrl+C. Gazebo exited with signal code -2 without forced kill. This is successful interruption, but Gazebo still reports a nonzero exit.")
probe = EVIDENCE / "logs/pair-corrected-probe.json"
data = json.loads(probe.read_text()) if probe.exists() and probe.stat().st_size else {}
if data:
    p("Corrected live pair: missing requested streams = " + str(data["missing"]))
    for topic, count in data["counts"].items():
        p(f"{topic}: {count} messages in {data['wall_seconds']:.1f} wall seconds.")
    for topic, poses in data["positions"].items():
        p(f"{topic}: first {[round(v, 3) for v in poses['first']]}; last {[round(v, 3) for v in poses['last']]}.")
else:
    p("Corrected live probe: PENDING. Do not infer success from source edits.")
story.append(PageBreak())
title("Reproducibility")
commands = """cd /home/yash/Desktop/swarm-sar/ros2_ws
source /opt/ros/lyrical/setup.bash
colcon build --symlink-install
source install/setup.bash
LIBGL_ALWAYS_SOFTWARE=1 ros2 launch swarm_sar_gazebo \\
  swarm_sar_sim.launch.py scenario:=pair
"""
story.append(Preformatted(commands, styles["Code"]))
p("For one rover use scenario:=rover; one drone: scenario:=drone; four robots: scenario:=full. Add headless:=true for server-only operation, rviz:=true to show RViz, and low_resource:=false for full sensor settings. Four-robot operation was not revalidated during this audit.")
p("From the repository root in another sourced terminal: python3 simulation/scripts/ros2_runtime_probe.py --seconds 30. For a single robot pass --agents rover_0 or --agents drone_0. Peer traffic is checked only for multi-robot runs.")
p("Stop with Ctrl+C in the launch terminal. Do not overlap launches. The raw failed and successful observations are preserved under docs/evidence/2026-10-28/logs. Dependencies are declared in package.xml; resolve with rosdep before building on a fresh machine.")
title("Limitations and future work")
p("The drone uses a body velocity controller rather than rotor aerodynamics. Mapping uses odometry and approximates sensor offsets; the reactive obstacle barrier does not guarantee collision avoidance. Initial rover ground contact, wheel TF, long-duration coverage, survivor recovery and command-step response need further tests. Synthetic health/battery values are not hardware diagnostics.")
p("The VM has 7.3 GiB RAM and no swap. GNOME denied direct screenshot capture; the user offered manual capture. Ten original screenshots remain a required deliverable until supplied. No screenshots, terminal displays or simulation results have been fabricated.")
p("Official graphics troubleshooting reference: https://gazebosim.org/docs/latest/troubleshooting/")
story.append(PageBreak())
title("Screenshot evidence register")
captions = ["World overview", "Robot model detail", "ROS runtime nodes", "Topics and sensor readings", "ROS/Gazebo bridge", "Robot movement", "Drone operation", "Simultaneous multi-robot scene", "TF and diagnostics", "Final demonstration scene"]
for i, caption in enumerate(captions, 1):
    p(f"{i:02d}. {caption}: " + ("awaiting manual capture and review" if not screenshots else "see supplied originals; captions require review against actual content"))
for path in screenshots:
    story.append(PageBreak())
    title(path.stem)
    image = Image(str(path))
    scale = min(510/image.imageWidth, 570/image.imageHeight)
    image.drawWidth = image.imageWidth*scale
    image.drawHeight = image.imageHeight*scale
    story.append(image)
    p("Original supplied capture. No compositing or image alteration applied.")
    p("SHA-256: " + hashlib.sha256(path.read_bytes()).hexdigest())
p("Conclusion: source and configuration improvements are implemented and supported by bounded runtime observations. Complete acceptance requires the remaining genuine screenshots and unresolved validation gates.")
SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42).build(story, onFirstPage=footer, onLaterPages=footer)
print(OUTPUT)
