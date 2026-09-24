import { useEffect, useState } from 'react';
import { api, type RunResult, type RunResultItem, type TestCase } from '../api';
import { useProject, useToast } from '../context';

const VERDICT_BADGE: Record<string, string> = {
  pass: 'badge-success',
  fail: 'badge-danger',
  error: 'badge-danger',
  skip: 'badge-muted',
};

export default function RunnerPage() {
  const { activeProject } = useProject();
  const { addToast } = useToast();
  const [tests, setTests] = useState<TestCase[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [includeDraft, setIncludeDraft] = useState(true);
  const [faultInput, setFaultInput] = useState('');
  const [expandedTest, setExpandedTest] = useState<string | null>(null);

  useEffect(() => {
    if (!activeProject) return;
    api.listTests(activeProject).then(r => setTests(r.tests)).catch(() => {});
    api.listRuns(activeProject).then(r => setRuns(r.runs as any[])).catch(() => {});
  }, [activeProject]);

  const approvedTests = tests.filter(t => t.status === 'approved');

  const handleRun = async () => {
    if (!activeProject) return;
    setRunning(true);
    setResult(null);
    setExpandedTest(null);
    try {
      const faults = faultInput.trim() ? faultInput.split(',').map(s => s.trim()).filter(Boolean) : [];
      const r = await api.runTests(activeProject, {
        target: 'simulator',
        include_draft: includeDraft,
        faults,
      });
      setResult(r);
      addToast(
        `Run complete: ${r.passed}/${r.total} passed (${Math.round(r.pass_rate * 100)}%)`,
        r.failed === 0 ? 'success' : 'error'
      );
      api.listRuns(activeProject).then(x => setRuns(x.runs as any[])).catch(() => {});
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setRunning(false);
    }
  };

  if (!activeProject) return <div className="empty-state"><p>Select a project first.</p></div>;

  const passRate = result ? Math.round(result.pass_rate * 100) : 0;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Test Runner</h1>
        <p className="page-subtitle">Execute tests against the UDS simulator or hardware</p>
      </div>

      {/* Controls */}
      <div className="card mb-6">
        <div className="card-title">Run Configuration</div>
        <div className="grid grid-2" style={{ gap: '16px', marginBottom: '16px' }}>
          <div className="card" style={{ padding: '16px' }}>
            <div style={{ fontWeight: 600, marginBottom: '4px' }}>Mode</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              <span className="badge badge-cyan">Simulator</span>
              &nbsp;(Hardware runs require CAN interface)
            </div>
          </div>
          <div className="card" style={{ padding: '16px' }}>
            <div style={{ fontWeight: 600, marginBottom: '4px' }}>Eligible Tests</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.2rem', color: 'var(--amber)' }}>
              {includeDraft ? tests.length : approvedTests.length}
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '6px' }}>
                {includeDraft ? 'all (including drafts)' : 'approved only'}
              </span>
            </div>
          </div>
        </div>

        <div className="form-group" style={{ marginBottom: '12px' }}>
          <label className="form-label">Fault Injection (comma-separated)</label>
          <input className="form-input" placeholder="e.g., accept_any_key, skip_security, nrc31" value={faultInput}
            onChange={e => setFaultInput(e.target.value)} />
          <span className="form-hint">Inject simulated faults to test negative paths. Leave blank for normal run.</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
          <input type="checkbox" id="includeDraft" checked={includeDraft} onChange={e => setIncludeDraft(e.target.checked)}
            style={{ accentColor: 'var(--amber)', width: 16, height: 16, cursor: 'pointer' }} />
          <label htmlFor="includeDraft" style={{ cursor: 'pointer', fontSize: '0.875rem' }}>Include draft tests</label>
          {includeDraft && <span className="badge badge-warning" style={{ fontSize: '0.62rem' }}>draft included</span>}
        </div>

        <button className="btn btn-primary pulse-glow" onClick={handleRun} disabled={running || tests.length === 0}>
          {running ? <><span className="spinner" /> Running…</> : <><span>▶</span> Run Tests</>}
        </button>
      </div>

      {/* Live running indicator */}
      {running && (
        <div className="card mb-6" style={{ textAlign: 'center', padding: '48px' }}>
          <div className="spinner spinner-lg" style={{ margin: '0 auto 16px' }} />
          <div style={{ fontWeight: 600 }}>Executing tests against simulator…</div>
          <div className="text-muted" style={{ fontSize: '0.85rem', marginTop: '4px' }}>This may take a few seconds</div>
        </div>
      )}

      {/* Results */}
      {result && !running && (
        <div className="card mb-6">
          <div className="flex justify-between items-center" style={{ marginBottom: '16px' }}>
            <div className="card-title" style={{ marginBottom: 0 }}>Run Results</div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {result.faults.length > 0 && (
                <span className="badge badge-danger" style={{ fontSize: '0.65rem' }}>
                  ⚠ {result.faults.join(', ')}
                </span>
              )}
              <span className="badge badge-cyan text-mono">#{result.run_id?.slice(0, 8)}</span>
            </div>
          </div>

          {/* Summary stats */}
          <div className="grid grid-4" style={{ marginBottom: '20px' }}>
            {[
              { label: 'Total', value: result.total, cls: '' },
              { label: 'Passed', value: result.passed, cls: 'text-success' },
              { label: 'Failed', value: result.failed, cls: result.failed > 0 ? 'text-danger' : '' },
              { label: 'Duration', value: `${result.duration_s.toFixed(1)}s`, cls: '' },
            ].map(({ label, value, cls }) => (
              <div className="stat-card" key={label}>
                <div className="stat-label">{label}</div>
                <div className={`stat-value ${cls}`} style={{ fontSize: '1.5rem' }}>{value}</div>
              </div>
            ))}
          </div>

          <div className="progress-bar" style={{ marginBottom: '20px' }}>
            <div className={`progress-fill ${passRate === 100 ? 'success' : passRate < 60 ? 'danger' : ''}`}
              style={{ width: `${passRate}%` }} />
          </div>

          {/* Per-test results — click to expand steps */}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Test ID</th>
                  <th>Title</th>
                  <th>Category</th>
                  <th>Verdict</th>
                  <th>Steps</th>
                </tr>
              </thead>
              <tbody>
                {(result.results ?? []).map((r: RunResultItem) => {
                  const isExpanded = expandedTest === r.test_id;
                  const lastStep = r.steps?.[r.steps.length - 1];
                  return [
                    <tr
                      key={r.test_id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => setExpandedTest(isExpanded ? null : r.test_id)}
                    >
                      <td className="td-mono">{r.test_id}</td>
                      <td style={{ fontWeight: 500, fontSize: '0.82rem' }}>{r.title}</td>
                      <td><span className="badge badge-muted">{r.category}</span></td>
                      <td>
                        <span className={`badge ${VERDICT_BADGE[r.verdict] ?? 'badge-muted'}`}>
                          {r.verdict}
                        </span>
                      </td>
                      <td className="td-dim" style={{ fontFamily: 'var(--font-mono)' }}>
                        {r.steps?.length ?? 0} steps
                        {lastStep && lastStep.t_ms > 0 && ` · ${lastStep.t_ms}ms`}
                      </td>
                    </tr>,
                    isExpanded && (
                      <tr key={`${r.test_id}-steps`}>
                        <td colSpan={5} style={{ padding: '0 16px 12px', background: 'var(--bg-base)' }}>
                          <div className="code-block" style={{ fontSize: '0.75rem', lineHeight: 1.7 }}>
                            {(r.steps ?? []).map((s, si) => (
                              <div key={si} style={{ color: s.passed ? 'var(--success)' : 'var(--danger)' }}>
                                {`[${String(s.n).padStart(2, '0')}] ${s.role.padEnd(7)} ${s.action.padEnd(5)}`}
                                {s.request && ` TX: ${s.request}`}
                                {s.response && ` RX: ${s.response}`}
                                {s.t_ms > 0 && ` (${s.t_ms}ms)`}
                                {s.message && s.message !== 'ok' ? ` ← ${s.message}` : ''}
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ),
                  ];
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Run history */}
      {runs.length > 0 && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: '12px' }}>Run History ({runs.length})</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Run ID</th><th>Time</th><th>Tests</th><th>Passed</th><th>Failed</th><th>Pass Rate</th></tr>
              </thead>
              <tbody>
                {runs.slice().reverse().slice(0, 20).map((r: any, i: number) => (
                  <tr key={i}>
                    <td className="td-mono">{r.run_id?.slice(0, 12)}</td>
                    <td className="td-dim">{new Date((r.ts ?? 0) * 1000).toLocaleString()}</td>
                    <td className="td-dim">{r.total ?? '—'}</td>
                    <td><span className="text-success text-mono">{r.passed ?? '—'}</span></td>
                    <td><span className={r.failed > 0 ? 'text-danger text-mono' : 'text-mono'}>{r.failed ?? '—'}</span></td>
                    <td>
                      {r.pass_rate != null && (
                        <span className={`badge ${r.pass_rate === 1 ? 'badge-success' : 'badge-warning'}`}>
                          {Math.round(r.pass_rate * 100)}%
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
