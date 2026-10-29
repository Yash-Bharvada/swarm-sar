import * as THREE from 'three';
import { applyAnchoredZoom, captureGroundAnchor, overviewOffset } from '../scene/cameraMath';

function view(topDown = false) {
  const camera = new THREE.OrthographicCamera(-640, 640, 400, -400, 0.1, 1000);
  camera.position.copy(topDown ? new THREE.Vector3(0, 180, 0.6) : overviewOffset(45));
  camera.lookAt(0, 0, 0);
  camera.zoom = 14;
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
  return camera;
}

describe('Camera framing and cursor zoom', () => {
  it('keeps the overview map level rather than rotated diagonally', () => {
    const camera = view();
    const left = new THREE.Vector3(-12, 0, 0).project(camera);
    const right = new THREE.Vector3(12, 0, 0).project(camera);
    expect(left.y).toBeCloseTo(right.y, 10);
    expect(left.x).toBeLessThan(right.x);
  });

  it.each([false, true])('keeps a chosen ground point under the cursor during both zoom directions (top-down: %s)', (topDown) => {
    const camera = view(topDown);
    const target = new THREE.Vector3();
    const cursor = new THREE.Vector2(0.57, -0.24);
    const anchor = captureGroundAnchor(camera, cursor)!;
    expect(anchor).not.toBeNull();
    for (const zoom of [16, 20, 30, 22, 14, 10]) {
      applyAnchoredZoom(camera, target, zoom, anchor);
      const screen = anchor.point.clone().project(camera);
      expect(screen.x).toBeCloseTo(cursor.x, 8);
      expect(screen.y).toBeCloseTo(cursor.y, 8);
      expect(target.y).toBeCloseTo(0, 8);
    }
  });

  it('returns to the same framing when zooming in and back out at a fixed cursor', () => {
    const camera = view();
    const target = new THREE.Vector3();
    const original = camera.position.clone();
    const anchor = captureGroundAnchor(camera, new THREE.Vector2(-0.63, 0.38));
    applyAnchoredZoom(camera, target, 35, anchor);
    applyAnchoredZoom(camera, target, 14, anchor);
    expect(camera.position.distanceTo(original)).toBeLessThan(1e-8);
    expect(target.length()).toBeLessThan(1e-8);
  });

  it('preserves the camera position when no cursor has been placed in the world', () => {
    const camera = view();
    const original = camera.position.clone();
    const target = new THREE.Vector3();
    applyAnchoredZoom(camera, target, 20, null);
    expect(camera.zoom).toBe(20);
    expect(camera.position.equals(original)).toBe(true);
    expect(target.length()).toBe(0);
  });
});
