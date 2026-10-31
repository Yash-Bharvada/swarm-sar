import { Component, type ReactNode } from 'react';
import { Icon } from '../components/Icon';

/** A renderer failure must not take the live telemetry and mission controls down. */
export class SceneBoundary extends Component<{ children: ReactNode; onRetry: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <GraphicsUnavailable onRetry={this.props.onRetry} />;
  }
}

export function GraphicsUnavailable({ onRetry }: { onRetry?: () => void }) {
  return <section className="ob-graphics-unavailable" role="status">
    <Icon name="layers" size={28} />
    <h2>The 3D view needs a moment.</h2>
    <p>Check that hardware acceleration is enabled. Your mission controls and message stream remain available.</p>
    {onRetry && <button className="ob-primary" onClick={onRetry}><Icon name="reset" size={14} />Retry 3D view</button>}
  </section>;
}
