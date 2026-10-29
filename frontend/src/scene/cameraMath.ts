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
