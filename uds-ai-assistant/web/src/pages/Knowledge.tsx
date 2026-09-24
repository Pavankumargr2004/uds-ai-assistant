import { useEffect, useState, useRef } from 'react';
import { api, type KnowledgeSource, type AskResponse } from '../api';
import { useProject, useToast } from '../context';
import { getSampleProfileFile } from '../sampleProfile';

export default function KnowledgePage() {
  const { activeProject } = useProject();
  const { addToast } = useToast();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedLayer, setSelectedLayer] = useState('project');
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const docFileRef = useRef<HTMLInputElement>(null);
  const [activeTab, setActiveTab] = useState<'documents' | 'ask' | 'profile'>('documents');
  const [profileUploading, setProfileUploading] = useState(false);

  const loadSources = () => {
    if (!activeProject) return;
    setLoading(true);
    api.listDocuments(activeProject)
      .then(r => setSources(r.sources))
      .catch(e => addToast(e.message, 'error'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadSources(); }, [activeProject]);

  const handleDocUpload = async (file: File) => {
    if (!activeProject || !file) return;
    setUploading(true);
    try {
      const r = await api.uploadDocument(activeProject, file, selectedLayer);
      addToast(`Indexed ${r.chunks} chunks from "${r.source}"`, 'success');
      loadSources();
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleProfileUpload = async (file: File) => {
    if (!activeProject || !file) return;
    setProfileUploading(true);
    try {
      const r = await api.uploadProfile(activeProject, file);
      const svcCount = Array.isArray(r.services) ? r.services.length : Object.keys(r.services || {}).length;
      const didCount = Array.isArray(r.dids) ? r.dids.length : Object.keys(r.dids || {}).length;
      const rtnCount = Array.isArray(r.routines) ? r.routines.length : Object.keys(r.routines || {}).length;
      addToast(`Profile "${r.name}" loaded (${svcCount} services, ${didCount} DIDs, ${rtnCount} routines)`, 'success');
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setProfileUploading(false);
    }
  };

  const handleDelete = async (source: string) => {
    if (!activeProject) return;
    try {
      const r = await api.deleteDocument(activeProject, source);
      addToast(`Deleted ${r.deleted_chunks} chunks`, 'success');
      setSources(s => s.filter(x => x.source !== source));
    } catch (e: any) {
      addToast(e.message, 'error');
    }
  };

  const handleAsk = async () => {
    if (!activeProject || !question.trim()) return;
    setAsking(true);
    setAnswer(null);
    try {
      const r = await api.ask(activeProject, question);
      setAnswer(r);
    } catch (e: any) {
      addToast(e.message, 'error');
    } finally {
      setAsking(false);
    }
  };

  if (!activeProject) {
    return <div className="empty-state"><p>Select a project first.</p></div>;
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Knowledge Base</h1>
        <p className="page-subtitle">Ingest documents, ECU profiles, and query with AI</p>
      </div>

      <div className="tabs">
        {(['documents', 'profile', 'ask'] as const).map(t => (
          <button key={t} className={`tab-btn ${activeTab === t ? 'active' : ''}`} onClick={() => setActiveTab(t)}>
            {t === 'documents' ? '📄 Documents' : t === 'profile' ? '🔧 ECU Profile' : '🤖 Ask AI'}
          </button>
        ))}
      </div>

      {activeTab === 'documents' && (
        <div>
          {/* Upload area */}
          <div className="card mb-6"
            style={{ borderStyle: 'dashed', cursor: 'pointer', textAlign: 'center', padding: '32px' }}
            onClick={() => docFileRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleDocUpload(f); }}
          >
            <input ref={docFileRef} type="file" accept=".pdf,.txt,.md,.yaml,.yml,.json" style={{ display: 'none' }}
              onChange={e => { const f = e.target.files?.[0]; if (f) handleDocUpload(f); e.target.value = ''; }} />
            {uploading ? (
              <div className="flex items-center gap-2" style={{ justifyContent: 'center' }}>
                <span className="spinner" />
                <span className="text-muted">Indexing document…</span>
              </div>
            ) : (
              <>
                <div style={{ fontSize: '2rem', marginBottom: '8px' }}>📂</div>
                <div style={{ fontWeight: 600, marginBottom: '4px' }}>Drop a file or click to upload</div>
                <div className="text-muted" style={{ fontSize: '0.8rem' }}>PDF, TXT, MD, YAML, JSON · Layer:
                  <select className="form-select" value={selectedLayer} style={{ width: 'auto', display: 'inline-block', marginLeft: '8px', padding: '2px 8px' }}
                    onClick={e => e.stopPropagation()}
                    onChange={e => { e.stopPropagation(); setSelectedLayer(e.target.value); }}>
                    {['standard', 'oem', 'ecu', 'project'].map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                </div>
              </>
            )}
          </div>

          {/* Sources table */}
          {sources.length > 0 ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Layer</th>
                    <th>Chunks</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map(s => (
                    <tr key={s.source}>
                      <td className="text-mono">{s.source}</td>
                      <td><span className="badge badge-info">{s.layer}</span></td>
                      <td className="td-dim" style={{ fontFamily: 'var(--font-mono)' }}>{s.chunks}</td>
                      <td>
                        <button className="btn btn-sm btn-danger" onClick={() => handleDelete(s.source)}>Remove</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : !loading && (
            <div className="empty-state">
              <p>No documents indexed yet. Upload a PDF, spec sheet, or YAML file above.</p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'profile' && (
        <div className="card" style={{ maxWidth: 580 }}>
          <div className="card-title">Upload ECU Profile (YAML)</div>
          <p className="text-muted" style={{ fontSize: '0.85rem', marginBottom: '16px', lineHeight: 1.6 }}>
            The ECU profile defines available services, DIDs, and routines. It is required before generating tests.
          </p>
          <div
            style={{ borderStyle: 'dashed', border: '1px dashed var(--border-bright)', borderRadius: 'var(--radius-lg)', padding: '32px', textAlign: 'center', cursor: 'pointer', marginBottom: '16px' }}
            onClick={() => fileRef.current?.click()}
          >
            <input ref={fileRef} type="file" accept=".yaml,.yml,.json" style={{ display: 'none' }}
              onChange={e => { const f = e.target.files?.[0]; if (f) handleProfileUpload(f); e.target.value = ''; }} />
            {profileUploading ? (
              <div className="flex items-center gap-2" style={{ justifyContent: 'center' }}>
                <span className="spinner" /> <span className="text-muted">Parsing profile…</span>
              </div>
            ) : (
              <>
                <div style={{ fontSize: '2rem', marginBottom: '8px' }}>🔧</div>
                <div style={{ fontWeight: 600 }}>Drop YAML/JSON profile here</div>
                <div className="text-muted" style={{ fontSize: '0.8rem', marginTop: '4px' }}>or click to browse from disk</div>
              </>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Or use demo data:</span>
            <button
              className="btn btn-sm"
              onClick={() => handleProfileUpload(getSampleProfileFile())}
              disabled={profileUploading}
              style={{ color: 'var(--amber)', borderColor: 'rgba(245,158,11,0.4)' }}
            >
              ⚡ Load Built-in BCM-X1 Profile
            </button>
          </div>
        </div>
      )}

      {activeTab === 'ask' && (
        <div>
          <div className="card mb-4" style={{ maxWidth: 760 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Ask a question about your ECU or UDS specs</label>
              <textarea
                className="form-textarea"
                placeholder="e.g., What sessions does this ECU support? What is the NRC for 0x22?"
                value={question}
                onChange={e => setQuestion(e.target.value)}
                rows={3}
              />
            </div>
            <div className="flex justify-end mt-4" style={{ marginTop: '12px' }}>
              <button className="btn btn-primary" onClick={handleAsk} disabled={asking || !question.trim()}>
                {asking ? <span className="spinner" /> : <span>🤖</span>}
                Ask AI
              </button>
            </div>
          </div>

          {answer && (
            <div className="card" style={{ maxWidth: 760 }}>
              <div className="card-title">Answer</div>
              <div className="code-block" style={{ color: 'var(--text-primary)', background: 'var(--bg-overlay)', fontFamily: 'var(--font)', fontSize: '0.9rem' }}>
                {answer.answer}
              </div>
              {answer.sources.length > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <div className="card-title" style={{ marginBottom: '8px' }}>Sources</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {answer.sources.map((s, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem' }}>
                        <span className="badge badge-info">{s.layer}</span>
                        <span className="text-mono">{s.source}</span>
                        <span className="text-muted">score: {s.score.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
