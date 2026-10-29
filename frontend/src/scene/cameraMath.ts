import * as THREE from 'three';

/** A level, north-up angled view: world X always stays horizontal on screen. */
export function overviewOffset(span: number, target = new THREE.Vector3()): THREE.Vector3 {
  return target.set(0, span * 3.3, span * 1.95);
}

export interface GroundZoomAnchor {
  ndc: THREE.Vector2;
  point: THREE.Vector3;
}

const ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const raycaster = new THREE.Raycaster();
const after = new THREE.Vector3();
const shift = new THREE.Vector3();

export function captureGroundAnchor(camera: THREE.OrthographicCamera, ndc: THREE.Vector2): GroundZoomAnchor | null {
  camera.updateMatrixWorld();
  raycaster.setFromCamera(ndc, camera);
  const point = raycaster.ray.intersectPlane(ground, new THREE.Vector3());
  return point ? { ndc: ndc.clone(), point } : null;
}

/** Keep the original ground point under the same cursor throughout an animated zoom. */
export function applyAnchoredZoom(camera: THREE.OrthographicCamera, target: THREE.Vector3, zoom: number, anchor: GroundZoomAnchor | null): void {
  camera.zoom = zoom;
  camera.updateProjectionMatrix();
  if (!anchor) return;
  camera.updateMatrixWorld();
  raycaster.setFromCamera(anchor.ndc, camera);
  if (!raycaster.ray.intersectPlane(ground, after)) return;
  shift.copy(anchor.point).sub(after);
  camera.position.add(shift);
  target.add(shift);
  camera.updateMatrixWorld();
}

/** Normalize mouse wheels, line scrolling and trackpads to bounded zoom intent. */
export function wheelZoom(current: number, delta: number, mode: number, height: number, min: number, max: number): number {
  const pixels = delta * (mode === 1 ? 16 : mode === 2 ? height : 1);
  const bounded = THREE.MathUtils.clamp(Number.isFinite(pixels) ? pixels : 0, -240, 240);
  return THREE.MathUtils.clamp(current * Math.exp(-bounded * 0.0018), min, max);
}

/** Multiplicative interpolation gives the same perceived speed at every scale. */
export function smoothZoom(current: number, destination: number, dt: number): number {
  const factor = 1 - Math.exp(-Math.min(Math.max(dt, 0), 0.05) * 12);
  return Math.exp(THREE.MathUtils.lerp(Math.log(current), Math.log(destination), factor));
}
