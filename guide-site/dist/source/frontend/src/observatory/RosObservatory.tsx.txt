import { useRosObservatory } from './useObservatory';
import { ObservatoryPage } from './ObservatoryPage';

export function RosObservatory() {
  const ros = useRosObservatory();
  return <ObservatoryPage snapshot={ros.snapshot} connection={ros.connection} onConnect={ros.connect} onDisconnect={ros.disconnect} onIsolate={ros.isolate} isolated={ros.isolated} radioStatusFresh={ros.radioStatusFresh} onBack={() => { window.location.href = '/'; }} />;
}
