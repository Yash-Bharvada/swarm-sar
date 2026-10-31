export interface ObservatoryTourStep {
  id: string;
  title: string;
  story: string;
  built: string;
  tryIt: string;
  target: 'sources' | 'connection' | 'map' | 'agent' | 'layers' | 'network' | 'messages' | 'gnn' | 'playback' | 'evidence';
  view?: 'spatial' | 'neural' | 'concept';
  agent?: boolean;
  conceptStep?: number;
  evidence?: boolean;
}

export function observatoryTour(source: 'browser' | 'ros'): ObservatoryTourStep[] {
  const ros = source === 'ros';
  return [
    {
      id: 'workspace', title: ros ? 'From robot messages to a living map.' : 'Open the team’s notebook.', target: 'sources',
      story: ros ? 'This is our ROS / SLAM workspace. A bridge brings information from the robot system into this page, so we can see what each helper knows.' : 'The rescue world shows what happens. This observatory helps explain how it happens: each robot’s map, its journey, and the messages between teammates.',
      built: 'We built two connected viewing workflows: Browser mission and ROS / SLAM, with a shared 3D map, network view, and robot inspector.',
      tryIt: ros ? 'Follow the tour even without a connected host. Original project captures are included.' : 'Use Launch mission below for moving robots, or inspect the current mission at your own pace.',
    },
    ...(ros ? [{
      id: 'connection', title: 'Give the robot system a window.', target: 'connection' as const,
      story: 'ROS 2 is the message system inside our robot project. The bridge is like a window: it lets the website listen to maps, robot positions, and messages from the running ROS host.',
      built: 'We implemented bridge connection tools, incoming-data checks, and freshness indicators. Old information is visibly marked as stale.',
      tryIt: 'Open Connect ROS to enter the address of your running bridge. The tour never connects or sends robot commands automatically.',
    }] : []),
    {
      id: 'map', title: ros ? 'Draw the map while finding your place.' : 'A map of what this robot knows.', target: 'map', view: 'spatial', agent: true,
      story: ros ? 'Picture walking through an unknown house with a torch and a notebook. You sketch the walls while working out where you are. That is the SLAM puzzle. This view displays the rover’s reported map.' : 'Imagine each friend carrying a separate notebook. A robot only fills in places it has seen or learned about. Blank space means “I don’t know yet,” even when you can see the whole rescue world.',
      built: ros ? 'Our ROS source connects separate rover SLAM maps, position feedback, map alignment, and the 3D occupancy-map viewer.' : 'We built private knowledge for every robot and a 3D view of its observed cells, rather than handing every robot the whole map.',
      tryIt: 'Choose another robot on the left. Notice whose notebook you are looking at.',
    },
    {
      id: 'agent', title: 'Meet the mind behind the marker.', target: 'agent', view: 'spatial', agent: true,
      story: 'A moving dot cannot tell the whole story. Open its little report to see its energy, goal, current job, and how much ground it knows.',
      built: ros ? 'The inspector separates rover SLAM estimates from drone simulator poses, and reports cells learned from peers.' : 'The inspector connects each robot’s map, goal, battery, and decision state to the running browser or Python-policy mission.',
      tryIt: 'Select a rover, then a drone. Different helpers bring different knowledge and abilities.',
    },
    {
      id: 'routes', title: 'A trail behind. Possibilities ahead.', target: 'layers', view: 'spatial', agent: true,
      story: 'A trail helps us see where a robot has travelled. A frontier is the edge of the known world: a place where the robot might look next. Think of the next unopened door in our house.',
      built: 'We added paths, frontier markers, map layers, top-down viewing, and zoom tools so exploration can be inspected from several angles.',
      tryIt: 'Try Paths and Frontiers in Layers. Markers appear when the source has reported that information.',
    },
    ...(ros ? [{
      id: 'shared-map', title: 'Your discovery can help my search.', target: 'agent' as const, view: 'spatial' as const, agent: true,
      story: 'One robot notices a hallway. It sends that discovery to a teammate. The teammate can add the delivered clue to its own notebook, even before visiting that hallway.',
      built: 'We added private rover maps, known-start alignment, radio-delivered map snapshots, and a peer-only map layer. The inspector counts cells learned from teammates.',
      tryIt: 'Compare Known cells with Peer-only cells. A message must arrive and be accepted before it can help.',
    }] : []),
    {
      id: 'network', title: 'Watch the walkie-talkie friendships.', target: 'network', view: 'neural',
      story: 'Switch from places to connections. Each point is a teammate. A line shows a communication link. Moving messages help explain how discoveries travel through the team.',
      built: 'Our peer-network view renders actual reported transport links and packet events, including healthy, weak, and unavailable connections.',
      tryIt: 'Follow a moving packet, then open Messages to find its delivery record.',
    },
    {
      id: 'messages', title: 'Did the little note arrive?', target: 'messages', view: 'neural',
      story: 'Sending a note is only half the job. It might arrive late, be lost, or be too old to use. This list lets us follow what really happened to each message.',
      built: 'We built a searchable-by-status packet stream with sender, receiver, payload, timestamps, and telemetry export. Selecting a robot narrows the list to its traffic.',
      tryIt: 'Filter Delivered / applied or Dropped. Export telemetry to keep a record of the mission.',
    },
    ...(ros ? [{
      id: 'isolation', title: 'What if one walkie-talkie goes quiet?', target: 'agent' as const, view: 'spatial' as const, agent: true,
      story: 'If a teammate loses contact, the others still have their own eyes and notebooks. An isolation experiment helps us see how the team behaves when a radio is unavailable.',
      built: 'The ROS inspector can request radio isolation or reconnection, wait for acknowledgement, and display the status actually reported by ROS.',
      tryIt: 'On a fresh connection, the selected robot has an Isolate radio control. Use it only when you want to change that running experiment.',
    }] : []),
    {
      id: 'gnn-graph', title: 'Give the team’s relationships a shape.', target: 'gnn', view: 'concept', agent: true, conceptStep: 0,
      story: 'Choose one robot. Put it and its teammates into a little web. The points represent helpers; the connections say whose information can be considered together.',
      built: 'We implemented an interactive GNN architecture view using mission robot labels, selectable receivers, and four visible processing stages.',
      tryIt: 'Select another robot. The receiver at the centre of the explanation changes.',
    },
    {
      id: 'gnn-messages', title: 'Turn observations into useful clues.', target: 'gnn', view: 'concept', agent: true, conceptStep: 1,
      story: 'A teammate’s position, energy, or discovery can become a little bundle of information. In a graph model, these bundles travel along connections toward the robot making a decision.',
      built: 'The graph animation makes message passing visible, alongside the separate peer-network view for actual radio traffic.',
      tryIt: 'Watch the incoming graph messages. The architecture animation uses example connections and scores.',
    },
    {
      id: 'gnn-attention', title: 'Some clues deserve more attention.', target: 'gnn', view: 'concept', agent: true, conceptStep: 2,
      story: 'A nearby warm room may matter more than a distant empty hallway. Attention is a way to give clues different weights before combining them. Like listening more closely to the friend with the most useful clue.',
      built: 'We built adjustable scores and calculated attention weights, so you can see exactly how changing a score changes the combined information.',
      tryIt: 'Move Example message score. Watch the percentages change; these are calculated example weights.',
    },
    {
      id: 'gnn-decision', title: 'Connect understanding to a next step.', target: 'gnn', view: 'concept', agent: true, conceptStep: 3,
      story: 'Once the clues are combined, a robot policy can use that summary to help choose where to go. GNN is the relationship tool; PPO is the learning method. They answer different parts of the puzzle.',
      built: 'The project includes a GNN–PPO experimental training path and CPU checks, alongside the selected recurrent PPO policy and the working graph explainer.',
      tryIt: 'Use the four graph stages to follow the whole path. The active controller remains the selected browser or PPO policy.',
    },
    {
      id: 'playback', title: 'Pause the view. Inspect the story.', target: 'playback', view: 'spatial',
      story: 'Sometimes events move too quickly to understand. Freeze the picture to inspect it, turn the camera, or add a map layer. Freezing this viewer leaves the underlying mission alone.',
      built: 'We separated visualization freeze from mission playback, with camera controls, layers, and clear stale-data indicators.',
      tryIt: 'The view is frozen for this scene. Use Resume visualization to compare it with the continuing mission.',
    },
    {
      id: 'evidence', title: 'The engineering behind every view.', target: 'evidence', evidence: true,
      story: 'The project goes beyond a moving picture: robot models, sensors, ROS packages, private maps, radio delivery, policy training, and tools for checking results all support these views.',
      built: 'Our original Ubuntu / Gazebo / RViz captures document the physics workflow. The new SLAM source integration is implemented; live Linux validation remains the next check.',
      tryIt: ros ? 'Open an original capture below, then return to your connected workspace.' : 'Open the ROS / SLAM tour next to see that side of the project, too.',
    },
  ];
}
