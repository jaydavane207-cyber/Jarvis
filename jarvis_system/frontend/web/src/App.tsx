import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { MainLayout } from './layouts/MainLayout';
import { Dashboard } from './pages/Dashboard';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="study" element={<div>Study Module Active</div>} />
          <Route path="productivity" element={<div>Productivity Module Active</div>} />
          <Route path="communication" element={<div>Communication Module Active</div>} />
          <Route path="agent" element={<div>Autonomous Agent Active</div>} />
          <Route path="cognitive" element={<div>Cognitive Engine Active</div>} />
          <Route path="analytics" element={<div>Analytics Active</div>} />
          <Route path="security" element={<div>Security Core Active</div>} />
          <Route path="twin" element={<div>Digital Twin Active</div>} />
          <Route path="neural" element={<div>Neural Interface Active</div>} />
          <Route path="arvr" element={<div>AR/VR Spatial Active</div>} />
          <Route path="web3" element={<div>Blockchain Agent Active</div>} />
          <Route path="iot" element={<div>IoT & India Ops Active</div>} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
