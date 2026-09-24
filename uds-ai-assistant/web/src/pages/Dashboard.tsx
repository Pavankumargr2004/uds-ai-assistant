import { useEffect, useState } from 'react';
import { api, type Project, type CoverageReport } from '../api';
import { useProject, useToast } from '../context';

interface StatCardProps {
  label: string;
  value: string | number;
  delta?: string;
  accent?: boolean;
}
function StatCard({ label, value, delta, accent }: StatCardProps) {
  return (
    <div className="stat-card glow">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={accent ? { color: 'var(--success)' } : undefined}>{value}</div>
      {delta && <div className="stat-delta">{delta}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { activeProject } = useProject();
  const { addToast } = useToast();
  const [project, setProject] = useState<Project | null>(null);
  const [coverage, setCoverage] = useState<CoverageReport | null>(null);
  const [health, setHealth] = useState<{ status: string; llm: string; store_backend: string } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeProject) return;
    setLoading(true);
    Promise.all([
      api.getProject(activeProject),
      api.getCoverage(activeProject).catch(() => null),
    ]).then(([proj, cov]) => {
      setProject(proj);
      setCoverage(cov);
    }).catch(e => addToast(e.message, 'error'))
      .finally(() => setLoading(false));
  }, [activeProject]);

  if (!activeProject) {
    return (
      <div className="empty-state">
        <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
        </svg>
        <div className="page-title" style={{ fontSize: '1.2rem' }}>Welcome to UDS AI Assistant</div>
        <p>Create or select a project from the sidebar to get started.</p>
      </div>
    );
  }

  const overallPct = coverage ? Math.round(coverage.percent) : 0;

  // Build per-category rows from by_category
  const categoryRows = coverage
    ? Object.entries(coverage.by_category).map(([name, v]) => ({
        label: name.charAt(0).toUpperCase() + name.slice(1),
        covered: v.covered,
        total: v.total,
        pct: Math.round(v.percent),
      }))
    : [];

  // Per-service rows
  const serviceRows = coverage
    ? Object.entries(coverage.by_service).map(([name, v]) => ({
        label: name,
        covered: v.covered,
        total: v.total,
        pct: Math.round(v.percent),
      }))
    : [];

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">
          Project: <span className="text-amber" style={{ fontFamily: 'var(--font-mono)' }}>{activeProject}</span>
          {project?.profile && <> · ECU: {project.profile.name} v{project.profile.version} · {project.profile.oem}</>}
        </p>
      </div>

      {/* Backend health */}
      {health && (
        <div className="card mb-4" style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px' }}>
          <div className={`status-dot ${health.status === 'ok' ? '' : 'offline'}`} />
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Backend {health.status === 'ok' ? 'online' : 'offline'} · LLM: <span className="text-mono">{health.llm}</span> · Store: <span className="text-mono">{health.store_backend}</span>
          </span>
          {coverage && (
            <span className="badge badge-success" style={{ marginLeft: 'auto' }}>
              {overallPct}% overall coverage
            </span>
          )}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-4 mb-6">
        <StatCard label="Total Tests" value={loading ? '…' : project?.test_count ?? 0} />
        <StatCard label="Run History" value={loading ? '…' : project?.run_count ?? 0} />
        <StatCard
          label="Overall Coverage"
          value={coverage ? `${overallPct}%` : '—'}
          delta={coverage ? `${coverage.covered_items}/${coverage.total_items} items` : undefined}
          accent={overallPct === 100}
        />
        <StatCard
          label="Gaps"
          value={coverage ? coverage.gaps.length : '—'}
          delta={coverage?.gaps.length === 0 ? 'No coverage gaps' : undefined}
          accent={coverage?.gaps.length === 0}
        />
      </div>

      {/* Category coverage bars */}
      {coverage && categoryRows.length > 0 && (
        <div className="card mb-6">
          <div className="card-title">Coverage by Category</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {categoryRows.map(({ label, covered, total, pct }) => (
              <div key={label}>
                <div className="flex justify-between items-center" style={{ marginBottom: '6px' }}>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{label}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--amber)' }}>
                    {covered}/{total} ({pct}%)
                  </span>
                </div>
                <div className="progress-bar">
                  <div className={`progress-fill ${pct >= 80 ? 'success' : pct < 40 ? 'danger' : ''}`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-service table */}
      {coverage && serviceRows.length > 0 && (
        <div className="card mb-6">
          <div className="card-title">Coverage by Service</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Covered</th>
                  <th>Total</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {serviceRows.map(({ label, covered, total, pct }) => (
                  <tr key={label}>
                    <td className="td-mono">{label}</td>
                    <td><span className="text-success text-mono">{covered}</span></td>
                    <td className="td-dim">{total}</td>
                    <td>
                      <span className={`badge ${pct === 100 ? 'badge-success' : pct < 50 ? 'badge-danger' : 'badge-warning'}`}>
                        {pct}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ECU Profile quick info */}
      {project?.profile && (
        <div className="card">
          <div className="card-title">ECU Profile Loaded</div>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
            {[
              ['Name', project.profile.name],
              ['OEM', project.profile.oem],
              ['Version', project.profile.version],
            ].map(([k, v]) => (
              <div key={k}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{k}</div>
                <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--cyan)', fontSize: '0.85rem' }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
