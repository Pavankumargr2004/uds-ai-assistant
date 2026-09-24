import { useEffect, useState } from 'react';
import { api, type AuditEntry } from '../api';
import { useProject, useToast } from '../context';

export default function AuditPage() {
  const { activeProject } = useProject();
  const { addToast } = useToast();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!activeProject) return;
    setLoading(true);
    api.audit(activeProject)
      .then(r => setEntries(r.audit.slice().reverse()))
      .catch(e => addToast(e.message, 'error'))
      .finally(() => setLoading(false));
  }, [activeProject]);

  const ACTION_ICONS: Record<string, string> = {
    create_project: '🗂',
    ingest_document: '📄',
    delete_document: '🗑',
    upload_profile: '🔧',
    generate_tests: '⚡',
    review_test: '✅',
    record_run: '▶',
  };

  if (!activeProject) return <div className="empty-state"><p>Select a project first.</p></div>;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Audit Log</h1>
        <p className="page-subtitle">Full traceability record for all project actions</p>
      </div>

      {loading ? (
        <div className="empty-state"><span className="spinner spinner-lg" /></div>
      ) : entries.length === 0 ? (
        <div className="empty-state">
          <p>No audit events yet for this project.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {entries.map((e, i) => (
            <div key={i} className="card" style={{
              padding: '14px 18px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '14px',
              borderRadius: '8px',
            }}>
              <div style={{ fontSize: '1.2rem', flexShrink: 0, marginTop: '1px' }}>
                {ACTION_ICONS[e.action] ?? '📋'}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="flex items-center gap-2" style={{ marginBottom: '4px' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{e.action.replace(/_/g, ' ')}</span>
                  <span className="badge badge-info">{e.role}</span>
                </div>
                {e.detail && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>{e.detail}</div>
                )}
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  {e.user} · {new Date(e.ts).toLocaleString()}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
