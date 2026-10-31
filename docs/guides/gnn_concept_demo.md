# GNN concept demonstration

The observatory includes an explicitly illustrative graph view for explaining GNN message aggregation. It is a teaching aid, separate from actual transport telemetry and the experimental Python GNN-PPO checkpoint.

Open the browser mission observatory at `http://127.0.0.1:5173/?mode=observatory`, then choose **GNN concept**. The view is also available when the ROS observatory has agent telemetry, with the same illustration label; it is not a learned SLAM integration.

## Demonstration flow

1. **Build a local graph:** use the fleet labels to identify a receiver and up to eight example neighbors. Select another robot to rebuild the illustration around it.
2. **Pass messages:** directed arcs and gold markers illustrate feature messages arriving at the receiver. These are example edges, not reported radio deliveries.
3. **Weight and aggregate:** authored scores are normalized with softmax, including a self contribution. Change **Example score** to demonstrate how relative weights and line thickness change.
4. **Inform a decision:** show the conceptual aggregate → LSTM → PPO path. The illustration produces no robot commands or predicted actions.

Use **Next step** for a paced explanation or **Play illustration** to cycle the four steps. Illustration playback is independent of mission playback. Freeze visualization pauses it. Reduced-motion settings disable 3D message animation. On mobile, **Show explanation** expands the panel; the compact control panel leaves more room for the graph.

## Presentation wording

“This view illustrates how our receiver-local GNN can aggregate information from neighboring robots. These displayed weights are teaching examples. Our actual GNN-PPO implementation has been trained and evaluated separately; this browser view is not running that checkpoint.”

Do not describe example percentages as trained attention, measured trust, or causal contributions to the robot's decision. Do not present this as evidence of GNN improvement, deployed learned communication or collaborative SLAM. The GPU candidate's measured regression remains part of its separate evaluation record.

## Data boundaries

- Graph construction uses fleet IDs and UI-local example scores. It never mutates simulation state, controllers, packets, observations or weights.
- Actual peer links remain in **Peer network**. Actual packets remain in **Messages** and the telemetry export.
- No example edges or weights are inserted into the transport log or telemetry export.
- The graph includes illustrative peer connections, regardless of real radio connectivity. Its permanent **ILLUSTRATION · NOT LIVE INFERENCE** badge identifies that distinction.
- Neither this view nor the existing mission interface silently activates a GNN policy. Live checkpoint attention would require verified Python serving and decision-linked telemetry.

## Validation

The frontend suite passed **152 tests**, including example-graph normalization, receiver selection, bounded peer count and input immutability. TypeScript/Vite production build passed. Real Chrome checks verified nine behaviors, including unchanged mission fingerprint/step/command log and identical actual packet/metric exports before and after illustration interaction.

The existing observatory Chrome regression also passed 20 checks covering real browser missions, packet controls/export, navigation, graphics recovery, mobile layout and explicitly synthetic ROS/PPO UI contracts. Those contracts do not establish live ROS or GNN inference.

Evidence:

- [Concept browser verification](../../artifacts/gnn_concept_ui/verification.json)
- [Desktop illustration](../../artifacts/gnn_concept_ui/desktop-gnn-illustration.png)
- [Mobile illustration](../../artifacts/gnn_concept_ui/mobile-gnn-illustration.png)
- [Existing observatory regression](../../artifacts/gnn_concept_observatory_regression/validation.json)

To reproduce after starting Vite locally:

```bash
npm --prefix frontend test
npm --prefix frontend run build
.venv/bin/python frontend/tools/validate_gnn_concept.py --url http://127.0.0.1:5173
```

The browser checker accepts `--browser-executable` if an installed Chrome/Chromium executable is needed. No model training or sensor change is required for this teaching view.
