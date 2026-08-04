import { useEffect, useState } from 'react';

export default function NetworkDiagnostic() {
  const [healthStatus, setHealthStatus] = useState<string>('Testing /api/health...');
  const [origin, setOrigin] = useState<string>('');

  useEffect(() => {
    setOrigin(window.location.origin);

    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => setHealthStatus(`CONNECTED: ${data.message || data.status || 'OK'}`))
      .catch((err) => {
        // Fallback to /health endpoint
        fetch('/health')
          .then((res) => res.json())
          .then((data) => setHealthStatus(`CONNECTED (/health): ${data.status || 'OK'}`))
          .catch(() => setHealthStatus(`FAILED: ${err.message}`));
      });
  }, []);

  return (
    <div style={{
      margin: '16px',
      padding: '16px',
      borderRadius: '8px',
      backgroundColor: '#0f172a',
      color: '#f8fafc',
      fontFamily: 'monospace',
      fontSize: '13px',
      border: '1px solid #3b82f6'
    }}>
      <h4 style={{ margin: '0 0 8px 0', color: '#38bdf8' }}>LAN Connection Diagnostic</h4>
      <div><strong>window.location.origin:</strong> {origin}</div>
      <div><strong>Target Endpoint:</strong> {origin}/api/health</div>
      <div>
        <strong>Backend Status:</strong>{' '}
        <span style={{ color: healthStatus.startsWith('CONNECTED') ? '#4ade80' : '#f87171' }}>
          {healthStatus}
        </span>
      </div>
    </div>
  );
}
