import React, { useState, useEffect, useRef } from 'react';
import { startHiringAssistant, getHiringStatus, approveHiring, hiringWsUrl, careerCoach } from '../api/aiApi';
import { jobsByRecruiter, searchJobs } from '../api/jobApi';

function coachRoleBucket(title = '') {
  const t = String(title || '').toLowerCase();
  if (/(machine learning|ml|data scientist|data science|ai|analytics|nlp)/.test(t)) return 'data-ai';
  if (/(backend|api|platform|server|java|python developer|golang|node)/.test(t)) return 'backend';
  if (/(frontend|front end|ui|ux|react|angular|vue)/.test(t)) return 'frontend';
  if (/(full.?stack)/.test(t)) return 'fullstack';
  if (/(devops|sre|site reliability|cloud|infrastructure)/.test(t)) return 'devops';
  if (/(qa|test|automation)/.test(t)) return 'qa';
  if (/(product manager|product owner)/.test(t)) return 'product';
  if (/(security|cyber)/.test(t)) return 'security';
  if (/(ios|android|mobile)/.test(t)) return 'mobile';
  if (/(analyst|business analyst)/.test(t)) return 'analyst';
  return 'other';
}

function buildDiverseCoachJobs(rows, maxCount = 48) {
  const seen = new Set();
  const unique = [];
  for (const job of rows || []) {
    const sig = `${(job.title || '').toLowerCase()}|${(job.company_name || '').toLowerCase()}`;
    if (seen.has(sig)) continue;
    seen.add(sig);
    unique.push(job);
  }

  const groups = unique.reduce((acc, job) => {
    const bucket = coachRoleBucket(job.title);
    if (!acc[bucket]) acc[bucket] = [];
    acc[bucket].push(job);
    return acc;
  }, {});

  const order = ['backend', 'frontend', 'fullstack', 'devops', 'product', 'security', 'qa', 'mobile', 'analyst', 'data-ai', 'other'];
  const chosen = [];
  const capPerBucket = 6;

  for (const bucket of order) {
    const bucketRows = groups[bucket] || [];
    chosen.push(...bucketRows.slice(0, capPerBucket));
  }

  for (const bucket of order) {
    const bucketRows = groups[bucket] || [];
    const remainder = bucketRows.slice(capPerBucket);
    for (const job of remainder) {
      if (chosen.length >= maxCount) break;
      chosen.push(job);
    }
    if (chosen.length >= maxCount) break;
  }

  return chosen.slice(0, maxCount);
}

