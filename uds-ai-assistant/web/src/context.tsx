import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { api, setApiRole } from './api';

// ── Toast ──────────────────────────────────────────────────────────────────
interface Toast { id: number; message: string; type: 'success' | 'error' | 'info'; }

interface ToastContextType {
  toasts: Toast[];
  addToast: (msg: string, type?: Toast['type']) => void;
}

const ToastCtx = createContext<ToastContextType>({ toasts: [], addToast: () => {} });
export const useToast = () => useContext(ToastCtx);

let _toastId = 0;
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const addToast = useCallback((message: string, type: Toast['type'] = 'info') => {
    const id = ++_toastId;
    setToasts(t => [...t, { id, message, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={{ toasts, addToast }}>
      {children}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.type}`}>
            <span>{t.type === 'success' ? '✓' : t.type === 'error' ? '✕' : 'ℹ'}</span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// ── Project context ────────────────────────────────────────────────────────
export type UserRole = 'engineer' | 'lead' | 'viewer' | 'admin';

interface ProjectContextType {
  projects: string[];
  activeProject: string;
  loadingProjects: boolean;
  setProjects: (p: string[]) => void;
  setActiveProject: (p: string) => void;
  refreshProjects: () => Promise<void>;
  userRole: UserRole;
  setUserRole: (r: UserRole) => void;
}

const ProjectCtx = createContext<ProjectContextType>({
  projects: [],
  activeProject: '',
  loadingProjects: false,
  setProjects: () => {},
  setActiveProject: () => {},
  refreshProjects: async () => {},
  userRole: 'engineer',
  setUserRole: () => {},
});
export const useProject = () => useContext(ProjectCtx);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjectsState] = useState<string[]>([]);
  const [activeProject, setActiveProjectState] = useState<string>(() => {
    return localStorage.getItem('uds_active_project') || '';
  });
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [userRole, setUserRoleState] = useState<UserRole>('engineer');

  const setUserRole = useCallback((r: UserRole) => {
    setUserRoleState(r);
    setApiRole(r, `dev-${r}`);
  }, []);

  const setActiveProject = useCallback((p: string) => {
    setActiveProjectState(p);
    if (p) {
      localStorage.setItem('uds_active_project', p);
    } else {
      localStorage.removeItem('uds_active_project');
    }
  }, []);

  const setProjects = useCallback((list: string[]) => {
    setProjectsState(list);
  }, []);

  const refreshProjects = useCallback(async () => {
    setLoadingProjects(true);
    try {
      const res = await api.listProjects();
      const list = res.projects ?? [];
      setProjectsState(list);
      setActiveProjectState(prev => {
        if (prev && list.includes(prev)) return prev;
        const stored = localStorage.getItem('uds_active_project');
        if (stored && list.includes(stored)) return stored;
        return list[0] ?? '';
      });
    } catch {
      // Backend offline or initializing
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects]);

  return (
    <ProjectCtx.Provider value={{
      projects,
      activeProject,
      loadingProjects,
      setProjects,
      setActiveProject,
      refreshProjects,
      userRole,
      setUserRole
    }}>
      {children}
    </ProjectCtx.Provider>
  );
}
