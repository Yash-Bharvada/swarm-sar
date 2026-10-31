import { create } from 'zustand';
import type { ConceptKind } from './ConceptVisual';

export type StoryCue = 'problem' | 'rover' | 'drone' | 'world' | 'ros' | 'gazebo' | 'rviz' | 'slam' | 'learning' | 'cooperation' | 'communication' | 'gnn' | 'proof' | 'system';
export interface StoryBeat {
  chapter: number;
  chapterName: string;
  cue: StoryCue;
  eyebrow: string;
  title: string;
  story: string;
  takeaway: string;
  technology: string;
  built: string;
  technical: string;
  sceneCaption: string;
  visual?: ConceptKind;
}

export const STORY: StoryBeat[] = [
  {
    chapter: 1, chapterName: 'The problem', cue: 'problem', eyebrow: 'EVERY RESCUE STARTS WITH A QUESTION',
    title: 'What if help could go first?',
    story: 'A building is damaged. Someone inside needs help. The hallways are unfamiliar, and sending people in can be dangerous. Imagine a small team of robots going ahead to look for signs of life.',
    takeaway: 'Our mission: find people, share clues, and help rescuers know where to look.',
    technology: 'Search-and-rescue robotics',
    built: 'We built an interactive rescue world where different robots search with limited sight, energy, and radio contact.',
    technical: 'The simulator models obstacles, noisy heat and sound clues, local maps, battery use, and delayed or lost messages. Finding someone means confirming their location; physical evacuation is a future task.',
    sceneCaption: 'The amber beacons show you where people are. The robots must discover them with their sensors.',
  },
  {
    chapter: 2, chapterName: 'Meet the team', cue: 'rover', eyebrow: 'MEET OUR GROUND EXPLORER',
    title: 'Little wheels. A careful search.',
    story: 'Meet the rover. It rolls through open paths, looks around, and checks clues nearby. Think of a careful detective: a warm spot or a faint sound is a reason to look closer, not a reason to guess.',
    takeaway: 'Eyes, heat, and sound help the rover build its own picture of the world.',
    technology: 'Rover · sensing and battery',
    built: 'We gave the rover its own sensor readings, private map, energy budget, safe movement, and detailed 3D model.',
    technical: 'Browser rover ranges: vision 4, thermal 6, acoustic 10 map cells. Starting battery: 300 simulated energy units. These are simulation settings, not hardware specifications. Solid walls block movement.',
    sceneCaption: 'The ring highlights our rover. The dotted circle shows its simulated vision range.',
  },
  {
    chapter: 2, chapterName: 'Meet the team', cue: 'drone', eyebrow: 'MEET OUR WIDER-LOOKING SCOUT',
    title: 'A different view helps the team.',
    story: 'Now meet the drone. It can spot clues over a wider area. Like friends with different talents, rover and drone bring different strengths. The drone also has less energy, so every trip needs to count.',
    takeaway: 'Different abilities make a useful team. Every helper still has limits.',
    technology: 'Drone · wider sensing',
    built: 'We built a separate drone model and sensing profile, with animated rotors, its own knowledge, and a smaller battery.',
    technical: 'Browser drone ranges: vision 7, thermal 8, acoustic 12 map cells. Battery: 240 simulated units. The browser uses grid movement with visual altitude; the separate Gazebo demo supplies physical robot models.',
    sceneCaption: 'Compare the drone’s wider view with the rover’s. Both must search for clues.',
  },
  {
    chapter: 3, chapterName: 'The virtual world', cue: 'world', eyebrow: 'A PLACE TO PRACTICE',
    title: 'Big ideas need a little world.',
    story: 'Before asking a robot to help in a real emergency, give it a practice world. Here, the team can explore, get stuck, try another route, and discover people. You can turn the world around and watch each helper work.',
    takeaway: 'Drag to look around. Tap a robot to see whose journey you are following.',
    technology: 'Our interactive 3D frontend',
    built: 'This is our existing animated website: editable worlds, moving robots, cameras, fleet details, survivor discoveries, and live communication.',
    technical: 'React and Three.js display a deterministic browser simulation. Optional Python PPO mode renders an authoritative saved-policy mission through a service. The guided sandbox uses the browser controller, so it runs without starting Python or ROS.',
    sceneCaption: 'Live browser simulation · Your original mission is safely kept while this story runs.',
  },
  {
    chapter: 4, chapterName: 'Understanding the world', cue: 'ros', eyebrow: 'FIRST, GIVE EVERY PART A VOICE',
    title: 'A robot needs a team inside it, too.',
    story: 'Imagine a little school. One friend watches the door, another draws a map, and another decides where to walk. They need a way to pass notes. Inside a robot, its sensors, map maker, and movement tools need the same thing.',
    takeaway: 'ROS 2 is the shared language that lets robot parts exchange useful messages.',
    technology: 'ROS 2 · the robot’s message system',
    built: 'We created ROS 2 packages, robot messages, launch tools, and a bridge for inspecting robot telemetry in the website.',
    technical: 'ROS 2 connects sensor, mapping, and control processes through typed messages. The browser simulation is a separate execution path. The ROS observatory reads a connected ROS host rather than pretending the browser is running ROS.',
    sceneCaption: 'A simple message journey: sensors → map maker → movement. The browser world remains our visual guide.',
  },
  {
    chapter: 4, chapterName: 'Understanding the world', cue: 'gazebo', eyebrow: 'THEN, BUILD A PHYSICS PLAYGROUND',
    title: 'A dress rehearsal for robots.',
    story: 'A toy car on a drawing is useful. A toy car that has weight, wheels, and things to bump into teaches us more. Our robot project also has a practice world with physics, where robot bodies and sensors can be tested together.',
    takeaway: 'Gazebo is the physics playground. This photograph is a real capture of our simulator running.',
    technology: 'Gazebo · simulated bodies and sensors',
    built: 'We modeled the rover and drones, assembled a disaster site, and built launch and readiness checks for the physics demo.',
    technical: 'The checked-in physics demo launches one rover and two drones with waypoint controllers. The original host capture records a separate supplied run. It is supporting simulation evidence; the web browser does not run Gazebo.',
    sceneCaption: 'Original Gazebo capture · Ubuntu host session · 29 October 2026 UTC · 1 rover + 2 drones.',
  },
  {
    chapter: 4, chapterName: 'Understanding the world', cue: 'rviz', eyebrow: 'LOOK THROUGH THE ROBOT’S EYES',
    title: 'What does the robot actually know?',
    story: 'You can see the whole little world. A robot cannot. Imagine opening its notebook: you would see the paths it has noticed, its current position, and clues from its sensors. A special viewer helps us open that notebook.',
    takeaway: 'RViz is our window into robot data. Watch the map fill in across real recorded captures.',
    technology: 'RViz · the robot-data viewer',
    built: 'We connected robot positions, sensor information, and map views so the team’s progress can be inspected, not just imagined.',
    technical: 'RViz displays ROS data such as transforms, scans, and occupancy maps. The image sequence is recorded evidence from one host session. It is not a live connection or proof of the newer SLAM integration.',
    sceneCaption: 'Original RViz captures · Move the slider to compare earlier and later map states.',
  },
  {
    chapter: 4, chapterName: 'Understanding the world', cue: 'slam', eyebrow: 'FIND YOUR WAY WHILE DRAWING THE MAP',
    title: 'An unknown house. A growing map.',
    story: 'Imagine walking through an unknown house in the dark with a little torch. As you move, you sketch the walls and remember where you have been. The tricky part? Working out where you are while you are still drawing the map!',
    takeaway: 'SLAM solves those two puzzles together: “Where am I?” and “What is around me?”',
    technology: 'SLAM · Simultaneous Localization and Mapping',
    built: 'We added separate rover map makers, estimated position feedback, map alignment, and radio-delivered map sharing in the ROS source.',
    technical: 'The ROS integration uses slam_toolbox and private occupancy maps. Source and protocol checks pass; live Linux validation and demonstrated loop closure remain ahead. The browser map is a simplified sensing model, not live SLAM.',
    sceneCaption: 'The green tiles show sensed ground. The little house game explains the SLAM idea.', visual: 'slam',
  },
  {
    chapter: 5, chapterName: 'How they learn', cue: 'learning', eyebrow: 'TRY. GET FEEDBACK. IMPROVE.',
    title: 'Practice makes a better explorer.',
    story: 'Think of learning a maze game. Finding a new path or a person earns a reward. Wasting a turn does not help. After lots of practice, helpful choices become more likely. Our learning method changes its habits a little at a time.',
    takeaway: 'Reinforcement learning learns from feedback. PPO keeps each change small and steady.',
    technology: 'PPO · Proximal Policy Optimization',
    built: 'We built expert demonstrations, a learning pipeline, saved policies, evaluation gates, and a Python service that runs the selected checkpoint.',
    technical: 'The selected recurrent PPO checkpoint reached 753,664 training steps. Its training reward includes +50 for confirming a survivor and +0.02 for a newly seen cell. The game below uses simpler example points; it does not train or run that model.',
    sceneCaption: 'Teaching game beside the existing robots · Actual trained-policy results appear in the proof chapter.', visual: 'learning',
  },
  {
    chapter: 6, chapterName: 'Learning to cooperate', cue: 'cooperation', eyebrow: 'GOOD TEAMWORK IS A SKILL',
    title: 'Two helpers. More possibilities.',
    story: 'If every friend searches the same cupboard, the rest of the house stays unknown. A team does better when friends learn to cover different places and share what they find. Each robot still makes its own choice using what it knows.',
    takeaway: 'MARL means multiple helpers learning in a world where their choices affect one another.',
    technology: 'MARL · Multi-Agent Reinforcement Learning',
    built: 'Our training environment puts mixed rover–drone teams together, with shared policies by robot type and private observations for every robot.',
    technical: 'The recurrent rover and drone PPO policies train in a multi-agent environment. Delivered peer information can influence their local observations. The live browser sandbox uses our decentralized heuristic controller; the small game demonstrates the cooperation idea.',
    sceneCaption: 'Watch the robots spread out. Open routes and local clues shape their separate decisions.', visual: 'cooperation',
  },
  {
    chapter: 7, chapterName: 'Passing useful messages', cue: 'communication', eyebrow: 'NEIGHBORS HELP NEIGHBORS',
    title: '“I found a clue. Pass it on!”',
    story: 'Imagine friends exploring a big garden with little walkie-talkies. Nearby friends can swap clues. Someone far away might miss a message, but the others keep searching. Nobody needs one boss who knows everything.',
    takeaway: 'Decentralized communication lets robots share what reached them and keep working with their own knowledge.',
    technology: 'Peer-to-peer robot communication',
    built: 'We implemented actual message delivery, delay, loss, range limits, stale-message checks, map merging, and a radio log you can inspect.',
    technical: 'Local controllers only read their own sensors, private map, and delivered peer messages. The animated links and moving packets in the 3D scene reflect simulated transport. A missed message cannot magically update a robot’s map.',
    sceneCaption: 'Live radio links and packets · The little note game lets you try a disconnected teammate.', visual: 'communication',
  },
  {
    chapter: 8, chapterName: 'Thinking with teammates', cue: 'gnn', eyebrow: 'A LITTLE CLUE CAN CHANGE A DECISION',
    title: 'Connect the clues, not just the dots.',
    story: 'One friend notices warmth. Another finds a blocked hallway. Together, those clues say: “Try a different way to the warm room.” A robot can learn to combine information from connected teammates before choosing its next step.',
    takeaway: 'A GNN learns from relationships: who is connected, and what useful information they bring.',
    technology: 'GNN · Graph Neural Network',
    built: 'We implemented the graph view, message-passing stages, adjustable attention weights, and an experimental GNN–PPO training path with CPU checks.',
    technical: 'The architecture view uses mission robot labels and adjustable example scores to reveal how a GNN combines information. The GNN training path is experimental; the selected live PPO controller remains the recurrent baseline.',
    sceneCaption: 'Interactive GNN architecture · Combine the team’s clues and explore how relationships matter.', visual: 'gnn',
  },
  {
    chapter: 9, chapterName: 'The work behind the world', cue: 'proof', eyebrow: 'FROM A NICE IDEA TO RUNNING SOFTWARE',
    title: 'A lot of work. Real things to show.',
    story: 'The moving robots are only the part you can see. Underneath are robot models, sensor rules, separate maps, radio messages, practice runs, saved learning, and tools for checking what happened. Here is the evidence behind that work.',
    takeaway: 'Open a real capture. Inspect the training settings. See what runs, and what we are working toward.',
    technology: 'Built, trained, measured, and recorded',
    built: 'One project connects an animated frontend, a decentralized simulator, a trained-policy service, and a separate ROS 2 / Gazebo / RViz physics workflow.',
    technical: 'The gallery includes original host captures, browser screenshots, selected development evaluation, and reproducible settings. The different execution paths are labeled so every achievement has the right evidence behind it.',
    sceneCaption: 'Project evidence · Original captures and recorded development results.',
  },
  {
    chapter: 10, chapterName: 'The complete system', cue: 'system', eyebrow: 'SMALL PARTS. ONE SHARED PURPOSE.',
    title: 'Now you can read the whole story.',
    story: 'The robots sense a clue, grow their maps, choose where to go, and share what they know. Their teammates keep searching too. Practice helps the learned policies improve. Together, these ideas turn a confusing place into useful information for rescuers.',
    takeaway: 'Tap each part below and watch it appear in the 3D world. Then explore your own mission.',
    technology: 'Sense → map → decide → share → search',
    built: 'You have seen the working browser team, the training evidence, and the physical-simulation tools behind our rescue project.',
    technical: 'This final live scene uses the browser controller. Saved PPO inference runs through the optional Python service; ROS physics runs on a ROS host. SLAM validation and the experimental GNN extension are the next integration milestones.',
    sceneCaption: 'Live browser team · Select a system part to reveal its role.',
  },
];

export const useExplain = create<{ beat: number; systemPart: number; setBeat: (beat: number) => void; setSystemPart: (part: number) => void }>((set) => ({
  beat: 0, systemPart: 0,
  setBeat: (beat) => set({ beat: Math.max(0, Math.min(STORY.length - 1, beat)) }),
  setSystemPart: (systemPart) => set({ systemPart }),
}));
