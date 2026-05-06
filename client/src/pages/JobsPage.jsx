import { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { searchJobs, getJob, saveJob, unsaveJob, savedJobs } from '../api/jobApi';
import { submitApplication, applicationsByMember } from '../api/applicationApi';
import { uuid } from '../api/apiClient';
import api from '../api/apiClient';

// ─────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────

// Returns a colored circle with the first letter of the company name
function CompanyLogo({ name, size = 44 }) {
  const colors = ['#0a66c2','#1a73e8','#4f46e5','#0891b2','#059669','#d97706','#dc2626'];
  const color  = colors[(name || 'A').charCodeAt(0) % colors.length];
  return (
    <div style={{
      width: size, height: size, borderRadius: 10,
      background: color, color: 'white',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontWeight: 700, fontSize: size * 0.4, flexShrink: 0,
    }}>
      {(name || '?')[0].toUpperCase()}
    </div>
  );
}

// Formats salary range → "$160K – $220K"
function salary(min, max) {
  if (!min) return null;
  const fmt = n => `$${Math.round(+n / 1000)}K`;
  return `${fmt(min)} – ${fmt(max)}`;
}

// Relative date → "3 days ago"
function timeAgo(dateStr) {
  const days = Math.floor((Date.now() - new Date(dateStr)) / 86400000);
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  return `${days} days ago`;
}

// Small pill badge
function Badge({ children, color = '#e0eaff', text = '#1e40af' }) {
  return (
    <span style={{
      background: color, color: text,
      padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 500,
      whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

// ─────────────────────────────────────────────
//  COMPANY NAME MAP  (job → company)
//  The API returns recruiter data on the job;
//  we store company name from JOBS seed data.
// ─────────────────────────────────────────────
const COMPANY_BY_TITLE = {
  'Senior Software Engineer':   'Google',
  'Machine Learning Engineer':  'Google',
  'Site Reliability Engineer':  'Google',
  'Backend Engineer – Instagram':'Meta',
  'Data Engineer – Analytics':  'Meta',
  'Frontend Engineer – React':  'Meta',
  'Cloud Solutions Architect':  'Microsoft',
  'Software Engineer – Azure':  'Microsoft',
  'DevOps Engineer':            'Microsoft',
  'Product Manager – AI':       'Microsoft',
};

// ─────────────────────────────────────────────
//  MAIN COMPONENT
// ─────────────────────────────────────────────
function JobsSidebarModule({ title, children, actionLabel, onAction }) {
  return (
    <section style={{ background: 'white', borderRadius: 12, border: '1px solid #e2e8f0', padding: 14, boxShadow: '0 1px 6px rgba(15,23,42,0.04)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h4 style={{ margin: 0, fontSize: 14, color: '#0f172a' }}>{title}</h4>
        {actionLabel && <button onClick={onAction} style={{ border: 'none', background: 'transparent', color: '#0a66c2', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>{actionLabel}</button>}
      </div>
      {children}
    </section>
  );
}

function JobPreviewCard({ job, onOpen }) {
  const company = job.company_name || COMPANY_BY_TITLE[job.title] || 'Company';
  return (
    <button onClick={() => onOpen(job)} style={{ width: '100%', textAlign: 'left', border: '1px solid #e2e8f0', background: '#fff', borderRadius: 12, padding: 12, cursor: 'pointer' }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
        <CompanyLogo name={company} size={38} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{job.title}</div>
          <div style={{ marginTop: 2, fontSize: 12, color: '#334155', fontWeight: 600 }}>{company}</div>
          <div style={{ marginTop: 4, fontSize: 12, color: '#64748b' }}>{job.city}, {job.state} · {job.work_mode}</div>
          <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <Badge>{job.employment_type}</Badge>
            <Badge color="#f9fafb" text="#64748b">{timeAgo(job.posted_at)}</Badge>
          </div>
        </div>
      </div>
    </button>
  );
}

function JobRecommendationSection({ title, subtitle, jobs, onOpenJob, onShowAll }) {
  return (
    <section style={{ background: 'white', borderRadius: 14, border: '1px solid #e2e8f0', padding: 16, boxShadow: '0 2px 12px rgba(15,23,42,0.04)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12, gap: 12 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 18, color: '#0f172a' }}>{title}</h3>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: '#64748b' }}>{subtitle}</p>
        </div>
        <button onClick={onShowAll} style={{ height: 34, padding: '0 14px', borderRadius: 999, border: '1px solid #bfdbfe', background: '#f8fbff', color: '#0a66c2', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>
          Show all
        </button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
        {jobs.map(job => <JobPreviewCard key={job.job_id} job={job} onOpen={onOpenJob} />)}
      </div>
    </section>
  );
}

export default function JobsPage() {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [savedCount, setSavedCount] = useState(0);
  const member_id = localStorage.getItem('member_id');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const res = await searchJobs({ page: 1, limit: 36 });
        setJobs(res.data.results || []);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    if (!member_id) return;
    savedJobs(member_id).then(r => setSavedCount((r.data.results || []).length)).catch(() => {});
  }, [member_id]);

  const openJob = (job) => navigate('/jobs/browse', { state: { jobId: job.job_id } });
  const showAll = (presetFilters = {}) => navigate('/jobs/browse', { state: { filters: presetFilters } });

  const preferenceJobs = jobs.filter(job => ['remote', 'hybrid'].includes((job.work_mode || '').toLowerCase())).slice(0, 4);
  const activityJobs = [...jobs].sort((a, b) => (b.applicants_count || 0) - (a.applicants_count || 0)).slice(0, 4);
  const featuredJobs = [...jobs].sort((a, b) => new Date(b.posted_at || 0) - new Date(a.posted_at || 0)).slice(0, 4);
  const userName = localStorage.getItem('user_name') || 'Member';

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '280px minmax(0, 1fr)', gap: 16 }}>
      <aside style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <JobsSidebarModule title="Profile Summary">
          <div style={{ fontSize: 13, color: '#334155', lineHeight: 1.5 }}>
            <div style={{ fontWeight: 700, color: '#0f172a' }}>{userName}</div>
            <div>Keep your profile fresh for better matches.</div>
          </div>
        </JobsSidebarModule>
        <JobsSidebarModule title="Preferences" actionLabel="Update" onAction={() => showAll({ work_mode: 'remote' })}>
          <p style={{ margin: 0, fontSize: 12, color: '#64748b', lineHeight: 1.5 }}>Work mode, role, and level settings influence every recommendation.</p>
        </JobsSidebarModule>
        <JobsSidebarModule title="Job Tracker">
          <div style={{ fontSize: 12, color: '#64748b' }}>Saved jobs: <strong style={{ color: '#0f172a' }}>{savedCount}</strong></div>
          <button onClick={() => showAll({})} style={{ marginTop: 10, border: '1px solid #cbd5e1', borderRadius: 999, height: 32, padding: '0 12px', background: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
            View tracked jobs
          </button>
        </JobsSidebarModule>
      </aside>

      <main style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 14, padding: 16 }}>
          <h2 style={{ margin: 0, fontSize: 24, color: '#0f172a' }}>Discover jobs for you</h2>
          <p style={{ margin: '6px 0 0', color: '#64748b', fontSize: 14 }}>Curated recommendations based on your profile, activity, and market demand.</p>
        </div>
        {loading ? (
          <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 14, padding: 18, color: '#64748b', fontSize: 14 }}>Loading recommendations...</div>
        ) : (
          <>
            <JobRecommendationSection title="Jobs based on your preferences" subtitle="Matches aligned with your preferred work setup." jobs={preferenceJobs} onOpenJob={openJob} onShowAll={() => showAll({ work_mode: 'remote' })} />
            <JobRecommendationSection title="Jobs based on your activity" subtitle="Roles many candidates like you are exploring." jobs={activityJobs} onOpenJob={openJob} onShowAll={() => showAll({})} />
            <JobRecommendationSection title="Featured recommendations" subtitle="Fresh opportunities from top employers." jobs={featuredJobs} onOpenJob={openJob} onShowAll={() => showAll({})} />
          </>
        )}
      </main>
    </div>
  );
}

export function JobsBrowsePage() {
  const location = useLocation();
  const initialFilters = location.state?.filters;
  const initialJobId = location.state?.jobId;
  const [filters, setFilters] = useState({ keyword: '', location: '', employment_type: '', seniority_level: '', work_mode: '', industry: '' });
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [toast, setToast] = useState({ text: '', type: 'success' });
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState('');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [totalJobs, setTotalJobs] = useState(0);
  const [myApps, setMyApps] = useState([]);
  const [savedIds, setSavedIds] = useState([]);
  const [showSavedOnly, setShowSavedOnly] = useState(false);
  const [hoveredJobId, setHoveredJobId] = useState(null);
  const [showCompactDetailBar, setShowCompactDetailBar] = useState(false);
  const [compactBarThreshold, setCompactBarThreshold] = useState(180);
  const detailScrollRef = useRef(null);
  const largeHeaderRef = useRef(null);
  const member_id = localStorage.getItem('member_id');

  useEffect(() => {
    const merged = initialFilters ? { ...filters, ...initialFilters } : filters;
    if (initialFilters) setFilters(merged);
    handleSearch(1, merged);
  }, []);

  useEffect(() => {
    if (!member_id) return;
    savedJobs(member_id).then(r => setSavedIds((r.data.results || []).map(j => j.job_id))).catch(() => {});
  }, [member_id]);

  useEffect(() => {
    if (!initialJobId || jobs.length === 0) return;
    handleView(initialJobId);
  }, [initialJobId, jobs.length]);

  useEffect(() => {
    const headerHeight = largeHeaderRef.current?.offsetHeight || 180;
    setCompactBarThreshold(Math.max(80, headerHeight - 52));
    setShowCompactDetailBar(false);
    if (detailScrollRef.current) detailScrollRef.current.scrollTop = 0;
  }, [selected]);

  const set = (k, v) => setFilters(f => ({ ...f, [k]: v }));
  const showToast = (text, type = 'success') => {
    setToast({ text, type });
    setTimeout(() => setToast({ text: '', type: 'success' }), 3500);
  };

  const handleSearch = async (p = 1, overrideFilters, options = {}) => {
    const savedOnly = options.savedOnly ?? showSavedOnly;
    if (savedOnly && member_id) {
      setLoading(true);
      try {
        const r = await savedJobs(member_id);
        setJobs(r.data.results || []);
        setHasMore(false);
        setPage(1);
      } catch (e) {
        showToast('Failed to load saved jobs: ' + e.message, 'error');
      }
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const payload = { ...(overrideFilters !== undefined ? overrideFilters : filters), page: p, limit: 20 };
      Object.keys(payload).forEach(k => { if (!payload[k]) delete payload[k]; });
      const res = await searchJobs(payload);
      const results = res.data.results || [];
      const total = res.data.total ?? results.length;
      setJobs(p === 1 ? results : prev => [...prev, ...results]);
      setPage(p);
      setTotalJobs(total);
      setHasMore(results.length === 20 && (p * 20) < total);
    } catch (e) {
      showToast('Search failed: ' + e.message, 'error');
    }
    setLoading(false);
  };

  const handleView = async (job_id) => {
    setApplyError('');
    try {
      const res = await getJob(job_id);
      setSelected(res.data);
      if (member_id) applicationsByMember(member_id).then(r => setMyApps((r.data.results || []).map(a => a.job_id))).catch(() => {});
    } catch (_) {
      showToast('Error loading job details', 'error');
    }
  };

  const handleApply = async () => {
    if (!member_id) { setApplyError('Please sign in to apply.'); return; }
    if (!selected) return;
    setApplying(true);
    setApplyError('');
    try {
      let resume_text = null;
      let resume_url = null;
      try {
        const profile = await api.post('/members/get', { member_id });
        resume_text = profile.data.resume_text || null;
        resume_url = profile.data.resume_url || null;
      } catch (_) {}
      await submitApplication({ job_id: selected.job_id, member_id, resume_text, resume_url, idempotency_key: uuid() });
      setMyApps(prev => [...prev, selected.job_id]);
      showToast('Application submitted successfully');
    } catch (e) {
      setApplyError(e.response?.data?.detail || e.response?.data?.error || 'Apply failed. Please try again.');
    } finally {
      setApplying(false);
    }
  };

  const handleSaveToggle = async (job_id) => {
    if (!member_id) { showToast('Please sign in to save jobs.', 'error'); return; }
    const isSaved = savedIds.includes(job_id);
    try {
      if (isSaved) {
        await unsaveJob(member_id, job_id);
        setSavedIds(prev => prev.filter(id => id !== job_id));
      } else {
        await saveJob(member_id, job_id);
        setSavedIds(prev => [...prev, job_id]);
      }
      if (showSavedOnly) {
        const r = await savedJobs(member_id);
        setJobs(r.data.results || []);
      }
    } catch (e) {
      showToast(e.response?.data?.detail || e?.response?.data?.error || 'Save action failed', 'error');
    }
  };

  const alreadyApplied = selected && myApps.includes(selected.job_id);
  const selectedSaved = selected && savedIds.includes(selected.job_id);
  const companyName = job => job.company_name || COMPANY_BY_TITLE[job.title] || 'Company';
  const compactMetaLine = selected ? `${companyName(selected)} · ${selected.city}, ${selected.state}` : '';

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      {toast.text && <div style={{ position: 'fixed', top: 70, right: 24, zIndex: 999, background: toast.type === 'error' ? '#fef2f2' : '#f0fdf4', border: `1px solid ${toast.type === 'error' ? '#fecaca' : '#bbf7d0'}`, color: toast.type === 'error' ? '#dc2626' : '#15803d', padding: '12px 20px', borderRadius: 8 }}>{toast.text}</div>}
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 26, color: '#0f172a', fontWeight: 700 }}>Find your next role</h2>
        <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 10 }}>
          <p style={{ margin: 0, color: '#64748b', fontSize: 14 }}>
            {totalJobs > 0 ? `${jobs.length} of ${totalJobs.toLocaleString()} jobs` : jobs.length > 0 ? `${jobs.length} jobs` : 'Search across open roles'}
          </p>
          {member_id && <span style={{ background: '#eff6ff', color: '#1e40af', padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>Saved Jobs: {savedIds.length}</span>}
        </div>
      </div>

      <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e2e8f0', padding: 16, marginBottom: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr auto auto', gap: 8, alignItems: 'center' }}>
          <input placeholder="Job title, skill, or keyword" value={filters.keyword} onChange={e => set('keyword', e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch(1)} style={searchInputStyle({ height: 40 })} />
          <input placeholder="City or state" value={filters.location} onChange={e => set('location', e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch(1)} style={searchInputStyle({ height: 40 })} />
          <select value={filters.seniority_level} onChange={e => set('seniority_level', e.target.value)} style={selectStyle({ height: 40, borderRadius: 999 })}>
            <option value="">Level</option>
            {['Internship', 'Entry level', 'Associate', 'Mid-Senior level', 'Director', 'Executive'].map(t => <option key={t}>{t}</option>)}
          </select>
          <button onClick={() => handleSearch(1)} disabled={loading} style={{ height: 40, padding: '0 20px', background: '#0a66c2', color: 'white', border: 'none', borderRadius: 999, cursor: 'pointer' }}>{loading ? 'Searching…' : 'Search'}</button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          {['Full-time', 'Part-time', 'Contract', 'Temporary', 'Volunteer', 'Internship'].map(type => <button key={type} onClick={() => set('employment_type', filters.employment_type === type ? '' : type)} style={chipStyle(filters.employment_type === type)}>{type}</button>)}
          {['onsite', 'remote', 'hybrid'].map(mode => <button key={mode} onClick={() => set('work_mode', filters.work_mode === mode ? '' : mode)} style={chipStyle(filters.work_mode === mode)}>{mode.charAt(0).toUpperCase() + mode.slice(1)}</button>)}
          <input placeholder="Industry" value={filters.industry} onChange={e => set('industry', e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch(1)} style={searchInputStyle({ minWidth: 140, width: 180, height: 34 })} />
          {member_id && <button onClick={() => { const next = !showSavedOnly; setShowSavedOnly(next); handleSearch(1, filters, { savedOnly: next }); }} style={chipStyle(showSavedOnly)}>{showSavedOnly ? 'Showing Saved' : 'Saved Jobs'}</button>}
          {(filters.keyword || filters.location || filters.employment_type || filters.seniority_level || filters.work_mode || filters.industry || showSavedOnly) && <button onClick={() => { const cleared = { keyword: '', location: '', employment_type: '', seniority_level: '', work_mode: '', industry: '' }; setFilters(cleared); setShowSavedOnly(false); handleSearch(1, cleared); }} style={{ height: 34, padding: '0 12px', background: '#fff', color: '#475569', border: '1px solid #cbd5e1', borderRadius: 999, cursor: 'pointer', fontSize: 12, fontWeight: 500 }}>Clear</button>}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'stretch', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <div style={{ flex: '0 0 380px', minWidth: 0, height: '100%', overflowY: 'auto', paddingRight: 4 }}>
          {jobs.map(job => {
            const isActive = selected?.job_id === job.job_id;
            const company = companyName(job);
            const isSaved = savedIds.includes(job.job_id);
            return (
              <div key={job.job_id} onClick={() => handleView(job.job_id)} onMouseEnter={() => setHoveredJobId(job.job_id)} onMouseLeave={() => setHoveredJobId(null)} style={{ background: isActive ? '#f8fbff' : hoveredJobId === job.job_id ? '#fcfdff' : 'white', borderRadius: 10, padding: 16, marginBottom: 10, cursor: 'pointer', border: `1px solid ${isActive ? '#93c5fd' : '#e5e7eb'}` }}>
                <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
                  <CompanyLogo name={company} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 15, color: '#111', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{job.title}</div>
                    <div style={{ color: '#0a66c2', fontSize: 13, fontWeight: 500 }}>{company}</div>
                  </div>
                </div>
                <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>📍 {job.city}, {job.state} · {job.work_mode}</div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}><Badge>{job.employment_type}</Badge>{salary(job.salary_min, job.salary_max) && <Badge color="#f0fdf4" text="#15803d">{salary(job.salary_min, job.salary_max)}</Badge>}</div>
                {member_id && <button onClick={(e) => { e.stopPropagation(); handleSaveToggle(job.job_id); }} style={{ marginTop: 8, padding: '6px 10px', borderRadius: 14, border: '1px solid #d1d5db', background: isSaved ? '#eff6ff' : 'white', color: isSaved ? '#1e40af' : '#374151', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>{isSaved ? '★ Saved' : '☆ Save'}</button>}
              </div>
            );
          })}
          {hasMore && <button onClick={() => handleSearch(page + 1)} disabled={loading} style={{ width: '100%', padding: 12, border: '1px solid #0a66c2', color: '#0a66c2', background: 'white', borderRadius: 8, fontWeight: 600, cursor: 'pointer' }}>{loading ? 'Loading…' : `Load more jobs (${totalJobs - jobs.length} remaining)`}</button>}
        </div>

        <div style={{ flex: 1, minWidth: 0, height: '100%', overflow: 'hidden', paddingRight: 4 }}>
          {!selected ? (
            <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e5e7eb', padding: '80px 20px', textAlign: 'center', color: '#9ca3af' }}>
              <div style={{ fontSize: 52, marginBottom: 12 }}>📋</div>
              <p style={{ margin: 0, fontSize: 15 }}>Select a job to see full details</p>
            </div>
          ) : (
            <div style={{ background: 'white', borderRadius: 10, border: '1px solid #e5e7eb', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div ref={detailScrollRef} onScroll={(e) => setShowCompactDetailBar(e.currentTarget.scrollTop > compactBarThreshold)} style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
                <div style={{ position: 'sticky', top: 0, zIndex: 5, marginBottom: -64, height: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: 'rgba(255,255,255,0.98)', opacity: showCompactDetailBar ? 1 : 0 }}>
                  <div style={{ minWidth: 0, flex: 1, paddingRight: 10 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{selected.title}</div>
                    <div style={{ fontSize: 12, color: '#64748b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{compactMetaLine}</div>
                  </div>
                </div>
                <div ref={largeHeaderRef} style={{ padding: '24px 24px 20px', borderBottom: '1px solid #f3f4f6' }}>
                  <h3 style={{ margin: 0, fontSize: 20, color: '#111', fontWeight: 700 }}>{selected.title}</h3>
                  <p style={{ margin: '6px 0 0', color: '#6b7280', fontSize: 14 }}>📍 {selected.city}, {selected.state}, {selected.country} · {selected.work_mode}</p>
                </div>
                <div style={{ padding: 24 }}>
                  {member_id && <button onClick={() => handleSaveToggle(selected.job_id)} style={{ width: '100%', padding: '10px 0', marginBottom: 10, background: selectedSaved ? '#eff6ff' : 'white', color: selectedSaved ? '#1e40af' : '#374151', border: '1px solid #d1d5db', borderRadius: 8 }}>{selectedSaved ? '★ Saved' : '☆ Save Job'}</button>}
                  <button onClick={handleApply} disabled={alreadyApplied || selected.status !== 'open' || applying} style={{ width: '100%', padding: '13px 0', background: alreadyApplied ? '#dcfce7' : selected.status !== 'open' ? '#e5e7eb' : '#0a66c2', color: alreadyApplied ? '#15803d' : selected.status !== 'open' ? '#9ca3af' : 'white', border: 'none', borderRadius: 8 }}>
                    {alreadyApplied ? '✓ Applied' : applying ? 'Submitting…' : selected.status !== 'open' ? 'Position Closed' : 'Apply Now'}
                  </button>
                  {applyError && <div style={{ marginTop: 10, padding: '10px 14px', borderRadius: 6, background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626' }}>⚠ {applyError}</div>}
                  <div style={{ marginTop: 20 }}>
                    <h4 style={{ margin: '0 0 10px', fontSize: 14, color: '#111', fontWeight: 600 }}>About the Role</h4>
                    <p style={{ color: '#374151', fontSize: 14, lineHeight: 1.7, margin: 0, whiteSpace: 'pre-wrap' }}>{selected.description}</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Shared style helpers ──────────────────────────────────────────────────────
function searchInputStyle(extra = {}) {
  return {
    width: '100%', padding: '10px 12px', border: '1px solid #e5e7eb',
    borderRadius: 6, fontSize: 14, boxSizing: 'border-box',
    outline: 'none', color: '#111', background: '#fafafa',
    ...extra,
  };
}

function selectStyle(extra = {}) {
  return {
    padding: '10px 12px', border: '1px solid #dbe2ea', borderRadius: 8,
    fontSize: 14, background: 'white', cursor: 'pointer', color: '#374151',
    minWidth: 120,
    ...extra,
  };
}

function chipStyle(active) {
  return {
    height: 34,
    padding: '0 12px',
    borderRadius: 999,
    border: `1px solid ${active ? '#93c5fd' : '#dbe2ea'}`,
    background: active ? '#eff6ff' : '#fff',
    color: active ? '#0a66c2' : '#475569',
    fontSize: 12,
    fontWeight: active ? 600 : 500,
    cursor: 'pointer',
  };
}
