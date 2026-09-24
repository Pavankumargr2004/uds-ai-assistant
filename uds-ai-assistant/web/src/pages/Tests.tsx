import { useEffect, useState } from 'react';
import { api, type TestCase } from '../api';
import { useProject, useToast } from '../context';

const STATUS_CLASS: Record<string, string> = {
  approved: 'badge-success',
  rejected: 'badge-danger',
  draft: 'badge-muted',
  changes_requested: 'badge-warning',
};

const CATEGORY_COLORS: Record<string, string> = {
  positive: 'badge-success',
  negative: 'badge-danger',
  security: 'badge-info',
  timing: 'badge-cyan',
  boundary: 'badge-warning',
  session: 'badge-info',
};

export default function TestsPage() {
  const { activeProject } = useProject();
  const { addToast } = useToast();
  const [tests, setTests] = useState<TestCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [requirement, setRequirement] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [selected, setSelected] = useState<TestCase | null>(null);
  const [reviewing, setReviewing] = useState(false);

  const loadTests = () => {
    if (!activeProject) return;
    setLoading(true);
    api.listTests(activeProject, filterStatus || undefined, filterCategory || undefined)
      .then(r => setTests(r.tests))
      .catch(e => addToast(e.message, 'error'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadTests(); }, [activeProject, filterStatus, filterCategory]);

  const handleGenerate = async () => {
    if (!activeProject) return;
    setGenerating(true);
    try {
      const r = await api.generate(activeProject, requirement || undefined);
      addToast(`Generated ${r.generated} test cases`, 'success');
      setRequirement('');
      loadTests();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setGenerating(false);
    }
  };

  const handleReview = async (id: string, decision: 'approved' | 'rejected') => {
    setReviewing(true);
    try {
      await api.reviewTest(activeProject, id, decision);
      addToast(`Test ${decision}`, decision === 'approved' ? 'success' : 'info');
      setSelected(null);
      loadTests();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setReviewing(false);
    }
  };

  if (!activeProject) return <div className="empty-state"><p>Select a project first.</p></div>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Test Cases</h1>
        <p className="page-subtitle">Generate, review, and manage UDS test cases</p>
      </div>

      {/* Generation panel */}
      <div className="card mb-6">
        <div className="card-title">Generate Tests</div>
        <div className="flex gap-3 items-center" style={{ flexWrap: 'wrap' }}>
          <input
            className="form-input"
            style={{ flex: 1, minWidth: '220px' }}
            placeholder="Optional: describe a requirement (e.g., 'test read DID 0xF190'). Leave blank for full suite."
            value={requirement}
            onChange={e => setRequirement(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleGenerate()}
          />
          <button className="btn btn-primary" onClick={handleGenerate} disabled={generating}>
            {generating ? <span className="spinner" /> : <span>⚡</span>}
            {requirement ? 'Generate from Requirement' : 'Generate Full Suite'}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 items-center" style={{ marginBottom: '16px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Filter:</span>
        <select className="form-select" style={{ width: 'auto' }} value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
          <option value="">All statuses</option>
          {['draft', 'approved', 'rejected', 'changes_requested'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="form-select" style={{ width: 'auto' }} value={filterCategory} onChange={e => setFilterCategory(e.target.value)}>
          <option value="">All categories</option>
          {['positive', 'negative', 'security', 'timing', 'boundary', 'session'].map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="text-muted" style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
          {tests.length} test{tests.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tests table */}
      {loading ? (
        <div className="empty-state"><span className="spinner spinner-lg" /></div>
      ) : tests.length === 0 ? (
        <div className="empty-state">
          <p>No tests yet. Upload an ECU profile and click "Generate Full Suite".</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Service</th>
                <th>Category</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tests.map(t => (
                <tr key={t.id}>
                  <td className="td-mono">{t.id.slice(0, 8)}</td>
                  <td>
                    <div style={{ fontWeight: 500 }}>{t.name}</div>
                    {t.description && <div className="td-dim" style={{ fontSize: '0.75rem', marginTop: '2px' }}>{t.description.slice(0, 80)}{t.description.length > 80 ? '…' : ''}</div>}
                  </td>
                  <td><span className="hex-frame">0x{t.service.toString(16).toUpperCase().padStart(2, '0')}</span></td>
                  <td><span className={`badge ${CATEGORY_COLORS[t.category] ?? 'badge-muted'}`}>{t.category}</span></td>
                  <td><span className={`badge ${STATUS_CLASS[t.status] ?? 'badge-muted'}`}>{t.status}</span></td>
                  <td>
                    <button className="btn btn-sm" onClick={() => setSelected(t)}>Details</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail modal */}
      {selected && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setSelected(null)}>
          <div className="modal" style={{ maxWidth: '680px' }}>
            <div className="flex justify-between items-center" style={{ marginBottom: '16px' }}>
              <div className="modal-title" style={{ marginBottom: 0 }}>{selected.name}</div>
              <span className={`badge ${STATUS_CLASS[selected.status] ?? 'badge-muted'}`}>{selected.status}</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
              {[
                ['ID', selected.id],
                ['Service', `0x${selected.service.toString(16).toUpperCase().padStart(2, '0')}`],
                ['Category', selected.category],
                ['Created By', selected.created_by ?? '—'],
                ['Requirement', selected.requirement_id ?? '—'],
                ['Origin', selected.origin ?? '—'],
              ].map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{k}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', color: 'var(--cyan)', marginTop: '2px' }}>{v}</div>
                </div>
              ))}
            </div>

            {selected.description && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '6px' }}>Description</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>{selected.description}</div>
              </div>
            )}

            {selected.request_frames && selected.request_frames.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '6px' }}>Request Frames</div>
                <div className="code-block">{selected.request_frames.join('\n')}</div>
              </div>
            )}

            {selected.expected_response && (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '6px' }}>Expected Response</div>
                <div className="code-block">{selected.expected_response}</div>
              </div>
            )}

            <div className="divider" />
            <div className="flex gap-2 justify-end">
              <button className="btn" onClick={() => setSelected(null)}>Close</button>
              {selected.status === 'draft' && (
                <>
                  <button className="btn btn-danger" disabled={reviewing} onClick={() => handleReview(selected.id, 'rejected')}>
                    {reviewing ? <span className="spinner" /> : null} Reject
                  </button>
                  <button className="btn btn-success" disabled={reviewing} onClick={() => handleReview(selected.id, 'approved')}>
                    {reviewing ? <span className="spinner" /> : null} Approve
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
