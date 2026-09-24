import { useState } from 'react';
import { api } from '../api';
import { useProject, useToast } from '../context';

export default function ExportPage() {
  const { activeProject } = useProject();
  const { addToast } = useToast();
  const [approvedOnly, setApprovedOnly] = useState(false);
  const [validateReq, setValidateReq] = useState('');
  const [validateResult, setValidateResult] = useState<any>(null);
  const [validating, setValidating] = useState(false);

  const FORMATS = [
    { fmt: 'json', label: 'JSON', icon: '{}', desc: 'Machine-readable test suite' },
    { fmt: 'csv', label: 'CSV', icon: '⊞', desc: 'Spreadsheet-compatible format' },
    { fmt: 'md', label: 'Markdown', icon: '📝', desc: 'Human-readable report' },
    { fmt: 'python', label: 'Python', icon: '🐍', desc: 'pytest-compatible test script' },
    { fmt: 'cangen', label: 'CANgen', icon: '🔌', desc: 'CAN generator test sequences' },
  ];

  const handleValidate = async () => {
    if (!activeProject || !validateReq.trim()) return;
    setValidating(true);
    setValidateResult(null);
    try {
      const r = await api.validate(activeProject, validateReq.trim());
      setValidateResult(r);
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setValidating(false);
    }
  };

  if (!activeProject) return <div className="empty-state"><p>Select a project first.</p></div>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Export & Tools</h1>
        <p className="page-subtitle">Export test suites and validate UDS requests</p>
      </div>

      {/* Export cards */}
      <div className="card mb-6">
        <div className="card-title" style={{ marginBottom: '12px' }}>Export Test Suite</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <input type="checkbox" id="approvedOnly" checked={approvedOnly} onChange={e => setApprovedOnly(e.target.checked)}
            style={{ accentColor: 'var(--amber)', width: 16, height: 16, cursor: 'pointer' }} />
          <label htmlFor="approvedOnly" style={{ cursor: 'pointer', fontSize: '0.875rem' }}>
            Approved tests only
            {!approvedOnly && <span className="badge badge-warning" style={{ marginLeft: '8px', fontSize: '0.62rem' }}>includes drafts</span>}
          </label>
        </div>
        <div className="grid grid-3" style={{ gap: '12px' }}>
          {FORMATS.map(({ fmt, label, icon, desc }) => (
            <a
              key={fmt}
              href={api.exportUrl(activeProject, fmt, approvedOnly)}
              target="_blank"
              rel="noreferrer"
              className="card"
              style={{
                display: 'flex', flexDirection: 'column', gap: '8px',
                padding: '18px', textDecoration: 'none',
                transition: 'all var(--transition)', cursor: 'pointer',
              }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(245,158,11,0.5)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = '')}
            >
              <div style={{ fontSize: '1.5rem' }}>{icon}</div>
              <div style={{ fontWeight: 700 }}>{label}</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{desc}</div>
              <div style={{ fontSize: '0.72rem', fontFamily: 'var(--font-mono)', color: 'var(--amber)', marginTop: 'auto' }}>
                Download ↓
              </div>
            </a>
          ))}
        </div>
      </div>

      {/* Request validator */}
      <div className="card" style={{ maxWidth: 720 }}>
        <div className="card-title" style={{ marginBottom: '12px' }}>UDS Request Validator</div>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '16px', lineHeight: 1.6 }}>
          Validate a raw UDS request against the ECU profile (requires profile to be uploaded).
        </p>
        <div className="form-group">
          <label className="form-label">Request Hex</label>
          <input className="form-input" style={{ fontFamily: 'var(--font-mono)' }}
            placeholder="e.g., 22 F1 90" value={validateReq}
            onChange={e => setValidateReq(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleValidate()} />
        </div>
        <button className="btn btn-primary" onClick={handleValidate} disabled={validating || !validateReq.trim()}>
          {validating ? <span className="spinner" /> : null} Validate
        </button>

        {validateResult && (
          <div style={{ marginTop: '16px' }}>
            <div className="divider" />
            <div className="code-block">{JSON.stringify(validateResult, null, 2)}</div>
          </div>
        )}
      </div>
    </div>
  );
}
