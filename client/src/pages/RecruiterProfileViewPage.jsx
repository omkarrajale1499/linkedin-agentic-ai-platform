import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api/apiClient';

function Avatar({ name, photo, size = 120 }) {
  if (photo) {
    return (
      <img
        src={photo}
        alt=""
        style={{ width: size, height: size, borderRadius: '50%', objectFit: 'cover', display: 'block' }}
      />
    );
  }
  const initials = (name || 'R').split(' ').filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: 'linear-gradient(135deg,#0a66c2,#0891b2)',
      color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontWeight: 700, fontSize: size * 0.35,
    }}>{initials}</div>
  );
}

function parseHiringHighlights(raw) {
  if (raw == null || raw === '') return [];
  if (Array.isArray(raw)) return raw.filter(Boolean);
  if (typeof raw === 'string') {
    try {
      const p = JSON.parse(raw);
      return Array.isArray(p) ? p.filter(Boolean) : [];
    } catch {
      return [];
    }
  }
  return [];
}

function SectionCard({ title, children }) {
  return (
    <div style={{
      background: 'white', borderRadius: 12, border: '1px solid #e5e7eb',
      boxShadow: '0 1px 3px rgba(0,0,0,0.06)', padding: '20px 24px',
    }}>
      <h2 style={{
        margin: '0 0 16px', fontSize: 19, fontWeight: 700, color: '#111827',
      }}>{title}</h2>
      {children}
    </div>
  );
}

export default function RecruiterProfileViewPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const sessionRecruiterId = localStorage.getItem('recruiter_id') || '';
  const recruiterId = searchParams.get('recruiter_id') || sessionRecruiterId;
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!recruiterId) {
      setError('No recruiter selected');
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await api.post('/recruiters/get', { recruiter_id: recruiterId });
        if (!cancelled) setData(r.data);
      } catch {
        if (!cancelled) setError('Could not load this profile.');
      }
    })();
    return () => { cancelled = true; };
  }, [recruiterId]);

  const specialtyChips = useMemo(() => {
    if (!data?.specialties) return [];
    return data.specialties.split(',').map(s => s.trim()).filter(Boolean);
  }, [data]);

  const highlights = useMemo(() => parseHiringHighlights(data?.hiring_highlights), [data]);

  if (!recruiterId) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: 40, textAlign: 'center', color: '#6b7280' }}>
        Missing recruiter id. <Link to="/connections" style={{ color: '#0a66c2' }}>Back to network</Link>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: 40, textAlign: 'center' }}>
        <p style={{ color: '#b91c1c', marginBottom: 16 }}>{error}</p>
        <button type="button" onClick={() => navigate(-1)}
          style={{ padding: '8px 20px', border: '1px solid #d1d5db', borderRadius: 20, background: 'white', cursor: 'pointer', fontWeight: 600 }}>
          Go back
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: 48, textAlign: 'center', color: '#6b7280' }}>
        Loading profile…
      </div>
    );
  }

  const displayName = `${data.first_name || ''} ${data.last_name || ''}`.trim() || 'Recruiter';
  const headline = data.headline || [data.company_industry, data.role].filter(Boolean).join(' · ') || 'Talent partner';

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: '24px 16px 48px' }}>
      <div style={{ marginBottom: 16 }}>
        <button type="button" onClick={() => navigate(-1)}
          style={{ background: 'none', border: 'none', color: '#0a66c2', cursor: 'pointer', fontWeight: 600, fontSize: 14, padding: 0 }}>
          ← Back
        </button>
      </div>

      <div style={{
        background: 'white', borderRadius: 12, border: '1px solid #e5e7eb',
        boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden', marginBottom: 12,
      }}>
        <div style={{ height: 96, background: 'linear-gradient(90deg,#1e3a5f,#0a66c2)' }} />
        <div style={{ padding: '0 24px 24px', marginTop: -56 }}>
          <Avatar name={displayName} photo={data.profile_photo_url} size={112} />
          <h1 style={{ margin: '16px 0 6px', fontSize: 26, fontWeight: 700, color: '#111' }}>{displayName}</h1>
          <p style={{ margin: 0, fontSize: 16, color: '#1f2937', fontWeight: 600, lineHeight: 1.35 }}>
            {headline}
          </p>
          {data.location ? (
            <p style={{ margin: '10px 0 0', fontSize: 14, color: '#4b5563' }}>{data.location}</p>
          ) : null}
          <span style={{
            display: 'inline-block', marginTop: 14, padding: '4px 12px', borderRadius: 20,
            fontSize: 12, fontWeight: 700, background: '#e8f0fe', color: '#0a66c2',
          }}>
            Recruiter
          </span>
        </div>
      </div>

      {(data.company_name || data.company_industry || data.company_size) ? (
        <SectionCard title="Organization">
          {data.company_name ? (
            <p style={{ margin: '0 0 6px', fontSize: 17, fontWeight: 700, color: '#111827' }}>
              {data.company_name}
            </p>
          ) : null}
          <div style={{ fontSize: 15, color: '#374151', lineHeight: 1.5 }}>
            {data.company_industry ? <span>{data.company_industry}</span> : null}
            {data.company_industry && data.company_size ? (
              <span style={{ color: '#9ca3af', margin: '0 8px' }}>·</span>
            ) : null}
            {data.company_size ? (
              <span>Company size: {data.company_size}</span>
            ) : null}
          </div>
        </SectionCard>
      ) : null}

      {data.about ? (
        <div style={{ marginTop: 12 }}>
          <SectionCard title="About">
            <p style={{
              margin: 0, fontSize: 15, color: '#374151', lineHeight: 1.65, whiteSpace: 'pre-wrap',
            }}>
              {data.about}
            </p>
          </SectionCard>
        </div>
      ) : null}

      {specialtyChips.length ? (
        <div style={{ marginTop: 12 }}>
          <SectionCard title="Hiring focus">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {specialtyChips.map(s => (
                <span key={s} style={{
                  padding: '6px 12px', borderRadius: 20, fontSize: 13, fontWeight: 600,
                  background: '#f3f4f6', color: '#1f2937', border: '1px solid #e5e7eb',
                }}>{s}</span>
              ))}
            </div>
          </SectionCard>
        </div>
      ) : null}

      {highlights.length ? (
        <div style={{ marginTop: 12 }}>
          <SectionCard title="Highlights">
            <ul style={{ margin: 0, paddingLeft: 20, color: '#374151', fontSize: 15, lineHeight: 1.65 }}>
              {highlights.map((h, i) => (
                <li key={i} style={{ marginBottom: 10 }}>{h}</li>
              ))}
            </ul>
          </SectionCard>
        </div>
      ) : null}

      {!data.about && !specialtyChips.length && !highlights.length ? (
        <div style={{ marginTop: 12 }}>
          <SectionCard title="About">
            <p style={{ margin: 0, fontSize: 14, color: '#6b7280' }}>
              This recruiter has not added a profile summary yet.
            </p>
          </SectionCard>
        </div>
      ) : null}

      <p style={{ marginTop: 24, fontSize: 13, color: '#9ca3af', textAlign: 'center' }}>
        <Link to="/connections" style={{ color: '#0a66c2' }}>My Network</Link>
      </p>
    </div>
  );
}
