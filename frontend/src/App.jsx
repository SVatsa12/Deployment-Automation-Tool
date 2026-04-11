import React, { useCallback, useEffect, useState } from 'react';
import { Layers, Rocket, Zap, ChevronRight, Github, RefreshCw, Loader2, ExternalLink } from 'lucide-react';
import HeroScene from './HeroScene';
import './index.css';
import * as api from './api';

function sortStepsById(list) {
  if (!Array.isArray(list)) return [];
  return [...list].sort((a, b) => a.id - b.id);
}

/** Parse deployment URL from platform_deploy step result text. */
function deploymentUrlFromSteps(steps) {
  const deploy = [...steps].reverse().find((s) => s.step_name === 'platform_deploy' && s.status === 'SUCCESS');
  const text = deploy?.result;
  if (!text || typeof text !== 'string') return null;
  const marker = text.indexOf('URL: ');
  if (marker !== -1) {
    const rest = text.slice(marker + 5).trim().split(/\s|\n/)[0];
    if (rest.startsWith('http')) return rest.replace(/[.,);]+$/, '');
  }
  const m = text.match(/https:\/\/[^\s"'<>)\]]+/);
  return m ? m[0].replace(/[.,);]+$/, '') : null;
}

function App() {
  const [backendOk, setBackendOk] = useState(null);
  const [runs, setRuns] = useState([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState(null);

  const [demoBusy, setDemoBusy] = useState(false);
  const [demoMessage, setDemoMessage] = useState(null);

  const [selectedRunId, setSelectedRunId] = useState(null);
  const [detailRun, setDetailRun] = useState(null);
  const [steps, setSteps] = useState([]);
  const [stepsLoading, setStepsLoading] = useState(false);

  const [githubUrl, setGithubUrl] = useState('https://github.com/vercel/next.js');
  const [branch, setBranch] = useState('main');
  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState(null);
  const [analyzeError, setAnalyzeError] = useState(null);
  const [platformId, setPlatformId] = useState('');
  const [deployBusy, setDeployBusy] = useState(false);
  const [deployMessage, setDeployMessage] = useState(null);

  const [actionBusy, setActionBusy] = useState(null);

  const loadRuns = useCallback(async () => {
    setRunsLoading(true);
    setRunsError(null);
    try {
      const list = await api.listWorkflowRuns({ limit: 50 });
      const arr = Array.isArray(list) ? list : [];
      setRuns(arr);
      setDetailRun((prev) => {
        if (!prev?.id) return prev;
        const row = arr.find((r) => r.id === prev.id);
        return row ? { ...prev, ...row } : prev;
      });
      setBackendOk(true);
    } catch (e) {
      setRunsError(e.message || String(e));
      setBackendOk(false);
    } finally {
      setRunsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const loadRunDetail = useCallback(async (runId) => {
    if (!runId) return;
    const rid = runId;
    setStepsLoading(true);
    try {
      const [run, stepList] = await Promise.all([api.getWorkflowRun(rid), api.getWorkflowSteps(rid)]);
      setDetailRun(run);
      setSteps(sortStepsById(stepList));
    } catch {
      setDetailRun(null);
      setSteps([]);
    } finally {
      setStepsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      setDetailRun(null);
      setSteps([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setStepsLoading(true);
      try {
        const [run, stepList] = await Promise.all([
          api.getWorkflowRun(selectedRunId),
          api.getWorkflowSteps(selectedRunId),
        ]);
        if (cancelled) return;
        setDetailRun(run);
        setSteps(sortStepsById(stepList));
      } catch {
        if (!cancelled) {
          setDetailRun(null);
          setSteps([]);
        }
      } finally {
        if (!cancelled) setStepsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || !detailRun) return;
    const busy = detailRun.status === 'RUNNING' || detailRun.status === 'PENDING';
    if (!busy) return;
    const t = setInterval(() => {
      const id = selectedRunId;
      Promise.all([api.getWorkflowRun(id), api.getWorkflowSteps(id), api.listWorkflowRuns({ limit: 50 })])
        .then(([run, stepList, list]) => {
          setDetailRun(run);
          setSteps(sortStepsById(stepList));
          if (Array.isArray(list)) {
            setRuns(list);
          }
        })
        .catch(() => {});
    }, 2500);
    return () => clearInterval(t);
  }, [selectedRunId, detailRun?.status]);

  async function handleExploreDemo() {
    setDemoBusy(true);
    setDemoMessage(null);
    try {
      const run = await api.createWorkflow({
        name: `Demo run ${new Date().toISOString()}`,
        description: 'Triggered from DeployNova UI',
        workflow_type: 'demo',
      });
      setDemoMessage(
        `Run #${run.id} — status: ${run.status}` +
          (run.current_step ? ` (step: ${run.current_step})` : '')
      );
      await loadRuns();
      setSelectedRunId(run.id);
    } catch (e) {
      setDemoMessage(`Error: ${e.message || e}`);
    } finally {
      setDemoBusy(false);
    }
  }

  async function handleAnalyze() {
    setAnalyzeBusy(true);
    setAnalyzeError(null);
    setAnalyzeResult(null);
    setDeployMessage(null);
    try {
      const res = await api.analyzeGithubRepo(githubUrl.trim());
      setAnalyzeResult(res);
      const platforms = res.compatible_platforms || [];
      if (platforms.length && !platformId) {
        const first = platforms[0];
        setPlatformId(typeof first === 'string' ? first : first.id || first.platform_id || '');
      }
    } catch (e) {
      setAnalyzeError(e.message || String(e));
    } finally {
      setAnalyzeBusy(false);
    }
  }

  async function handleDeploy() {
    if (!platformId.trim()) {
      setDeployMessage('Select or enter a platform id (e.g. vercel).');
      return;
    }
    setDeployBusy(true);
    setDeployMessage(null);
    try {
      const res = await api.deployToPlatform({
        github_url: githubUrl.trim(),
        platform_id: platformId.trim(),
        branch: branch.trim() || 'main',
      });
      setDeployMessage(res.message || JSON.stringify(res));
      await loadRuns();
      if (res.workflow_run_id) {
        setSelectedRunId(res.workflow_run_id);
        loadRunDetail(res.workflow_run_id);
      }
    } catch (e) {
      setDeployMessage(`Error: ${e.message || e}`);
    } finally {
      setDeployBusy(false);
    }
  }

  async function handleApprove(approved) {
    if (!selectedRunId) return;
    setActionBusy('approve');
    try {
      await api.approveWorkflowRun(selectedRunId, { approved, comment: approved ? 'Approved in UI' : 'Rejected in UI' });
      await loadRuns();
      await loadRunDetail(selectedRunId);
    } catch (e) {
      setRunsError(e.message || String(e));
    } finally {
      setActionBusy(null);
    }
  }

  async function handleResume() {
    if (!selectedRunId) return;
    setActionBusy('resume');
    try {
      await api.resumeWorkflowRun(selectedRunId);
      await loadRuns();
      await loadRunDetail(selectedRunId);
    } catch (e) {
      setRunsError(e.message || String(e));
    } finally {
      setActionBusy(null);
    }
  }

  const selectedRun = detailRun ?? runs.find((r) => r.id === selectedRunId);
  const deploymentUrl = selectedRun?.deployment_url || deploymentUrlFromSteps(steps);
  const deployStep = steps.find((s) => s.step_name === 'platform_deploy');

  return (
    <div className="app-container">
      <HeroScene />

      <div className="ui-overlay">
        <nav className="navbar">
          <div className="logo">
            <Layers size={28} color="#6366f1" />
            <span>DeployNova</span>
          </div>
          <div className="nav-links">
            <a href="#features">Features</a>
            <a href="#pipelines">Pipelines</a>
            <a href="#docs">Documentation</a>
            <a href="https://github.com" target="_blank" rel="noreferrer" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Github size={18} />
              GitHub
            </a>
          </div>
        </nav>

        <main className="hero">
          <div className="hero-badge">
            <Zap size={16} />
            <span>Automated Deployment v1.0 is live</span>
          </div>

          <h1 className="hero-title">
            The next generation of <span>deployment automation</span>
          </h1>

          <p className="hero-description">
            Build, test, and release your software with intelligent pipelines, manual approval gates, and step-level retry mechanisms. Seamlessly visual and immensely powerful.
          </p>

          <div className="backend-status" role="status">
            <span className={`status-dot ${backendOk === true ? 'ok' : backendOk === false ? 'err' : ''}`} />
            {backendOk === true && ' API connected'}
            {backendOk === false && ' API unreachable — start backend on port 8000'}
            {backendOk === null && ' Checking API…'}
          </div>

          <div className="hero-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
            >
              <Rocket size={18} />
              Start Deploying
            </button>
            <button type="button" className="btn btn-outline" onClick={handleExploreDemo} disabled={demoBusy}>
              {demoBusy ? <Loader2 size={18} className="spin" /> : null}
              Explore Demo
              <ChevronRight size={18} />
            </button>
          </div>

          {demoMessage && <p className="inline-message">{demoMessage}</p>}

          <div className="glass-panel" style={{ marginTop: '48px', maxWidth: '400px', display: 'flex', gap: '32px' }}>
            <div>
              <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--text-primary)' }}>99.9%</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '4px' }}>Uptime Guarantee</div>
            </div>
            <div>
              <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--accent-2)' }}>10x</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '4px' }}>Faster Deployments</div>
            </div>
          </div>
        </main>

        <section id="features" className="content-section">
          <h2 className="section-title">Connect your repo</h2>
          <p className="section-lead">Analyze a GitHub URL, then start a deployment against a supported platform (same routes as the REST API).</p>

          <div className="glass-panel api-panel">
            <label className="field-label" htmlFor="github-url">
              Repository URL
            </label>
            <input
              id="github-url"
              className="field-input"
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              placeholder="https://github.com/org/repo"
              autoComplete="off"
            />

            <div className="field-row">
              <div className="field-grow">
                <label className="field-label" htmlFor="branch">
                  Branch
                </label>
                <input id="branch" className="field-input" value={branch} onChange={(e) => setBranch(e.target.value)} />
              </div>
              <button type="button" className="btn btn-outline" onClick={handleAnalyze} disabled={analyzeBusy}>
                {analyzeBusy ? <Loader2 size={18} className="spin" /> : null}
                Analyze
              </button>
            </div>

            {analyzeError && <p className="form-error">{analyzeError}</p>}

            {analyzeResult?.compatible_platforms?.length > 0 && (
              <div className="platform-block">
                <span className="field-label">Compatible platforms</span>
                <ul className="platform-chips">
                  {analyzeResult.compatible_platforms.map((p) => {
                    const id = typeof p === 'string' ? p : p.id || p.platform_id || JSON.stringify(p);
                    const label = typeof p === 'string' ? p : p.name || p.id || id;
                    return (
                      <li key={id}>
                        <button
                          type="button"
                          className={`chip ${platformId === id ? 'active' : ''}`}
                          onClick={() => setPlatformId(id)}
                        >
                          {label}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <label className="field-label" htmlFor="platform-id">
              Platform id (deploy)
            </label>
            <input
              id="platform-id"
              className="field-input"
              value={platformId}
              onChange={(e) => setPlatformId(e.target.value)}
              placeholder="e.g. vercel, railway"
            />

            <button type="button" className="btn btn-primary deploy-btn" onClick={handleDeploy} disabled={deployBusy}>
              {deployBusy ? <Loader2 size={18} className="spin" /> : <Rocket size={18} />}
              POST /api/deploy
            </button>
            {deployMessage && <p className="inline-message">{deployMessage}</p>}
          </div>
        </section>

        <section id="pipelines" className="content-section">
          <div className="section-header">
            <h2 className="section-title">Workflow runs</h2>
            <button type="button" className="btn btn-outline btn-sm" onClick={loadRuns} disabled={runsLoading}>
              {runsLoading ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
              Refresh
            </button>
          </div>
          {runsError && <p className="form-error">{runsError}</p>}

          <div className="glass-panel api-panel runs-layout">
            <div className="runs-list">
              {runs.length === 0 && !runsLoading && <p className="muted">No runs yet. Start a demo or deployment above.</p>}
              <ul className="run-items">
                {runs.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      className={`run-item ${selectedRunId === r.id ? 'selected' : ''}`}
                      onClick={() => setSelectedRunId(r.id)}
                    >
                      <span className="run-id">#{r.id}</span>
                      <span className={`run-status status-${(r.status || '').toLowerCase()}`}>{r.status}</span>
                      <span className="run-step">{r.current_step || '—'}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div className="run-detail">
              {!selectedRunId && <p className="muted">Select a run to view steps.</p>}
              {selectedRun && (
                <>
                  <p className="run-detail-meta">
                    Run <strong>#{selectedRun.id}</strong> — <span className={`run-status status-${(selectedRun.status || '').toLowerCase()}`}>{selectedRun.status}</span>
                    {selectedRun.current_step && (
                      <>
                        {' '}
                        · current: <code>{selectedRun.current_step}</code>
                      </>
                    )}
                    {selectedRun.deployment_url && (
                      <div className="deployment-url-badge">
                        <Rocket size={14} />
                        <a href={selectedRun.deployment_url} target="_blank" rel="noreferrer">
                          {selectedRun.deployment_url}
                        </a>
                      </div>
                    )}
                  </p>
                  {selectedRun.status === 'WAITING_APPROVAL' && (
                    <div className="action-row">
                      <button type="button" className="btn btn-primary btn-sm" disabled={actionBusy} onClick={() => handleApprove(true)}>
                        Approve
                      </button>
                      <button type="button" className="btn btn-outline btn-sm" disabled={actionBusy} onClick={() => handleApprove(false)}>
                        Reject
                      </button>
                    </div>
                  )}
                  {(selectedRun.status === 'FAILED' || selectedRun.status === 'PENDING') && (
                    <div className="action-row">
                      <button type="button" className="btn btn-outline btn-sm" disabled={actionBusy} onClick={handleResume}>
                        Resume (POST /api/workflows/runs/…/resume)
                      </button>
                    </div>
                  )}
                  <h3 className="steps-heading">Steps</h3>
                  {stepsLoading && <p className="muted">Loading steps…</p>}
                  {!stepsLoading && steps.length === 0 && <p className="muted">No step records.</p>}
                  <ul className="step-list">
                    {steps.map((s) => (
                      <li key={s.id} className="step-row">
                        <div className="step-main">
                          <span className="step-name">{s.step_name}</span>
                          <span className={`run-status status-${(s.status || '').toLowerCase()}`}>{s.status}</span>
                        </div>
                        {s.result && <div className="step-result">{s.result}</div>}
                        {s.error_message && <div className="step-err">{s.error_message}</div>}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
        </section>

        <section id="docs" className="content-section docs-section">
          <h2 className="section-title">API</h2>
          <p className="section-lead">
            OpenAPI docs: run the backend and visit{' '}
            <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
              /docs
            </a>
            . The UI uses the same JSON bodies as <code>POST /api/workflows</code>, <code>/api/analyze</code>, and <code>/api/deploy</code>.
          </p>
        </section>

        <footer className="site-footer">
          <span>DeployNova · wired to FastAPI</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
