import { useState, useEffect } from 'react';
import { api, type HealthResponse } from './api';
import { ProjectProvider, ToastProvider, useProject, useToast, type UserRole } from './context';
import Dashboard from './pages/Dashboard';
import ProjectsPage from './pages/Projects';
import KnowledgePage from './pages/Knowledge';
import TestsPage from './pages/Tests';
import RunnerPage from './pages/Runner';
import ExportPage from './pages/Export';
import AuditPage from './pages/Audit';

type NavPage = 'dashboard' | 'projects' | 'knowledge' | 'tests' | 'runner' | 'export' | 'audit';

function AppContent() {
  const { activeProject, setActiveProject, projects, userRole, setUserRole, refreshProjects } = useProject();
  const { addToast } = useToast();
  const [currentPage, setCurrentPage] = useState<NavPage>('dashboard');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthStatus, setHealthStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [testCount, setTestCount] = useState<number | null>(null);

  // Poll backend health
  const checkHealth = async () => {
    try {
      const h = await api.health();
      setHealth(h);
      setHealthStatus('online');
    } catch {
      setHealthStatus('offline');
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  // Update test count when activeProject changes
  useEffect(() => {
    if (!activeProject) {
      setTestCount(null);
      return;
    }
    api.listTests(activeProject)
      .then(res => setTestCount(res.count ?? res.tests?.length ?? 0))
      .catch(() => setTestCount(null));
  }, [activeProject, currentPage]);

  const navItems: { id: NavPage; label: string; icon: string; badge?: string | number }[] = [
    { id: 'dashboard', label: 'Dashboard', icon: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z' },
    { id: 'projects', label: 'Projects', icon: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z', badge: projects.length ? `${projects.length}` : undefined },
    { id: 'knowledge', label: 'Knowledge Base', icon: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z' },
    { id: 'tests', label: 'Test Cases', icon: 'M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z', badge: testCount !== null ? `${testCount}` : undefined },
    { id: 'runner', label: 'Test Runner', icon: 'M8 5v14l11-7z' },
    { id: 'export', label: 'Export & Tools', icon: 'M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2v9.67z' },
    { id: 'audit', label: 'Audit Log', icon: 'M19 3h-4.18C14.4 1.84 13.3 1 12 1c-1.3 0-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z' },
  ];

  return (
    <div className="app-shell">
      {/* ── Sidebar ────────────────────────────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: 32,
              height: 32,
              background: 'linear-gradient(135deg, #F59E0B 0%, #D97706 100%)',
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 16px rgba(245,158,11,0.4)',
              color: '#000',
              fontWeight: 900,
              fontSize: '1rem',
              fontFamily: 'var(--font-mono)'
            }}>
              ⚡
            </div>
            <div>
              <div className="wordmark">
                UDS <span>ASSISTANT</span>
              </div>
              <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginTop: '2px' }}>
                <span className="badge">ISO 14229</span>
                <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>v{health?.version ?? '0.1.0'}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Quick project pill in sidebar */}
        <div style={{ padding: '12px 14px 4px' }}>
          <div style={{
            background: 'var(--bg-overlay)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: '8px 12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px'
          }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
                Active Target
              </div>
              <div style={{
                fontSize: '0.82rem',
                fontWeight: 600,
                color: activeProject ? 'var(--amber)' : 'var(--text-secondary)',
                fontFamily: 'var(--font-mono)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}>
                {activeProject || 'No project selected'}
              </div>
            </div>
            <button
              className="btn btn-sm btn-icon"
              title="Manage Projects"
              onClick={() => setCurrentPage('projects')}
              style={{ padding: '4px 6px', fontSize: '0.75rem', background: 'transparent', border: 'none', color: 'var(--text-secondary)' }}
            >
              ⇄
            </button>
          </div>
        </div>

        {/* Navigation Sections */}
        <div className="sidebar-section">
          <div className="sidebar-section-label">Workspace</div>
          <button
            className={`nav-item ${currentPage === 'dashboard' ? 'active' : ''}`}
            onClick={() => setCurrentPage('dashboard')}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d={navItems[0].icon} />
            </svg>
            <span>{navItems[0].label}</span>
          </button>
          <button
            className={`nav-item ${currentPage === 'projects' ? 'active' : ''}`}
            onClick={() => setCurrentPage('projects')}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d={navItems[1].icon} />
            </svg>
            <span>{navItems[1].label}</span>
            {navItems[1].badge && (
              <span className="badge badge-muted" style={{ marginLeft: 'auto', fontSize: '0.62rem' }}>
                {navItems[1].badge}
              </span>
            )}
          </button>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-section-label">Diagnostic Studio</div>
          <button
            className={`nav-item ${currentPage === 'knowledge' ? 'active' : ''}`}
            onClick={() => setCurrentPage('knowledge')}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d={navItems[2].icon} />
            </svg>
            <span>{navItems[2].label}</span>
          </button>
          <button
            className={`nav-item ${currentPage === 'tests' ? 'active' : ''}`}
            onClick={() => setCurrentPage('tests')}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d={navItems[3].icon} />
            </svg>
            <span>{navItems[3].label}</span>
            {navItems[3].badge !== undefined && (
              <span className="badge badge-warning" style={{ marginLeft: 'auto', fontSize: '0.62rem' }}>
                {navItems[3].badge}
              </span>
            )}
          </button>
          <button
            className={`nav-item ${currentPage === 'runner' ? 'active' : ''}`}
            onClick={() => setCurrentPage('runner')}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d={navItems[4].icon} />
            </svg>
            <span>{navItems[4].label}</span>
          </button>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-section-label">Compliance & Tools</div>
          <button
            className={`nav-item ${currentPage === 'export' ? 'active' : ''}`}
            onClick={() => setCurrentPage('export')}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d={navItems[5].icon} />
            </svg>
            <span>{navItems[5].label}</span>
          </button>
          <button
            className={`nav-item ${currentPage === 'audit' ? 'active' : ''}`}
            onClick={() => setCurrentPage('audit')}
          >
            <svg className="nav-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d={navItems[6].icon} />
            </svg>
            <span>{navItems[6].label}</span>
          </button>
        </div>

        {/* Oracle Architecture Callout */}
        <div style={{ margin: 'auto 12px 12px', padding: '12px', background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.15)', borderRadius: 'var(--radius)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
            <span style={{ fontSize: '0.75rem' }}>🛡️</span>
            <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--amber)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Spec-Oracle Active
            </span>
          </div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
            Deterministic rule engine (R1-R11) enforces correctness by construction.
          </p>
        </div>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          <div className="sidebar-status">
            <div className={`status-dot ${healthStatus === 'online' ? '' : 'offline'}`} />
            <span>{healthStatus === 'online' ? 'API Online' : 'API Disconnected'}</span>
            <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>:8000</span>
          </div>
          {health?.llm && (
            <div style={{ marginTop: '6px', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
              LLM: <span className="text-mono" style={{ color: 'var(--cyan)' }}>{health.llm}</span>
            </div>
          )}
        </div>
      </aside>

      {/* ── Main Content Area ──────────────────────────────────────────────── */}
      <main className="main-content">
        {/* Topbar */}
        <header className="topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '1.1rem' }}>
              {currentPage === 'dashboard' && '📊'}
              {currentPage === 'projects' && '🗂️'}
              {currentPage === 'knowledge' && '📚'}
              {currentPage === 'tests' && '⚡'}
              {currentPage === 'runner' && '▶️'}
              {currentPage === 'export' && '💾'}
              {currentPage === 'audit' && '📋'}
            </span>
            <div className="topbar-title">
              {currentPage === 'dashboard' && 'System Dashboard'}
              {currentPage === 'projects' && 'Project Management'}
              {currentPage === 'knowledge' && 'Knowledge & Profile Ingestion'}
              {currentPage === 'tests' && 'ISO 14229 Test Suite'}
              {currentPage === 'runner' && 'Simulator & Hardware Test Execution'}
              {currentPage === 'export' && 'Export, Reporting & Validation'}
              {currentPage === 'audit' && 'Four-Eyes Audit Log'}
            </div>
          </div>

          <div className="topbar-spacer" />

          {/* Project switcher dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label htmlFor="topbar-project" style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Project:
            </label>
            <select
              id="topbar-project"
              className="topbar-project-select"
              value={activeProject}
              onChange={e => {
                setActiveProject(e.target.value);
                addToast(`Switched project to "${e.target.value}"`, 'info');
              }}
            >
              {projects.length === 0 && <option value="">No projects</option>}
              {projects.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
            <button
              className="btn btn-sm"
              title="Refresh projects list"
              onClick={async () => {
                await refreshProjects();
                addToast('Projects list refreshed', 'info');
              }}
            >
              ↻
            </button>
          </div>

          {/* User role switch (dev auth header toggle) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '8px' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Role:</span>
            <select
              className="form-select"
              style={{ width: 'auto', padding: '4px 8px', fontSize: '0.78rem' }}
              value={userRole}
              onChange={e => {
                const r = e.target.value as UserRole;
                setUserRole(r);
                addToast(`Simulating user role: ${r}`, 'info');
              }}
            >
              <option value="engineer">Engineer (Author)</option>
              <option value="lead">Lead (Reviewer)</option>
              <option value="viewer">Viewer</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          {/* API Docs link */}
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="btn btn-sm"
            style={{ marginLeft: '6px', color: 'var(--text-secondary)' }}
            title="Open FastAPI Swagger Documentation"
          >
            Swagger ↗
          </a>
        </header>

        {/* Page Content */}
        <section className="page">
          {currentPage === 'dashboard' && <Dashboard />}
          {currentPage === 'projects' && <ProjectsPage />}
          {currentPage === 'knowledge' && <KnowledgePage />}
          {currentPage === 'tests' && <TestsPage />}
          {currentPage === 'runner' && <RunnerPage />}
          {currentPage === 'export' && <ExportPage />}
          {currentPage === 'audit' && <AuditPage />}
        </section>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <ProjectProvider>
        <AppContent />
      </ProjectProvider>
    </ToastProvider>
  );
}
