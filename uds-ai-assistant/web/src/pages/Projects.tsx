import { useState } from 'react';
import { api } from '../api';
import { useProject, useToast } from '../context';
import { getSampleProfileFile } from '../sampleProfile';

export default function ProjectsPage() {
  const { projects, setProjects, setActiveProject, activeProject, refreshProjects } = useProject();
  const { addToast } = useToast();
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [showModal, setShowModal] = useState(false);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.createProject(newName.trim());
      const updated = [...projects, newName.trim()];
      setProjects(updated);
      setActiveProject(newName.trim());
      addToast(`Project "${newName.trim()}" created`, 'success');
      setNewName('');
      setShowModal(false);
      await refreshProjects();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setCreating(false);
    }
  };

  const handleLoadDemo = async () => {
    setLoadingDemo(true);
    const demoName = 'bcm-demo';
    try {
      if (!projects.includes(demoName)) {
        await api.createProject(demoName);
      }
      const sampleFile = getSampleProfileFile();
      const prof = await api.uploadProfile(demoName, sampleFile);
      setActiveProject(demoName);
      await refreshProjects();
      addToast(`BCM-X1 Demo Project loaded (${prof.name} v${prof.version})!`, 'success');
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setLoadingDemo(false);
    }
  };

  return (
    <div>
      <div className="page-header flex justify-between items-center" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 className="page-title">Projects</h1>
          <p className="page-subtitle">Manage your ECU diagnostic projects</p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            className="btn"
            onClick={handleLoadDemo}
            disabled={loadingDemo}
            style={{ borderColor: 'rgba(245,158,11,0.4)', color: 'var(--amber)' }}
            title="Create and load the Acme Motors BCM-X1 sample profile"
          >
            {loadingDemo ? <span className="spinner" /> : <span>⚡</span>}
            Load Demo Project (BCM-X1)
          </button>
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            New Project
          </button>
        </div>
      </div>

      <div className="grid grid-3">
        {projects.length === 0 && (
          <div className="empty-state" style={{ gridColumn: '1/-1' }}>
            <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 9.776c.112-.017.227-.026.344-.026h15.812c.117 0 .232.009.344.026m-16.5 0a2.25 2.25 0 00-1.883 2.542l.857 6a2.25 2.25 0 002.227 1.932H19.05a2.25 2.25 0 002.227-1.932l.857-6a2.25 2.25 0 00-1.883-2.542m-16.5 0V6A2.25 2.25 0 016 3.75h3.879a1.5 1.5 0 011.06.44l2.122 2.12a1.5 1.5 0 001.06.44H18A2.25 2.25 0 0120.25 9v.776" />
            </svg>
            <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>No projects found</div>
            <p>Create a project or load the built-in BCM-X1 sample project to get started immediately.</p>
            <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
              <button className="btn btn-primary" onClick={handleLoadDemo} disabled={loadingDemo}>
                {loadingDemo ? <span className="spinner" /> : <span>⚡</span>} Load Demo Project (BCM-X1)
              </button>
              <button className="btn" onClick={() => setShowModal(true)}>Create Custom Project</button>
            </div>
          </div>
        )}
        {projects.map(name => (
          <div
            key={name}
            className={`card glow ${activeProject === name ? 'active-project' : ''}`}
            style={{
              cursor: 'pointer',
              borderColor: activeProject === name ? 'rgba(245,158,11,0.6)' : undefined,
              boxShadow: activeProject === name ? 'var(--shadow-amber)' : undefined,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between'
            }}
            onClick={() => {
              setActiveProject(name);
              addToast(`Selected project "${name}"`, 'info');
            }}
          >
            <div>
              <div className="flex items-center gap-2 mb-4" style={{ marginBottom: '12px' }}>
                <div style={{
                  width: 38, height: 38,
                  background: activeProject === name ? 'var(--amber-glow)' : 'var(--bg-overlay)',
                  border: `1px solid ${activeProject === name ? 'rgba(245,158,11,0.5)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={activeProject === name ? 'var(--amber)' : 'var(--text-secondary)'} strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008z" />
                  </svg>
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: '1rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</div>
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginTop: '2px' }}>
                    {activeProject === name ? (
                      <span className="badge badge-warning" style={{ fontSize: '0.62rem' }}>Active Target</span>
                    ) : (
                      <span className="badge badge-muted" style={{ fontSize: '0.62rem' }}>Inactive</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', borderTop: '1px solid var(--border)', paddingTop: '10px', marginTop: '10px' }}>
              {activeProject === name ? '✓ Current Active Target' : 'Click to select this target'}
            </div>
          </div>
        ))}
      </div>

      {/* Create modal */}
      {showModal && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal">
            <div className="modal-title">Create New Project</div>
            <div className="form-group">
              <label className="form-label">Project Name</label>
              <input
                className="form-input"
                placeholder="e.g., ecu-body-control-module"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleCreate()}
                autoFocus
              />
              <span className="form-hint">Use lowercase letters, numbers, and hyphens only.</span>
            </div>
            <div className="flex gap-2 justify-end">
              <button className="btn" onClick={() => setShowModal(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={handleCreate} disabled={creating || !newName.trim()}>
                {creating ? <span className="spinner" /> : null}
                Create Project
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
