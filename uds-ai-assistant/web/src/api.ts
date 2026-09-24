// API service layer for the UDS AI Assistant
const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const DEFAULT_HEADERS: Record<string, string> = {
  'Content-Type': 'application/json',
  'X-User': 'dev-user',
  'X-Role': 'engineer',
};

export function setApiRole(role: string, user = 'dev-user') {
  DEFAULT_HEADERS['X-Role'] = role;
  DEFAULT_HEADERS['X-User'] = user;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  extraHeaders?: Record<string, string>,
  isForm = false,
): Promise<T> {
  const headers: Record<string, string> = isForm
    ? { 'X-User': DEFAULT_HEADERS['X-User'], 'X-Role': DEFAULT_HEADERS['X-Role'] }
    : { ...DEFAULT_HEADERS, ...extraHeaders };

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: isForm ? (body as FormData) : body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let errMsg = `HTTP ${res.status}`;
    try { const e = await res.json(); errMsg = e.detail ?? JSON.stringify(e); } catch {}
    throw new Error(errMsg);
  }
  return res.json() as Promise<T>;
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  version: string;
  llm: string;
  store_backend: string;
}

export interface Project {
  name: string;
  created_ts: string;
  profile: { name: string; oem: string; version: string } | null;
  test_count: number;
  run_count: number;
}

export interface ECUProfile {
  name: string;
  oem: string;
  version: string;
  request_id: number;
  response_id: number;
  services: Record<string, unknown>[];
  dids: Record<string, unknown>[];
  routines: Record<string, unknown>[];
}

export interface TestCase {
  id: string;
  name: string;
  description: string;
  service: number;
  category: string;
  status: string;
  created_by?: string;
  requirement_id?: string;
  origin?: string;
  request_frames?: string[];
  expected_response?: string;
}

export interface CoverageReport {
  total_items: number;
  covered_items: number;
  percent: number;
  test_count: number;
  by_category: Record<string, { total: number; covered: number; percent: number }>;
  by_service: Record<string, { total: number; covered: number; percent: number }>;
  gaps: string[];
}

export interface RunStep {
  n: number;
  role: string;
  action: string;
  request: string;
  response: string | null;
  expected: string;
  expect: string;
  passed: boolean;
  message: string;
  t_ms: number;
}

export interface RunResultItem {
  test_id: string;
  title: string;
  category: string;
  service: number;
  verdict: 'pass' | 'fail' | 'skip' | 'error';
  steps: RunStep[];
  message: string;
  covers: string[];
}

export interface RunResult {
  run_id: string;
  target: string;
  faults: string[];
  total: number;
  passed: number;
  failed: number;
  errors: number;
  pass_rate: number;
  duration_s: number;
  results: RunResultItem[];
}

export interface AskResponse {
  answer: string;
  sources: { source: string; layer: string; score: number }[];
  query: string;
}

export interface KnowledgeSource {
  source: string;
  layer: string;
  chunks: number;
}

export interface AuditEntry {
  ts: string;
  user: string;
  role: string;
  action: string;
  detail?: string;
}

// ── API endpoints ──────────────────────────────────────────────────────────

export const api = {
  health: () => request<HealthResponse>('GET', '/health'),

  // Projects
  listProjects: () => request<{ projects: string[] }>('GET', '/projects'),
  createProject: (name: string) => request<{ name: string }>('POST', '/projects', { name }),
  getProject: (p: string) => request<Project>('GET', `/projects/${p}`),

  // Profile
  uploadProfile: (project: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<ECUProfile & { knowledge_chunks_indexed: number }>(
      'POST', `/projects/${project}/profile`, fd, undefined, true
    );
  },
  getProfile: (project: string) => request<ECUProfile>('GET', `/projects/${project}/profile`),

  // Knowledge / Documents
  listDocuments: (project: string) => request<{ sources: KnowledgeSource[] }>('GET', `/projects/${project}/documents`),
  uploadDocument: (project: string, file: File, layer: string) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<{ source: string; layer: string; chunks: number }>(
      'POST', `/projects/${project}/documents?layer=${layer}`, fd, undefined, true
    );
  },
  deleteDocument: (project: string, source: string) =>
    request<{ deleted_chunks: number }>('DELETE', `/projects/${project}/documents/${encodeURIComponent(source)}`),
  ask: (project: string, question: string, k = 5) =>
    request<AskResponse>('POST', `/projects/${project}/ask`, { question, k }),

  // Tests
  listTests: (project: string, status?: string, category?: string) => {
    const qs = new URLSearchParams();
    if (status) qs.append('status', status);
    if (category) qs.append('category', category);
    const q = qs.toString() ? `?${qs}` : '';
    return request<{ count: number; tests: TestCase[] }>('GET', `/projects/${project}/tests${q}`);
  },
  getTest: (project: string, id: string) => request<TestCase>('GET', `/projects/${project}/tests/${id}`),
  reviewTest: (project: string, id: string, decision: string, comment = '') =>
    request<TestCase>('POST', `/projects/${project}/tests/${id}/review`, { decision, comment }, { 'X-Role': 'lead' }),

  // Generation
  generate: (project: string, requirement?: string, use_llm = false) =>
    request<{ generated: number; test_ids?: string[]; intent?: unknown; coverage?: unknown }>(
      'POST', `/projects/${project}/generate`, { requirement, use_llm }
    ),

  // Coverage
  getCoverage: (project: string, approved_only = false) =>
    request<CoverageReport>('GET', `/projects/${project}/coverage?approved_only=${approved_only}`),

  // Runs
  runTests: (project: string, body: {
    test_ids?: string[];
    target?: string;
    faults?: string[];
    include_draft?: boolean;
  }) => request<RunResult>('POST', `/projects/${project}/run`, body),

  listRuns: (project: string) => request<{ runs: unknown[] }>('GET', `/projects/${project}/runs`),

  // Export
  exportUrl: (project: string, fmt: string, approved_only = true) =>
    `${BASE_URL}/projects/${project}/export/${fmt}?approved_only=${approved_only}`,

  // Audit
  audit: (project: string) => request<{ audit: AuditEntry[] }>('GET', `/projects/${project}/audit`, undefined, { 'X-Role': 'lead' }),

  // Validate
  validate: (project: string, req: string, session = 1) =>
    request<unknown>('POST', `/projects/${project}/validate`, { request: req, session }),
};
