import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend, LineChart, Line
} from 'recharts';
import { jobsByRecruiter, createJob, closeJob } from '../api/jobApi';
import { applicationsByJob, updateStatus } from '../api/applicationApi';
import { getFunnel, getGeo, getRecruiterDashboard } from '../api/analyticsApi';
import { searchMembers, getMember } from '../api/profileApi';
import api from '../api/apiClient';
import { resizeImageToJpegDataUrl } from '../utils/imageResize';

const BLUE   = '#0a66c2';
const COLORS = [BLUE, '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

// ── tiny helpers ──────────────────────────────────────────────────────────────
const card = (style = {}) => ({
  background: 'white', borderRadius: 10, padding: 20,
  boxShadow: '0 1px 4px rgba(0,0,0,0.08)', ...style,
});

const pill = (active) => ({
  padding: '8px 20px', border: 'none', cursor: 'pointer', borderRadius: 20,
  background: active ? BLUE : '#f0f0f0',
  color: active ? 'white' : '#444',
  fontWeight: active ? 700 : 500, fontSize: 14,
});

const btn = (variant = 'primary', extra = {}) => ({
  padding: '8px 18px', border: variant === 'primary' ? 'none' : `1.5px solid ${BLUE}`,
  background: variant === 'primary' ? BLUE : 'white',
  color: variant === 'primary' ? 'white' : BLUE,
  borderRadius: 20, cursor: 'pointer', fontWeight: 600, fontSize: 13, ...extra,
});

const inp = { width: '100%', padding: '9px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginBottom: 12, boxSizing: 'border-box' };

const STATUS_COLORS = {
  submitted: BLUE, reviewing: '#f59e0b', interview: '#10b981', offer: '#22c55e', rejected: '#ef4444',
};

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color = BLUE }) {
  return (
    <div style={{ ...card(), display: 'flex', alignItems: 'center', gap: 16, flex: '1 1 180px' }}>
      <div style={{ width: 6, height: 48, borderRadius: 4, background: color, flexShrink: 0 }} />
      <div>
        <div style={{ fontSize: 26, fontWeight: 700, color: '#111' }}>{value}</div>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#444' }}>{label}</div>
        {sub && <div style={{ fontSize: 12, color: '#888' }}>{sub}</div>}
      </div>
    </div>
  );
}

