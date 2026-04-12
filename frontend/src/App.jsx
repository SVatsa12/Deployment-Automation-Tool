import React, { useCallback, useEffect, useState } from 'react';

function scrollToExecutionSteps() {
  // Defer until React has committed the run detail panel (selectedRun + steps).
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.getElementById('execution-steps')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}
import { Layers, Rocket, Zap, ChevronRight, Github, RefreshCw, Loader2, ExternalLink, Shield, Cpu, BarChart3, Cloud } from 'lucide-react';
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
  const [filter, setFilter] = useState('all');
  const [docsTab, setDocsTab] = useState('architecture');

  const handleDeleteRun = async (e, runId) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete run #${runId}?`)) return;
    try {
      await api.deleteWorkflowRun(runId);
      setRuns((prev) => prev.filter((r) => r.id !== runId));
      if (selectedRunId === runId) {
        setSelectedRunId(null);
        setDetailRun(null);
        setSteps([]);
      }
    } catch (e) {
      setRunsError(e.message || String(e));
    }
  };

  const PipelineFlow = ({ run, steps }) => {
    const hasDeploySteps = (steps || []).some(
      (s) => s.step_name === 'git_clone' || s.step_name === 'platform_deploy'
    );
    const isDeployment =
      run.workflow_type === 'deployment' ||
      (run.name && run.name.toLowerCase().includes('deploy')) ||
      hasDeploySteps;
    const flowSteps = isDeployment 
      ? [
          { name: 'git_clone', label: 'Clone', icon: <Github size={18} /> },
          { name: 'platform_deploy', label: 'Deploy', icon: <Rocket size={18} /> },
          { name: 'cleanup', label: 'Cleanup', icon: <RefreshCw size={18} /> }
        ]
      : [
          { name: 'build', label: 'Build', icon: <Cpu size={18} /> },
          { name: 'test', label: 'Test', icon: <Shield size={18} /> },
          { name: 'approval', label: 'Approval', icon: <ExternalLink size={18} /> },
          { name: 'deploy', label: 'Deploy', icon: <Rocket size={18} /> }
        ];

    return (
      <div className="pipeline-flow-container">
        <div className="pipeline-flow">
          {flowSteps.map((fs, idx) => {
            const step = steps.find(s => s.step_name === fs.name);
            const status = step?.status || 'PENDING';
            const isActive = run.current_step === fs.name || (run.status === 'RUNNING' && status === 'RUNNING');
            
            return (
              <React.Fragment key={fs.name}>
                <div className={`pipeline-node ${status.toLowerCase()} ${isActive ? 'active' : ''}`}>
                  <div className="node-icon">
                    {status === 'RUNNING' || (isActive && run.status === 'RUNNING') ? <Loader2 size={18} className="spin" /> : fs.icon}
                  </div>
                  <div className="node-label">{fs.label}</div>
                </div>
                {idx < flowSteps.length - 1 && (
                  <div className={`pipeline-connector ${status === 'SUCCESS' ? 'active' : ''}`} />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>
    );
  };

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
      setRuns((prev) => prev.map((r) => (r.id === rid ? { ...r, ...run } : r)));
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

  // Poll while run is in progress; depend on status only so object identity changes do not reset the interval.
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
            setDetailRun((prev) => {
              if (!prev || prev.id !== id) return prev;
              const row = list.find((r) => r.id === id);
              return row ? { ...prev, ...row, ...run } : { ...prev, ...run };
            });
          }
        })
        .catch(() => {});
    }, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- detailRun?.status is the intended trigger
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
      await loadRunDetail(run.id);
      scrollToExecutionSteps();
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
        await loadRunDetail(res.workflow_run_id);
        scrollToExecutionSteps();
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
  const deploymentUrlLong = selectedRun?.deployment_url || deploymentUrlFromSteps(steps);
  const deploymentUrl =
    selectedRun?.short_url || selectedRun?.deployment_url || deploymentUrlFromSteps(steps);
  const deployStep = steps.find((s) => s.step_name === 'platform_deploy');

  const filteredRuns = runs.filter((r) => {
    if (filter === 'all') return true;
    return (r.status || '').toLowerCase() === filter.toLowerCase();
  });

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
              onClick={() => document.getElementById('deploy-section')?.scrollIntoView({ behavior: 'smooth' })}
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
          <h2 className="section-title">Why choose DeployNova?</h2>
          <p className="section-lead">Experience the future of CI/CD with our cutting-edge automation engine.</p>
          
          <div className="features-grid">
            <div className="feature-card">
              <div className="feature-icon-wrapper">
                <Cpu size={24} />
              </div>
              <h3>Intelligent Analysis</h3>
              <p>Our engine automatically detects your framework, dependencies, and environment requirements to suggest optimal deployment strategies.</p>
            </div>

            <div className="feature-card">
              <div className="feature-icon-wrapper">
                <BarChart3 size={24} />
              </div>
              <h3>Real-time Insights</h3>
              <p>Monitor your deployment pipelines thread-by-thread with live logs and granular status updates for every single execution step.</p>
            </div>

            <div className="feature-card">
              <div className="feature-icon-wrapper">
                <Shield size={24} />
              </div>
              <h3>Approval Gates</h3>
              <p>Maintain full control with manual approval triggers. Review changes and sign off before anything hits your production environment.</p>
            </div>

            <div className="feature-card">
              <div className="feature-icon-wrapper">
                <Cloud size={24} />
              </div>
              <h3>Multi-Cloud Ready</h3>
              <p>Whether it's Vercel, Railway, or your own Kubernetes cluster, DeployNova bridges the gap between code and infrastructure.</p>
            </div>
          </div>
        </section>

        <section id="deploy-section" className="content-section">
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
            <h2 className="section-title">Pipeline Dashboard</h2>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                type="button"
                className="btn btn-outline btn-sm"
                onClick={async () => {
                  await loadRuns();
                  if (selectedRunId) await loadRunDetail(selectedRunId);
                }}
                disabled={runsLoading}
              >
                {runsLoading ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
                Refresh
              </button>
            </div>
          </div>
          
          <div className="pipeline-filters">
            {['all', 'RUNNING', 'SUCCESS', 'FAILED', 'WAITING_APPROVAL'].map(f => (
              <button 
                key={f} 
                className={`filter-chip ${filter === f ? 'active' : ''}`}
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>

          {runsError && <p className="form-error">{runsError}</p>}

          <div className="runs-layout">
            <div className="runs-grid">
              {filteredRuns.length === 0 && !runsLoading && <p className="muted">No runs found for this filter.</p>}
              {filteredRuns.map((r) => (
                <div 
                  key={r.id} 
                  className={`run-card ${selectedRunId === r.id ? 'selected' : ''}`}
                  onClick={() => setSelectedRunId(r.id)}
                >
                  <div className="run-card-header">
                    <div className="run-card-info">
                      <span className="run-card-id">Run #{r.id}</span>
                      <span className="run-card-type">{r.workflow_type || 'Workflow'}</span>
                    </div>
                    <span className={`run-card-status status-${(r.status || '').toLowerCase()}`}>{r.status}</span>
                  </div>
                  
                  <div className="run-visual-steps">
                    {[1, 2, 3, 4].map(idx => (
                      <div key={idx} className={`run-step-dot ${r.status === 'SUCCESS' ? 'success' : r.status === 'FAILED' ? 'failed' : r.status === 'RUNNING' ? 'active' : ''}`} />
                    ))}
                  </div>

                  <div className="run-actions-bar">
                    <button className="delete-btn" onClick={(e) => handleDeleteRun(e, r.id)}>
                      <RefreshCw size={12} /> Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {selectedRun && (
              <div id="execution-steps" className="run-details-overlay glass-panel">
                <div className="section-header" style={{ marginBottom: '24px' }}>
                  <h3 className="section-title" style={{ fontSize: '1.25rem' }}>
                    Execution: #{selectedRun.id}
                  </h3>
                  <span className={`run-status status-${(selectedRun.status || '').toLowerCase()}`}>
                    {selectedRun.status}
                  </span>
                </div>

                <PipelineFlow run={selectedRun} steps={steps} />

                {deploymentUrl && (
                  <div className="deployment-live-banner">
                    <div className="deployment-live-title">
                      <ExternalLink size={18} />
                      Live deployment
                    </div>
                    <a className="deployment-live-link" href={deploymentUrl} target="_blank" rel="noreferrer">
                      {deploymentUrl}
                    </a>
                  </div>
                )}

                <div className="action-row">
                  {selectedRun.status === 'WAITING_APPROVAL' && (
                    <>
                      <button type="button" className="btn btn-primary btn-sm" disabled={actionBusy} onClick={() => handleApprove(true)}>
                        Approve
                      </button>
                      <button type="button" className="btn btn-outline btn-sm" disabled={actionBusy} onClick={() => handleApprove(false)}>
                        Reject
                      </button>
                    </>
                  )}
                  {(selectedRun.status === 'FAILED' || selectedRun.status === 'PENDING') && (
                    <button type="button" className="btn btn-outline btn-sm" disabled={actionBusy} onClick={handleResume}>
                      Resume Execution
                    </button>
                  )}
                </div>

                <h4 className="steps-heading" style={{ marginTop: '32px' }}>Execution Log</h4>
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
              </div>
            )}
          </div>
        </section>


        <section id="docs" className="content-section docs-section">
          <h2 className="section-title">Technical Specification</h2>
          <p className="section-lead">
            A comprehensive guide to the DeployNova deployment lifecycle and the REST API that powers it.
          </p>

          <div className="glass-panel docs-container">
            <aside className="docs-nav">
              {[
                { id: 'lifecycle', label: 'Deployment Lifecycle' },
                { id: 'endpoints', label: 'API Endpoints' },
                { id: 'architecture', label: 'Architecture' },
                { id: 'security', label: 'Security & Config' }
              ].map(tab => (
                <button 
                  key={tab.id}
                  className={`docs-nav-item ${docsTab === tab.id ? 'active' : ''}`}
                  onClick={() => setDocsTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </aside>

            <main className="docs-content">
              {docsTab === 'lifecycle' && (
                <article className="docs-article">
                  <h3>Deployment Lifecycle</h3>
                  <p>When a deployment is triggered via <code>/api/deploy</code>, the system initiates a stateful three-stage pipeline. Each stage is an isolated execution step with its own retry logic and state persistence.</p>
                  
                  <div className="step-doc-block">
                    <h4>1. Git Clone Phase</h4>
                    <p>The system creates a workspace in a secured temporary directory and executes a shallow clone of the target repository.</p>
                    <ul>
                      <li><strong>Inputs:</strong> GitHub URL, Branch Name.</li>
                      <li><strong>Persistence:</strong> Stores the local path in the workflow context.</li>
                      <li><strong>Failure:</strong> Automatically retries if network issues occur or repository is temporarily unavailable.</li>
                    </ul>
                  </div>

                  <div className="step-doc-block">
                    <h4>2. Platform Deployment Phase</h4>
                    <p>This is the core execution stage where the system interfaces with third-party providers using their respective CLI engines (Vercel, Railway, etc.).</p>
                    <ul>
                      <li><strong>Action:</strong> Running environment analysis and executing the deployment command.</li>
                      <li><strong>Output:</strong> Captures the generated deployment URL and logs.</li>
                      <li><strong>Status:</strong> Remains in <code>RUNNING</code> status until the platform confirms the deployment is live or failed.</li>
                    </ul>
                  </div>

                  <div className="step-doc-block">
                    <h4>3. Cleanup Phase</h4>
                    <p>Vital for system health, this step ensures that ephemeral data is purged once the deployment confirms success or failure.</p>
                    <ul>
                      <li><strong>Security:</strong> Removes all source code from the local server disk.</li>
                      <li><strong>Metadata:</strong> Updates the database with the final <code>SUCCESS</code> or <code>FAILED</code> status and ensures short-links are generated.</li>
                    </ul>
                  </div>
                </article>
              )}

              {docsTab === 'endpoints' && (
                <article className="docs-article">
                  <h3>Full Endpoint Reference</h3>
                  <p>DeployNova uses a FastAPI-driven REST API. All endpoints are versioned and return JSON responses.</p>
                  
                  <div className="api-endpoint-doc">
                    <div className="docs-badge">POST</div> <code>/api/analyze</code>
                    <p>Analyzes a repository to detect framework and suggest platforms.</p>
                    <div className="code-block" style={{ marginTop: '12px', padding: '12px' }}>
                      <code>Body: &#123; "github_url": "string" &#125;</code>
                    </div>
                  </div>

                  <div className="api-endpoint-doc">
                    <div className="docs-badge">POST</div> <code>/api/deploy</code>
                    <p>Starts a non-blocking background deployment pipeline.</p>
                    <div className="code-block" style={{ marginTop: '12px', padding: '12px' }}>
                      <code>Body: &#123; "github_url": "string", "platform_id": "string", "branch": "string" &#125;</code>
                    </div>
                  </div>

                  <div className="api-endpoint-doc">
                    <div className="docs-badge">GET</div> <code>/api/workflows/runs/&#123;id&#125;</code>
                    <p>Returns the real-time status, current step, and deployment URL if available.</p>
                  </div>

                  <div className="api-endpoint-doc">
                    <div className="docs-badge">POST</div> <code>/api/workflows/runs/&#123;id&#125;/resume</code>
                    <p>Attempts to restart a failed workflow from the last successful checkpoint.</p>
                  </div>

                  <div className="api-endpoint-doc">
                    <div className="docs-badge">DELETE</div> <code>/api/workflows/runs/&#123;id&#125;</code>
                    <p>Purges run metadata and all associated execution steps from history.</p>
                  </div>
                </article>
              )}

              {docsTab === 'architecture' && (
                <article className="docs-article">
                  <h3>System Architecture</h3>
                  <p>DeployNova is built on a distributed, asynchronous architecture designed for high throughput and reliability.</p>
                  <ul>
                    <li><strong>Stateless API:</strong> The API handles request routing and validation. It uses FastAPI's <code>BackgroundTasks</code> to ensure responses are near-instant (~50ms).</li>
                    <li><strong>Stateful Workflow Engine:</strong> A dedicated runner that manages sequential execution. It checks the database before every step to determine if it should execute or skip.</li>
                    <li><strong>Persistence Layer:</strong> SQLite backend tracks every transition between <code>PENDING</code>, <code>RUNNING</code>, <code>SUCCESS</code>, and <code>FAILED</code> states.</li>
                  </ul>
                </article>
              )}

              {docsTab === 'security' && (
                <article className="docs-article">
                  <h3>Configuration & Security</h3>
                  <p>All sensitive configuration should be managed via environment variables. The system uses <code>python-dotenv</code> to load settings at runtime.</p>
                  <div className="code-block">
                    <code>
                      # Recommended Production Setup<br/>
                      DATABASE_URL=postgresql://user:pass@host:5432/db<br/>
                      DEPLOY_TIMEOUT=600<br/>
                      MAX_CONCURRENT_JOBS=10
                    </code>
                  </div>
                  <p style={{ marginTop: '20px' }}><strong>Security Note:</strong> Never expose your <code>DATABASE_URL</code> in public logs or client-side assets. The UI only interacts with the backend via the secure API layer.</p>
                </article>
              )}
            </main>
          </div>
        </section>

        <footer className="site-footer">
          <span>DeployNova · wired to FastAPI</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
