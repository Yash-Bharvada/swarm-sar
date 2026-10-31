import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import './styles/app.css';
import { RosObservatory } from './observatory/RosObservatory';

const liveRos = new URLSearchParams(window.location.search).get('mode') === 'ros';
const BrowserApp = lazy(() => import('./app/App').then(module => ({ default: module.App })));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={<p>Loading mission control…</p>}>
      {liveRos ? <RosObservatory /> : <BrowserApp />}
    </Suspense>
  </StrictMode>,
);