// ── Candidate card ────────────────────────────────────────────────────────────
function CandidateCard({ member, onMessage }) {
  const initials = `${member.first_name?.[0] || ''}${member.last_name?.[0] || ''}`.toUpperCase();
  return (
    <div style={{ ...card({ padding: 16 }), display: 'flex', alignItems: 'center', gap: 14 }}>
      <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'linear-gradient(135deg,#0a66c2,#5ba5f5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 700, fontSize: 18, flexShrink: 0 }}>
        {member.profile_photo_url
          ? <img src={member.profile_photo_url} alt="" style={{ width: 52, height: 52, borderRadius: '50%', objectFit: 'cover' }} />
          : initials}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>{member.first_name} {member.last_name}</div>
        <div style={{ fontSize: 13, color: '#555', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{member.headline || '—'}</div>
        <div style={{ fontSize: 12, color: '#888' }}>{[member.city, member.state, member.country].filter(Boolean).join(', ') || 'Location unknown'}</div>
        {member.skills?.length > 0 && (
          <div style={{ marginTop: 6, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {member.skills.slice(0, 4).map(s => (
              <span key={s} style={{ fontSize: 11, background: '#e8f0fe', color: BLUE, padding: '2px 8px', borderRadius: 10 }}>{s}</span>
            ))}
          </div>
        )}
      </div>
      <button onClick={() => onMessage && onMessage(member)} style={btn('outline')}>Message</button>
    </div>
  );
}

// ── Applicant row ─────────────────────────────────────────────────────────────
function ApplicantRow({ app, memberProfile, onStatus }) {
  const name = memberProfile
    ? `${memberProfile.first_name} ${memberProfile.last_name}`
    : app.member_id.slice(0, 8) + '…';
  const headline = memberProfile?.headline || '';
  const initials = memberProfile
    ? `${memberProfile.first_name?.[0] || ''}${memberProfile.last_name?.[0] || ''}`.toUpperCase()
    : '?';

  return (
    <div style={{ ...card({ padding: 16 }), display: 'flex', alignItems: 'center', gap: 14, marginBottom: 10 }}>
      <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'linear-gradient(135deg,#0a66c2,#5ba5f5)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', fontWeight: 700, fontSize: 15, flexShrink: 0, overflow: 'hidden' }}>
        {memberProfile?.profile_photo_url ? (
          <img src={memberProfile.profile_photo_url} alt="" style={{ width: 44, height: 44, objectFit: 'cover' }} />
        ) : initials}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600 }}>{name}</div>
        {headline && <div style={{ fontSize: 12, color: '#555' }}>{headline}</div>}
        <div style={{ fontSize: 12, color: '#888' }}>Applied {new Date(app.applied_at).toLocaleDateString()}</div>
      </div>
      <span style={{ padding: '3px 10px', borderRadius: 12, fontSize: 12, background: STATUS_COLORS[app.status] + '22', color: STATUS_COLORS[app.status], fontWeight: 600, marginRight: 8 }}>
        {app.status}
      </span>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', maxWidth: 260 }}>
        {['reviewing', 'interview', 'offer', 'rejected'].map(s => (
          <button key={s} onClick={() => onStatus(app.application_id, s)}
            style={{ padding: '3px 10px', fontSize: 11, border: `1px solid ${STATUS_COLORS[s]}`, color: app.status === s ? 'white' : STATUS_COLORS[s], background: app.status === s ? STATUS_COLORS[s] : 'white', borderRadius: 10, cursor: 'pointer', fontWeight: 600 }}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function RecruiterPage() {
  const recruiter_id = localStorage.getItem('recruiter_id') || '';
  const recruiterPhotoInputRef = useRef(null);

  const [me, setMe] = useState(null);
  const [tab, setTab]               = useState('dashboard');
  const [jobs, setJobs]             = useState([]);
  const [topJobs, setTopJobs]       = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [applicants, setApplicants] = useState([]);
  const [memberProfiles, setMemberProfiles] = useState({});   // member_id → profile
  const [funnel, setFunnel]         = useState(null);
  const [geo, setGeo]               = useState([]);
  const [recruiterDashboard, setRecruiterDashboard] = useState(null);
  const [newJob, setNewJob]         = useState({});
  const [msg, setMsg]               = useState('');
  const [msgType, setMsgType]       = useState('info');

  // Find Candidates state
  const [searchQuery, setSearchQuery] = useState({ keyword: '', skill: '', location: '' });
  const [candidates, setCandidates]   = useState([]);
  const [searchDone, setSearchDone]   = useState(false);

  // ── data loaders ────────────────────────────────────────────────────────────
  const loadJobs = useCallback(async () => {
    if (!recruiter_id) return;
    try {
      const [jobsRes, dashboardRes] = await Promise.all([
        jobsByRecruiter(recruiter_id),
        getRecruiterDashboard(recruiter_id, selectedJob || null),
      ]);
      const r = jobsRes;
      const rows = r.data.results || [];
      setJobs(rows);
      const dashboard = dashboardRes.data || null;
      setRecruiterDashboard(dashboard);
      const jobMap = Object.fromEntries(rows.map(j => [j.job_id, j.title]));
      const analyticsTop = (dashboard?.top_jobs_by_applications || []);
      if (analyticsTop.length > 0) {
        setTopJobs(analyticsTop.map(j => ({
          label: jobMap[j.job_id] || j.job_id,
          count: j.applications || 0,
          job_id: j.job_id,
        })));
      } else {
        setTopJobs(
          [...rows]
            .sort((a, b) => (b.applicants_count || 0) - (a.applicants_count || 0))
            .slice(0, 10)
            .map(job => ({ label: job.title, count: job.applicants_count || 0, job_id: job.job_id }))
        );
      }
      if (!selectedJob && rows.length) setSelectedJob(rows[0].job_id);
    } catch (_) {}
  }, [recruiter_id, selectedJob]);

  useEffect(() => { loadJobs(); }, [loadJobs]);

  useEffect(() => {
    if (!recruiter_id) return;
    api.post('/recruiters/get', { recruiter_id }).then((res) => setMe(res.data)).catch(() => setMe(null));
  }, [recruiter_id]);

  const uploadRecruiterPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (e.target) e.target.value = '';
    if (!file || !recruiter_id) return;
    if (file.size > 8 * 1024 * 1024) {
      notify('Image must be under 8 MB.', 'error');
      return;
    }
    try {
      const dataUrl = await resizeImageToJpegDataUrl(file);
      await api.post('/recruiters/update', { recruiter_id, profile_photo_url: dataUrl });
      setMe((m) => (m ? { ...m, profile_photo_url: dataUrl } : m));
      notify('Profile photo saved.', 'success');
    } catch (err) {
      notify(err?.message || 'Upload failed', 'error');
    }
  };

  const removeRecruiterPhoto = async () => {
    if (!recruiter_id) return;
    try {
      await api.post('/recruiters/update', { recruiter_id, profile_photo_url: '' });
      setMe((m) => (m ? { ...m, profile_photo_url: '' } : m));
      notify('Profile photo removed.', 'success');
    } catch (_) {
      notify('Could not remove photo.', 'error');
    }
  };

  const loadApplicants = async (job_id) => {
    if (!job_id) return;
    setSelectedJob(job_id);
    try {
      const [appRes, funnelRes, geoRes, dashboardRes] = await Promise.all([
        applicationsByJob({ job_id, recruiter_id }),
        getFunnel({ job_id, window_days: 30 }),
        getGeo({ job_id, window_days: 30 }),
        getRecruiterDashboard(recruiter_id, job_id),
      ]);
      const apps = appRes.data.results || [];
      setApplicants(apps);
      setFunnel(funnelRes.data);
      setGeo(geoRes.data.geo || []);
      setRecruiterDashboard(dashboardRes.data || null);

      // Fetch member profiles for all applicants in parallel
      const profiles = {};
      await Promise.all(apps.map(async (a) => {
        try {
          const r = await getMember(a.member_id);
          profiles[a.member_id] = r.data;
        } catch (_) {}
      }));
      setMemberProfiles(profiles);
    } catch (_) {}
  };

  const handleStatusChange = async (application_id, status) => {
    try {
      await updateStatus({ application_id, status, recruiter_id });
      await Promise.all([loadApplicants(selectedJob), loadJobs()]);
      notify('Status updated to: ' + status, 'success');
    } catch (_) { notify('Update failed', 'error'); }
  };

  const handleCreateJob = async () => {
    if (!newJob.title) { notify('Job title is required', 'error'); return; }
    try {
      const res = await createJob({ ...newJob, recruiter_id });
      notify('Job posted! ID: ' + res.data.job_id, 'success');
      setNewJob({});
      await loadJobs();
      setTab('myJobs');
    } catch (e) { notify(e.response?.data?.detail || e?.response?.data?.error || 'Create failed', 'error'); }
  };

  const handleCloseJob = async (job_id) => {
    try { await closeJob({ job_id, recruiter_id }); notify('Job closed.', 'success'); loadJobs(); } catch (_) {}
  };

  const handleSearch = async () => {
    try {
      const r = await searchMembers({ ...searchQuery, limit: 20 });
      setCandidates(r.data.results || []);
      setSearchDone(true);
    } catch (_) { notify('Search failed', 'error'); }
  };

  const notify = (text, type = 'info') => { setMsg(text); setMsgType(type); setTimeout(() => setMsg(''), 3500); };

  // ── Derived stats ──────────────────────────────────────────────────────────
  const activeJobs    = jobs.filter(j => j.status === 'open').length;
  const totalApps     = jobs.reduce((sum, j) => sum + (j.applicants_count || 0), 0);
  const pendingReview = applicants.filter(a => a.status === 'submitted' || a.status === 'reviewing').length;

  const funnelData = funnel ? [
    { name: 'Views',        value: funnel.funnel?.views        || 0 },
    { name: 'Saves',        value: funnel.funnel?.saves        || 0 },
    { name: 'Applications', value: funnel.funnel?.submissions  || 0 },
  ] : [];

  const statusDist = ['submitted', 'reviewing', 'interview', 'offer', 'rejected'].map(s => ({
    name: s, value: applicants.filter(a => a.status === s).length,
  })).filter(d => d.value > 0);

  const jobTitleById = jobs.reduce((acc, j) => {
    acc[j.job_id] = j.title || j.job_id;
    return acc;
  }, {});

  const recruiterTopPerMonth = (recruiterDashboard?.top_jobs_by_applications_per_month || [])
    .slice(0, 30)
    .map((r) => ({
      month: r.month,
      applications: r.applications,
      job_label: jobTitleById[r.job_id] || r.job_id?.slice(0, 8) || '',
    }));
  const recruiterLowTraction = (recruiterDashboard?.low_traction_jobs || [])
    .map((r) => ({
      job: (jobTitleById[r.job_id] || r.job_id || 'unknown').slice(0, 30),
      applications: r.applications || 0,
    }));
  const recruiterClicks = (recruiterDashboard?.clicks_per_job || [])
    .slice(0, 10)
    .map((r) => ({
      job: (jobTitleById[r.job_id] || r.job_id || 'unknown').slice(0, 30),
      clicks: r.clicks || 0,
    }));
  const recruiterSavesDaily = recruiterDashboard?.saved_jobs_per_day || [];
  const recruiterSavesWeekly = recruiterDashboard?.saved_jobs_per_week || [];
  const recruiterCityMonthly = (recruiterDashboard?.city_wise_applications_per_month || [])
    .slice(0, 30)
    .map((r) => ({ month: r.month, city: r.city || 'Unknown', applications: r.applications || 0 }));

  if (!recruiter_id) return (
    <div style={{ padding: 60, textAlign: 'center', color: '#666' }}>
      <div style={{ fontSize: 48, marginBottom: 16 }}>🔒</div>
      <h3>Recruiter access only</h3>
      <p>Please log out and sign in with a Recruiter account.</p>
    </div>
  );

  return (
    <div style={{ maxWidth: 1100 }}>

      {/* ── Header + profile photo ── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flex: '1 1 280px' }}>
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <div style={{
              width: 72, height: 72, borderRadius: '50%', border: '3px solid #e8f0fe',
              overflow: 'hidden', background: 'linear-gradient(135deg,#0a66c2,#5ba5f5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'white', fontWeight: 700, fontSize: 22,
            }}>
              {me?.profile_photo_url ? (
                <img src={me.profile_photo_url} alt="" style={{ width: 72, height: 72, objectFit: 'cover' }} />
              ) : (
                `${me?.first_name?.[0] || ''}${me?.last_name?.[0] || ''}`.toUpperCase() || '·'
              )}
            </div>
            <input ref={recruiterPhotoInputRef} type="file" accept="image/*" onChange={uploadRecruiterPhoto} style={{ display: 'none' }} />
          </div>
          <div style={{ minWidth: 0 }}>
            <h2 style={{ margin: 0, color: '#111', fontSize: 22 }}>Recruiter Hub</h2>
            <p style={{ margin: '4px 0 0', color: '#444', fontSize: 15, fontWeight: 600 }}>
              {me ? `${me.first_name} ${me.last_name}` : 'Loading…'}
              {me?.company_name ? <span style={{ color: '#666', fontWeight: 500 }}> · {me.company_name}</span> : null}
            </p>
            <p style={{ margin: '4px 0 0', color: '#666', fontSize: 13 }}>Manage your talent pipeline and job postings</p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10, alignItems: 'center' }}>
              <button type="button" onClick={() => recruiterPhotoInputRef.current?.click()}
                style={{ ...btn('outline'), fontSize: 12, padding: '6px 14px' }}>
                Upload photo
              </button>
              {me?.profile_photo_url ? (
                <button type="button" onClick={removeRecruiterPhoto}
                  style={{ ...btn('outline'), fontSize: 12, padding: '6px 14px', color: '#dc2626', borderColor: '#fecaca' }}>
                  Remove photo
                </button>
              ) : null}
              <Link to={`/recruiter/profile?recruiter_id=${encodeURIComponent(recruiter_id)}`}
                style={{ fontSize: 13, fontWeight: 600, color: BLUE, textDecoration: 'none' }}>
                View public profile →
              </Link>
            </div>
          </div>
        </div>
        <button onClick={() => setTab('postJob')} style={{ ...btn('primary'), fontSize: 14, padding: '10px 22px', borderRadius: 6 }}>
          + Post a Job
        </button>
      </div>

      {/* ── Toast ── */}
      {msg && (
        <div style={{ background: msgType === 'error' ? '#fee2e2' : msgType === 'success' ? '#dcfce7' : '#dbeafe', color: msgType === 'error' ? '#dc2626' : msgType === 'success' ? '#15803d' : '#1e40af', padding: '10px 16px', borderRadius: 8, marginBottom: 16, fontSize: 14, fontWeight: 500 }}>
          {msg}
        </div>
      )}

      {/* ── Stat cards ── */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 24 }}>
        <StatCard label="Jobs Posted"      value={jobs.length}   color={BLUE} />
        <StatCard label="Active Jobs"       value={activeJobs}    color="#10b981" />
        <StatCard label="Total Applicants"  value={totalApps}     color="#8b5cf6" />
        <StatCard label="Pending Review"    value={pendingReview} color="#f59e0b" sub="across selected job" />
      </div>

      {/* ── Nav tabs ── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { key: 'dashboard',       label: 'Analytics'        },
          { key: 'myJobs',          label: 'My Jobs'           },
          { key: 'applicants',      label: 'Talent Pipeline'  },
          { key: 'findCandidates',  label: 'Find Candidates'  },
          { key: 'postJob',         label: 'Post Job'          },
        ].map(t => (
          <button key={t.key} style={pill(tab === t.key)} onClick={() => { setTab(t.key); if (t.key === 'myJobs') loadJobs(); }}>
            {t.label}{t.key === 'myJobs' ? ` (${jobs.length})` : ''}
          </button>
        ))}
      </div>

      {/* ════════════════════════════════════════════════════
          TAB: ANALYTICS
      ════════════════════════════════════════════════════ */}
      {tab === 'dashboard' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>

            {/* Top Jobs bar chart */}
            <div style={card()}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16 }}>My Jobs by Applicants <span style={{ fontSize: 12, color: '#888', fontWeight: 400 }}>(live recruiter data)</span></h3>
              {topJobs.length === 0
                ? <p style={{ color: '#999', textAlign: 'center', padding: 40 }}>No data yet</p>
                : (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={topJobs.slice(0, 8)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={0} angle={-15} textAnchor="end" height={50} />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="count" fill={BLUE} radius={[4, 4, 0, 0]} name="Applications" />
                    </BarChart>
                  </ResponsiveContainer>
                )}
            </div>

            {/* Jobs by status pie */}
            <div style={card()}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16 }}>Jobs by Status</h3>
              {jobs.length === 0
                ? <p style={{ color: '#999', textAlign: 'center', padding: 40 }}>No jobs yet</p>
                : (
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={[
                        { name: 'Open',   value: jobs.filter(j => j.status === 'open').length },
                        { name: 'Closed', value: jobs.filter(j => j.status !== 'open').length },
                      ]} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                        {['#10b981', '#ef4444'].map((c, i) => <Cell key={i} fill={c} />)}
                      </Pie>
                      <Legend />
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                )}
            </div>
          </div>

          {/* Section 8 required recruiter analytics */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
            <div style={card()}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16 }}>Top Jobs by Applications per Month</h3>
              {recruiterTopPerMonth.length === 0 ? (
                <p style={{ color: '#999', textAlign: 'center', padding: 40 }}>No monthly application data yet</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={recruiterTopPerMonth}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="applications" fill={BLUE} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div style={card()}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16 }}>Low Traction Jobs (Top 5 Fewest Applications)</h3>
              {recruiterLowTraction.length === 0 ? (
                <p style={{ color: '#999', textAlign: 'center', padding: 40 }}>No low-traction data yet</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={recruiterLowTraction} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis type="number" />
                    <YAxis dataKey="job" type="category" width={90} />
                    <Tooltip />
                    <Bar dataKey="applications" fill="#f59e0b" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
            <div style={card()}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16 }}>Clicks per Job Posting</h3>
              {recruiterClicks.length === 0 ? (
                <p style={{ color: '#999', textAlign: 'center', padding: 40 }}>No click data yet</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={recruiterClicks}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="job" tick={{ fontSize: 11 }} />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="clicks" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div style={card()}>
              <h3 style={{ margin: '0 0 12px', fontSize: 16 }}>Saved Jobs Trend (Daily / Weekly)</h3>
              {(recruiterSavesDaily.length === 0 && recruiterSavesWeekly.length === 0) ? (
                <p style={{ color: '#999', textAlign: 'center', padding: 40 }}>No saved-jobs trend data yet</p>
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={recruiterSavesDaily.length > 0 ? recruiterSavesDaily : recruiterSavesWeekly}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey={recruiterSavesDaily.length > 0 ? 'day' : 'week'} tick={{ fontSize: 11 }} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="count" stroke="#10b981" strokeWidth={2} dot={false} name="Saved Jobs" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div style={card({ marginBottom: 24 })}>
            <h3 style={{ margin: '0 0 12px', fontSize: 16 }}>City-wise Applications per Month (Selected Job)</h3>
            {recruiterCityMonthly.length === 0 ? (
              <p style={{ color: '#999', textAlign: 'center', padding: 40 }}>
                Select a job in Funnel section to view city-wise monthly applications
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={recruiterCityMonthly}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="applications" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Funnel section */}
          <div style={card({ marginBottom: 24 })}>
            <h3 style={{ margin: '0 0 14px', fontSize: 16 }}>Application Funnel — Select a Job</h3>
            <select onChange={e => loadApplicants(e.target.value)}
              style={{ padding: '8px 14px', border: '1px solid #ddd', borderRadius: 6, width: 320, marginBottom: 16, fontSize: 14 }}>
              <option value="">— select a job —</option>
              {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title}</option>)}
            </select>

            {funnelData.length > 0 && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 }}>
                {/* Funnel bar */}
                <div>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={funnelData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="name" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="value" fill="#10b981" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Applicant status pie */}
                <div>
                  <h4 style={{ margin: '0 0 8px', fontSize: 14, color: '#555' }}>Applicants by Status</h4>
                  {statusDist.length > 0
                    ? (
                      <ResponsiveContainer width="100%" height={220}>
                        <PieChart>
                          <Pie data={statusDist} cx="50%" cy="50%" outerRadius={75} dataKey="value">
                            {statusDist.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                          </Pie>
                          <Legend iconSize={10} />
                          <Tooltip />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : <p style={{ color: '#999', fontSize: 13 }}>No applicants yet</p>}
                </div>

                {/* Geo bar */}
                <div>
                  <h4 style={{ margin: '0 0 8px', fontSize: 14, color: '#555' }}>Geo Distribution</h4>
                  {geo.length > 0
                    ? (
                      <ResponsiveContainer width="100%" height={220}>
                        <BarChart data={geo.slice(0, 6)} layout="vertical">
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis type="number" />
                          <YAxis dataKey="city" type="category" width={110} tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Bar dataKey="count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : <p style={{ color: '#999', fontSize: 13 }}>No geo data yet</p>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════
          TAB: MY JOBS
      ════════════════════════════════════════════════════ */}
      {tab === 'myJobs' && (
        <div>
          {jobs.length === 0 && (
            <div style={{ textAlign: 'center', padding: 60, color: '#888' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📭</div>
              <p>No jobs posted yet.</p>
              <button onClick={() => setTab('postJob')} style={btn('primary')}>Post your first job</button>
            </div>
          )}
          {jobs.map(j => (
            <div key={j.job_id} style={{ ...card({ padding: 18, marginBottom: 12 }), display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                  <span style={{ fontWeight: 700, fontSize: 16 }}>{j.title}</span>
                  <span style={{ padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600, background: j.status === 'open' ? '#dcfce7' : '#fee2e2', color: j.status === 'open' ? '#15803d' : '#dc2626' }}>
                    {j.status === 'open' ? '● Open' : '● Closed'}
                  </span>
                </div>
                <p style={{ color: '#555', margin: '2px 0', fontSize: 14 }}>
                  {[j.city, j.state, j.country].filter(Boolean).join(', ') || 'Location TBD'}
                  &nbsp;·&nbsp; {j.work_mode} &nbsp;·&nbsp; {j.employment_type}
                </p>
                {j.industry && <p style={{ margin: '2px 0', fontSize: 13, color: '#888' }}>{j.industry}</p>}
                {(j.salary_min || j.salary_max) && (
                  <p style={{ margin: '2px 0', fontSize: 13, color: '#888' }}>
                    ${j.salary_min?.toLocaleString()} – ${j.salary_max?.toLocaleString()}
                  </p>
                )}
                <div style={{ display: 'flex', gap: 20, marginTop: 8 }}>
                  <span style={{ fontSize: 13, color: BLUE, fontWeight: 600 }}>{j.applicants_count || 0} applicants</span>
                  <span style={{ fontSize: 13, color: '#888' }}>{j.views_count || 0} views</span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0, marginLeft: 16 }}>
                <button onClick={() => { loadApplicants(j.job_id); setTab('applicants'); }} style={btn('outline')}>
                  View Applicants
                </button>
                {j.status === 'open' && (
                  <button onClick={() => handleCloseJob(j.job_id)}
                    style={{ ...btn('outline'), borderColor: '#dc2626', color: '#dc2626' }}>
                    Close Job
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ════════════════════════════════════════════════════
          TAB: TALENT PIPELINE (APPLICANTS)
      ════════════════════════════════════════════════════ */}
      {tab === 'applicants' && (
        <div>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center' }}>
            <span style={{ color: '#555', fontWeight: 500, fontSize: 14, whiteSpace: 'nowrap' }}>Select job:</span>
            <select onChange={e => loadApplicants(e.target.value)} value={selectedJob || ''}
              style={{ padding: '9px 14px', border: '1px solid #ddd', borderRadius: 6, flex: 1, fontSize: 14 }}>
              <option value="">— select a job —</option>
              {jobs.map(j => <option key={j.job_id} value={j.job_id}>{j.title}</option>)}
            </select>
          </div>

          {selectedJob && applicants.length === 0 && (
            <div style={{ textAlign: 'center', padding: 60, color: '#888' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🤷</div>
              <p>No applicants for this job yet.</p>
            </div>
          )}

          {!selectedJob && (
            <div style={{ textAlign: 'center', padding: 60, color: '#aaa' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>👆</div>
              <p>Select a job above to view its applicants.</p>
            </div>
          )}

          {applicants.map(a => (
            <ApplicantRow
              key={a.application_id}
              app={a}
              memberProfile={memberProfiles[a.member_id]}
              onStatus={handleStatusChange}
            />
          ))}
        </div>
      )}

      {/* ════════════════════════════════════════════════════
          TAB: FIND CANDIDATES
      ════════════════════════════════════════════════════ */}
      {tab === 'findCandidates' && (
        <div>
          <div style={card({ marginBottom: 20 })}>
            <h3 style={{ margin: '0 0 14px', fontSize: 16 }}>Search Candidates</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr auto', gap: 10, alignItems: 'end' }}>
              <div>
                <label style={{ fontSize: 12, color: '#666', fontWeight: 600 }}>Keyword (name / headline)</label>
                <input style={{ ...inp, marginBottom: 0, marginTop: 4 }} placeholder="e.g. Python Developer"
                  value={searchQuery.keyword} onChange={e => setSearchQuery(q => ({ ...q, keyword: e.target.value }))} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#666', fontWeight: 600 }}>Skill</label>
                <input style={{ ...inp, marginBottom: 0, marginTop: 4 }} placeholder="e.g. React, Kafka, ML"
                  value={searchQuery.skill} onChange={e => setSearchQuery(q => ({ ...q, skill: e.target.value }))} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#666', fontWeight: 600 }}>Location</label>
                <input style={{ ...inp, marginBottom: 0, marginTop: 4 }} placeholder="e.g. San Francisco"
                  value={searchQuery.location} onChange={e => setSearchQuery(q => ({ ...q, location: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()} />
              </div>
              <button onClick={handleSearch} style={{ ...btn('primary'), padding: '10px 24px', borderRadius: 6, height: 40 }}>Search</button>
            </div>
          </div>

          {searchDone && candidates.length === 0 && (
            <div style={{ textAlign: 'center', padding: 60, color: '#888' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🔎</div>
              <p>No candidates found. Try different filters.</p>
            </div>
          )}

          {candidates.length > 0 && (
            <div>
              <p style={{ fontSize: 14, color: '#555', marginBottom: 12 }}>{candidates.length} candidate{candidates.length !== 1 ? 's' : ''} found</p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                {candidates.map(m => <CandidateCard key={m.member_id} member={m} />)}
              </div>
            </div>
          )}

          {!searchDone && (
            <div style={{ textAlign: 'center', padding: 60, color: '#aaa' }}>
              <p>Search by skill, keyword, or location to find candidates.</p>
            </div>
          )}
        </div>
      )}

      {/* ════════════════════════════════════════════════════
          TAB: POST JOB
      ════════════════════════════════════════════════════ */}
      {tab === 'postJob' && (
        <div style={{ maxWidth: 640 }}>
          <div style={card()}>
            <h3 style={{ margin: '0 0 20px', fontSize: 18 }}>Post a New Job</h3>
            <input placeholder="Job title *" style={inp} value={newJob.title || ''} onChange={e => setNewJob(j => ({ ...j, title: e.target.value }))} />
            <textarea placeholder="Job description" style={{ ...inp, height: 110, resize: 'vertical' }} value={newJob.description || ''} onChange={e => setNewJob(j => ({ ...j, description: e.target.value }))} />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, color: '#666', fontWeight: 600, display: 'block', marginBottom: 4 }}>Employment Type</label>
                <select style={{ ...inp }} value={newJob.employment_type || ''} onChange={e => setNewJob(j => ({ ...j, employment_type: e.target.value }))}>
                  <option value="">Select type</option>
                  {['Full-time', 'Part-time', 'Contract', 'Internship'].map(t => <option key={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#666', fontWeight: 600, display: 'block', marginBottom: 4 }}>Work Mode</label>
                <select style={{ ...inp }} value={newJob.work_mode || ''} onChange={e => setNewJob(j => ({ ...j, work_mode: e.target.value }))}>
                  <option value="">Select mode</option>
                  {['onsite', 'remote', 'hybrid'].map(t => <option key={t}>{t}</option>)}
                </select>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              <input placeholder="City"    style={inp} value={newJob.city    || ''} onChange={e => setNewJob(j => ({ ...j, city: e.target.value }))} />
              <input placeholder="State"   style={inp} value={newJob.state   || ''} onChange={e => setNewJob(j => ({ ...j, state: e.target.value }))} />
              <input placeholder="Country" style={inp} value={newJob.country || ''} onChange={e => setNewJob(j => ({ ...j, country: e.target.value }))} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, color: '#666', fontWeight: 600, display: 'block', marginBottom: 4 }}>Salary Min (USD)</label>
                <input type="number" placeholder="e.g. 80000" style={inp} value={newJob.salary_min || ''} onChange={e => setNewJob(j => ({ ...j, salary_min: +e.target.value }))} />
              </div>
              <div>
                <label style={{ fontSize: 12, color: '#666', fontWeight: 600, display: 'block', marginBottom: 4 }}>Salary Max (USD)</label>
                <input type="number" placeholder="e.g. 120000" style={inp} value={newJob.salary_max || ''} onChange={e => setNewJob(j => ({ ...j, salary_max: +e.target.value }))} />
              </div>
            </div>
            <input placeholder="Industry (e.g. Technology, Finance)" style={inp} value={newJob.industry || ''} onChange={e => setNewJob(j => ({ ...j, industry: e.target.value }))} />
            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={handleCreateJob} style={{ ...btn('primary'), fontSize: 15, padding: '12px 32px', borderRadius: 6 }}>
                Post Job
              </button>
              <button onClick={() => setNewJob({})} style={{ ...btn('outline'), padding: '12px 20px', borderRadius: 6 }}>
                Clear
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