export default function AIAssistantPage() {
  const recruiter_id = localStorage.getItem('recruiter_id') || '';
  const member_id    = localStorage.getItem('member_id')    || '';
  const defaultTab = recruiter_id ? 'hiring' : 'coach';
  const tabStorageKey = `ai_tab_${recruiter_id || member_id || 'guest'}`;
  const hiringStateStorageKey = recruiter_id ? `ai_hiring_state_${recruiter_id}` : '';
  const coachStateStorageKey = member_id ? `ai_coach_state_${member_id}` : '';

  const [tab, setTab]   = useState(() => {
    const saved = sessionStorage.getItem(tabStorageKey);
    if (recruiter_id) return saved === 'coach' ? 'hiring' : (saved || 'hiring');
    return saved || 'coach';
  });
  const [jobs, setJobs] = useState([]);
  const [memberJobs, setMemberJobs] = useState([]);

  // Hiring Assistant state
  const [selectedJob, setSelectedJob] = useState('');
  const [topK, setTopK]               = useState(5);
  const [traceId, setTraceId]         = useState('');
  const [status, setStatus]           = useState(null);
  const [logs, setLogs]               = useState([]);
  const [loading, setLoading]         = useState(false);
  const wsRef = useRef(null);
  const logsEndRef = useRef(null);

  // Career Coach state
  const [jobId, setJobId]             = useState('');
  const [resumeText, setResumeText]   = useState('');
  const [resumeFile, setResumeFile]   = useState(null);
  const [coaching, setCoaching]       = useState(null);
  const [coachLoading, setCoachLoad]  = useState(false);
  const [coachJobsLoading, setCoachJobsLoading] = useState(false);
  const [coachJobsError, setCoachJobsError] = useState('');

  useEffect(() => {
    if (recruiter_id && tab === 'coach') setTab('hiring');
    if (!recruiter_id && tab === 'hiring') setTab('coach');
  }, [recruiter_id, tab]);

  useEffect(() => {
    sessionStorage.setItem(tabStorageKey, tab);
  }, [tabStorageKey, tab]);

  const loadCoachJobs = async () => {
    if (!member_id) return;
    setCoachJobsLoading(true);
    setCoachJobsError('');
    try {
      const r = await searchJobs({ limit: 200 });
      const rows = r.data.results || [];
      const diverseRows = buildDiverseCoachJobs(rows);
      setMemberJobs(diverseRows);
      if (!diverseRows.length) {
        setCoachJobsError('No open jobs found for coaching right now.');
      }
      if (!jobId && diverseRows.length) {
        setJobId(diverseRows[0].job_id);
      } else if (jobId && !diverseRows.some(j => j.job_id === jobId) && diverseRows.length) {
        setJobId(diverseRows[0].job_id);
      }
    } catch (_) {
      setMemberJobs([]);
      setCoachJobsError('Unable to load jobs for Career Coach. Please retry.');
    }
    setCoachJobsLoading(false);
  };

  useEffect(() => {
    if (recruiter_id) {
      jobsByRecruiter(recruiter_id).then(r => { const rows = r.data.results || []; setJobs(rows); if (!selectedJob && rows.length) setSelectedJob(rows[0].job_id); }).catch(() => {});
    } else if (member_id) {
      loadCoachJobs();
    }
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, [recruiter_id, member_id]);

  useEffect(() => {
    if (!hiringStateStorageKey) return;
    try {
      const raw = sessionStorage.getItem(hiringStateStorageKey);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (saved.selectedJob) setSelectedJob(saved.selectedJob);
      if (saved.topK) setTopK(saved.topK);
      if (saved.traceId) setTraceId(saved.traceId);
      if (saved.status) setStatus(saved.status);
      if (Array.isArray(saved.logs)) setLogs(saved.logs);
      setLoading(false);
    } catch {
      // ignore malformed cached state
    }
  }, [hiringStateStorageKey]);

  useEffect(() => {
    if (!hiringStateStorageKey) return;
    sessionStorage.setItem(hiringStateStorageKey, JSON.stringify({
      selectedJob,
      topK,
      traceId,
      status,
      logs,
    }));
  }, [hiringStateStorageKey, selectedJob, topK, traceId, status, logs]);

  useEffect(() => {
    if (!coachStateStorageKey) return;
    try {
      const raw = sessionStorage.getItem(coachStateStorageKey);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (saved.jobId) setJobId(saved.jobId);
      if (typeof saved.resumeText === 'string') setResumeText(saved.resumeText);
      if (saved.coaching) setCoaching(saved.coaching);
    } catch {
      // ignore malformed cached state
    }
  }, [coachStateStorageKey]);

  useEffect(() => {
    if (!coachStateStorageKey) return;
    sessionStorage.setItem(coachStateStorageKey, JSON.stringify({
      jobId,
      resumeText,
      coaching,
    }));
  }, [coachStateStorageKey, jobId, resumeText, coaching]);

  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  const startAssistant = async () => {
    if (!selectedJob) return;
    setLoading(true); setLogs([]); setStatus(null);

    try {
      const res = await startHiringAssistant({ job_id: selectedJob, recruiter_id, top_k: topK });
      const tid = res.data.trace_id;
      setTraceId(tid);
      addLog('info', `Workflow started — trace_id: ${tid}`);
      connectWebSocket(tid);
    } catch (e) {
      addLog('error', 'Failed to start: ' + (e.response?.data?.detail || e?.response?.data?.error || e.message));
      setLoading(false);
    }
  };

  const connectWebSocket = (tid) => {
    const url = hiringWsUrl(tid);
    addLog('info', `Connecting to WebSocket: ${url}`);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    let settled = false;

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      addLog('ws', `[${data.status}] ${data.step || ''}`);
      setStatus(prev => ({
        ...(prev || {}),
        ...data,
        shortlist: data.shortlist ?? prev?.shortlist ?? [],
      }));
      if (['awaiting_approval', 'completed', 'failed', 'approved', 'rejected'].includes(data.status)) {
        settled = true;
        setLoading(false);
        refreshStatus(tid);
        ws.close();
      }
    };
    ws.onerror = () => {
      if (!settled) {
        addLog('error', 'WebSocket unavailable — polling for status');
        pollStatus(tid);
      }
      ws.close();
    };
    ws.onclose = () => {
      if (!settled) pollStatus(tid);
    };
  };

  const refreshStatus = async (tid) => {
    try {
      const r = await getHiringStatus(tid);
      setStatus(prev => ({
        ...(prev || {}),
        ...(r.data || {}),
        shortlist: r.data?.shortlist ?? prev?.shortlist ?? [],
      }));
    } catch (_) {}
  };

  const pollStatus = async (tid) => {
    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 3000));
      try {
        const r = await getHiringStatus(tid);
        setStatus(r.data);
        addLog('poll', `[${r.data.status}] ${r.data.step || ''}`);
        if (['awaiting_approval', 'completed', 'failed'].includes(r.data.status)) { setLoading(false); return; }
      } catch (_) {}
    }
    setLoading(false);
  };

  const handleApprove = async (action, editedOutreach) => {
    try {
      const res = await approveHiring({ trace_id: traceId, action, edited_outreach: editedOutreach });
      setStatus(res.data);
      addLog('info', `Action "${action}" submitted`);
    } catch (e) { addLog('error', 'Approve failed: ' + e.message); }
  };

  const handleCoach = async () => {
    if (!jobId) return;
    setCoachLoad(true); setCoaching(null);
    try {
      let payload;
      if (resumeFile) {
        payload = new FormData();
        payload.append('member_id', member_id);
        payload.append('job_id', jobId);
        if (resumeText.trim()) payload.append('resume_text', resumeText.trim());
        payload.append('resume_file', resumeFile);
      } else {
        payload = { member_id, job_id: jobId, resume_text: resumeText || undefined };
      }
      const res = await careerCoach(payload);
      setCoaching(res.data);
    } catch (e) { alert('Career coach failed: ' + (e.response?.data?.detail || e.message)); }
    setCoachLoad(false);
  };

  const handleResumeFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) {
      setResumeFile(null);
      return;
    }
    const lower = file.name.toLowerCase();
    const ok = lower.endsWith('.pdf') || lower.endsWith('.doc') || lower.endsWith('.docx');
    if (!ok) {
      alert('Please upload a PDF, DOC, or DOCX file.');
      e.target.value = '';
      return;
    }
    setResumeFile(file);
  };

  const addLog = (type, msg) => setLogs(l => [...l, { type, msg, ts: new Date().toLocaleTimeString() }]);

  const logColor = { info: '#0a66c2', ws: '#10b981', poll: '#f59e0b', error: '#ef4444' };

  const tabStyle = (t) => ({
    padding: '8px 20px', border: 'none', cursor: 'pointer', borderRadius: 4,
    background: tab === t ? '#0a66c2' : '#f0f0f0', color: tab === t ? 'white' : '#333', fontWeight: tab === t ? 600 : 400
  });

  return (
    <div style={{ maxWidth: 1000 }}>
      <h2 style={{ color: '#0a66c2' }}>Agent Tools</h2>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {recruiter_id && (
          <button type="button" style={tabStyle('hiring')} onClick={() => setTab('hiring')}>Hiring Assistant</button>
        )}
        {!recruiter_id && (
          <button type="button" style={tabStyle('coach')} onClick={() => setTab('coach')}>Career Coach</button>
        )}
      </div>

      {/* HIRING ASSISTANT */}
      {tab === 'hiring' && (
        <div>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: 20, marginBottom: 20 }}>
            <h3 style={{ margin: '0 0 16px' }}>Start AI Hiring Workflow</h3>
            <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div style={{ flex: 2 }}>
                <label style={{ fontSize: 13, color: '#555', display: 'block', marginBottom: 4 }}>Select Job Posting</label>
                <select value={selectedJob} onChange={e => setSelectedJob(e.target.value)}
                  style={{ width: '100%', padding: '9px 12px', border: '1px solid #ddd', borderRadius: 4 }}>
                  <option value="">-- choose a job --</option>
                  {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title} ({j.city})</option>)}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 13, color: '#555', display: 'block', marginBottom: 4 }}>Top K candidates</label>
                <input type="number" min={1} max={20} value={topK} onChange={e => setTopK(+e.target.value)}
                  style={{ width: '100%', padding: '9px 12px', border: '1px solid #ddd', borderRadius: 4 }} />
              </div>
              <button onClick={startAssistant} disabled={loading || !selectedJob}
                style={{ padding: '10px 24px', background: loading ? '#93c5fd' : '#0a66c2', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 600 }}>
                {loading ? 'Running...' : 'Start AI Workflow'}
              </button>
            </div>
          </div>

          {/* Live Logs */}
          {logs.length > 0 && (
            <div style={{ background: '#0f172a', borderRadius: 8, padding: 16, marginBottom: 20, fontFamily: 'monospace', fontSize: 12, height: 180, overflowY: 'auto' }}>
              {logs.map((l, i) => (
                <div key={i} style={{ color: logColor[l.type] || '#fff', marginBottom: 4 }}>
                  <span style={{ color: '#64748b' }}>[{l.ts}]</span> {l.msg}
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          )}

          {/* Status Badge */}
          {status && (
            <div style={{ marginBottom: 20 }}>
              <span style={{ padding: '4px 12px', borderRadius: 12, fontSize: 13, fontWeight: 600, background:
                status.status === 'completed' ? '#dcfce7' : status.status === 'failed' ? '#fee2e2' :
                status.status === 'awaiting_approval' ? '#fef3c7' : '#dbeafe',
                color: status.status === 'completed' ? '#15803d' : status.status === 'failed' ? '#dc2626' :
                status.status === 'awaiting_approval' ? '#92400e' : '#1e40af' }}>
                Status: {status.status}
              </span>
              {status.step && <span style={{ marginLeft: 12, color: '#555', fontSize: 14 }}>{status.step}</span>}
            </div>
          )}

          {/* Shortlist Results */}
          {status?.shortlist?.length > 0 && (
            <div>
              <h3>Candidate Shortlist ({status.shortlist.length})</h3>
              {status.shortlist.map((c, i) => (
                <CandidateCard key={i} candidate={c} onApprove={handleApprove} awaitingApproval={status.status === 'awaiting_approval'} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* CAREER COACH — members only */}
      {!recruiter_id && tab === 'coach' && (
        <div style={{ maxWidth: 700 }}>
          <p style={{ color: '#555', marginBottom: 20 }}>Get feedback to tailor your resume and profile for a specific job.</p>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 13, color: '#555', display: 'block', marginBottom: 4 }}>Choose a target job</label>
            <select value={jobId} onChange={e => setJobId(e.target.value)}
              disabled={coachJobsLoading}
              style={{ width: '100%', padding: '9px 12px', border: '1px solid #ddd', borderRadius: 4, boxSizing: 'border-box', background: coachJobsLoading ? '#f8fafc' : 'white' }}>
              <option value="">-- choose a job --</option>
              {memberJobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title} — {j.company_name || 'Company'}</option>)}
            </select>
            {coachJobsLoading && <p style={{ margin: '6px 0 0', color: '#6b7280', fontSize: 12 }}>Loading jobs...</p>}
            {!coachJobsLoading && coachJobsError && (
              <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
                <p style={{ margin: 0, color: '#dc2626', fontSize: 12 }}>{coachJobsError}</p>
                <button onClick={loadCoachJobs}
                  style={{ padding: '4px 10px', border: '1px solid #d1d5db', background: 'white', borderRadius: 12, cursor: 'pointer', fontSize: 12 }}>
                  Retry
                </button>
              </div>
            )}
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 12, color: '#666', display: 'block', marginBottom: 4 }}>Manual job ID (optional)</label>
            <input placeholder="Paste a job_id only if you want to override the dropdown" value={jobId}
              onChange={e => setJobId(e.target.value)}
              style={{ width: '100%', padding: '9px 12px', border: '1px solid #ddd', borderRadius: 4, boxSizing: 'border-box' }} />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 13, color: '#555', display: 'block', marginBottom: 4 }}>Upload Resume (PDF, DOC, DOCX)</label>
            <input
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={handleResumeFileChange}
              style={{ display: 'block', marginBottom: 6 }}
            />
            <div style={{ fontSize: 12, color: '#6b7280' }}>
              {resumeFile ? `Selected: ${resumeFile.name}` : 'No file selected'}
            </div>
            {resumeFile && (
              <button
                type="button"
                onClick={() => setResumeFile(null)}
                style={{ marginTop: 6, padding: '4px 10px', border: '1px solid #d1d5db', background: 'white', borderRadius: 12, cursor: 'pointer', fontSize: 12 }}
              >
                Remove file
              </button>
            )}
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: 13, color: '#555', display: 'block', marginBottom: 4 }}>Your Resume Text (optional)</label>
            <textarea placeholder="Paste your resume text here, or leave blank to use profile data..." value={resumeText}
              onChange={e => setResumeText(e.target.value)}
              style={{ width: '100%', padding: '9px 12px', border: '1px solid #ddd', borderRadius: 4, height: 120, boxSizing: 'border-box' }} />
          </div>
          <button onClick={handleCoach} disabled={coachLoading || !jobId}
            style={{ padding: '10px 28px', background: '#0a66c2', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 600 }}>
            {coachLoading ? 'Analyzing...' : 'Get Career Coaching'}
          </button>

          {coaching && (
            <div style={{ marginTop: 28 }}>
              {coaching.headline_suggestion && (
                <div style={{ background: '#dbeafe', borderRadius: 8, padding: 16, marginBottom: 16 }}>
                  <strong>Suggested Headline:</strong>
                  <p style={{ margin: '4px 0', color: '#1e40af' }}>{coaching.headline_suggestion}</p>
                </div>
              )}
              <CoachSection title="Resume Improvements" items={coaching.resume_improvements} color="#10b981" />
              <CoachSection title="Skills to Add" items={coaching.skills_to_add} color="#8b5cf6" />
              <CoachSection title="Cover Letter Tips" items={coaching.cover_letter_tips} color="#f59e0b" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CandidateCard({ candidate, onApprove, awaitingApproval }) {
  const [editedMsg, setEdited] = useState(candidate.outreach_draft || '');
  const [submitted, setSubmitted] = useState(false);

  const score = Math.round((candidate.match_score || 0) * 100);
  const scoreColor = score >= 70 ? '#15803d' : score >= 40 ? '#b45309' : '#dc2626';

  const displayName = candidate.candidate_name?.trim() || 'Candidate';

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 20, marginBottom: 16, background: 'white' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#111' }}>{displayName}</div>
          <code style={{ fontSize: 12, color: '#6b7280' }}>{candidate.member_id}</code>
          <div style={{ fontSize: 13, color: '#555', marginTop: 4 }}>{candidate.explanation}</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 28, fontWeight: 700, color: scoreColor }}>{score}%</div>
          <div style={{ fontSize: 12, color: '#888' }}>Match Score</div>
        </div>
      </div>

      {candidate.skills_overlap?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <strong style={{ fontSize: 13 }}>Skill Overlap: </strong>
          {candidate.skills_overlap.map(s => (
            <span key={s} style={{ background: '#dbeafe', color: '#1e40af', padding: '2px 8px', borderRadius: 12, fontSize: 12, marginRight: 6 }}>{s}</span>
          ))}
        </div>
      )}

      {candidate.outreach_draft && (
        <div>
          <strong style={{ fontSize: 13 }}>Outreach Draft:</strong>
          <textarea value={editedMsg} onChange={e => setEdited(e.target.value)}
            style={{ width: '100%', padding: 10, border: '1px solid #ddd', borderRadius: 4, height: 80, fontSize: 13, marginTop: 6, boxSizing: 'border-box' }} />
          {awaitingApproval && !submitted && (
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button onClick={() => { onApprove('approve', editedMsg); setSubmitted(true); }}
                style={{ padding: '6px 16px', background: '#10b981', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer' }}>Approve & Send</button>
              <button onClick={() => { onApprove('edit', editedMsg); setSubmitted(true); }}
                style={{ padding: '6px 16px', background: '#f59e0b', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer' }}>Save Edits</button>
              <button onClick={() => { onApprove('reject', editedMsg); setSubmitted(true); }}
                style={{ padding: '6px 16px', background: '#ef4444', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer' }}>Reject</button>
            </div>
          )}
          {submitted && <p style={{ color: '#10b981', fontSize: 13, marginTop: 4 }}>Action submitted.</p>}
        </div>
      )}
    </div>
  );
}

function CoachSection({ title, items, color }) {
  if (!items?.length) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      <strong style={{ color }}>{title}:</strong>
      <ul style={{ margin: '8px 0', paddingLeft: 20 }}>
        {items.map((item, i) => <li key={i} style={{ color: '#374151', fontSize: 14, marginBottom: 4 }}>{item}</li>)}
      </ul>
    </div>
  );
}
