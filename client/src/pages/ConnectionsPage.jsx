import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { listConnections, sendRequest, acceptRequest, rejectRequest, pendingRequests, sentRequests } from '../api/connectionApi';
import api, { uuid } from '../api/apiClient';

// Avatar circle
function Avatar({ name = '', size = 48, color = '#0a66c2' }) {
  const letters = name.split(' ').filter(Boolean).map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?';
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', background: color,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: 'white', fontWeight: 700, fontSize: size * 0.35, flexShrink: 0,
    }}>
      {letters}
    </div>
  );
}

const COLORS = ['#0a66c2', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444', '#06b6d4'];

function Toast({ msg, onClose }) {
  useEffect(() => { if (msg) { const t = setTimeout(onClose, 3000); return () => clearTimeout(t); } }, [msg, onClose]);
  if (!msg) return null;
  return (
    <div style={{
      position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
      background: '#111', color: 'white', padding: '12px 24px', borderRadius: 8,
      fontSize: 14, fontWeight: 500, zIndex: 9999, boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
    }}>
      {msg}
    </div>
  );
}

export default function ConnectionsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const member_id = localStorage.getItem('member_id') || '';
  const recruiter_id = localStorage.getItem('recruiter_id') || '';
  const user_id = member_id || recruiter_id;

  const [tab,         setTab]         = useState(() => searchParams.get('tab') === 'find' ? 'find' : 'myConnections');
  const [connections, setConnections] = useState([]);
  const [pending,     setPending]     = useState([]);
  const [sent,        setSent]        = useState([]);
  const [sentRequestsList, setSentRequestsList] = useState([]);
  const [searchRes,   setSearchRes]   = useState([]);
  const [keyword,     setKeyword]     = useState(() => searchParams.get('q') || '');
  const [memberCache, setMemberCache] = useState({});
  const [toast,       setToast]       = useState('');
  const [loading,     setLoading]     = useState(false);

  // ── Fetch profile by ID — member or recruiter (cached) ──
  const fetchProfile = useCallback(async (id) => {
    if (!id || memberCache[id]) return memberCache[id];
    try {
      const r = await api.post('/members/get', { member_id: id });
      const row = { ...r.data, _type: 'member' };
      setMemberCache(prev => ({ ...prev, [id]: row }));
      return row;
    } catch {
      try {
        const rr = await api.post('/recruiters/get', { recruiter_id: id });
        const r = rr.data || {};
        const row = {
          member_id: id,
          first_name: r.first_name || r.company_name || 'Recruiter',
          last_name: r.last_name || '',
          headline: r.company_industry || r.company_name || 'Recruiter',
          city: '',
          _type: 'recruiter',
        };
        setMemberCache(prev => ({ ...prev, [id]: row }));
        return row;
      } catch {
        return null;
      }
    }
  }, [memberCache]);

  const memberName = (id) => {
    const m = memberCache[id];
    if (!m) return id.slice(0, 8) + '…';
    const full = `${m.first_name || ''} ${m.last_name || ''}`.trim();
    return full || id.slice(0, 8) + '…';
  };

  // ── Load connections ──
  const loadConnections = useCallback(async () => {
    try {
      const r = await listConnections(user_id);
      setConnections(r.data.results || []);
    } catch { /* ignore */ }
  }, [user_id]);

  // ── Load pending requests (sent TO me) ──
  const loadPending = useCallback(async () => {
    try {
      const r = await pendingRequests(user_id);
      const reqs = r.data.results || [];
      setPending(reqs);
      // Pre-fetch requester names
      reqs.forEach(req => fetchProfile(req.requester_id));
    } catch { /* ignore */ }
  }, [user_id, fetchProfile]);

  // ── Load sent requests (sent BY me, still pending) ──
  const loadSent = useCallback(async () => {
    try {
      const r = await sentRequests(user_id);
      const reqs = r.data.results || [];
      setSentRequestsList(reqs);
      setSent(reqs.map(r => r.receiver_id)); // store receiver_ids so we can disable Connect button
      reqs.forEach(req => fetchProfile(req.receiver_id));
    } catch { /* ignore */ }
  }, [user_id, fetchProfile]);

  // Load everything on mount
  useEffect(() => {
    if (!user_id) return;
    loadConnections();
    loadPending();
    loadSent();
  }, [user_id, loadConnections, loadPending, loadSent]);

  // Auto-search if arriving from nav search with ?q=
  useEffect(() => {
    const q = searchParams.get('q');
    if (q && user_id) {
      setTab('find');
      setKeyword(q);
      setLoading(true);
      api.post('/members/search', { keyword: q, limit: 20 })
        .then(r => {
          const results = (r.data.results || [])
            .filter(m => m.member_id !== user_id)
            .map(m => ({ ...m, _kind: 'member', peer_id: m.member_id }));
          setSearchRes(results);
        })
        .catch(() => setToast('Search failed'))
        .finally(() => setLoading(false));
    }
  }, [searchParams, user_id]);

  // Reload pending when switching to that tab
  useEffect(() => {
    if (tab === 'pending') loadPending();
    if (tab === 'myConnections') loadConnections();
    if (tab === 'sent') loadSent();
  }, [tab, loadPending, loadConnections, loadSent]);

  // ── Search ──
  const handleSearch = async () => {
    if (!keyword.trim()) return;
    setLoading(true);
    try {
      const r = await api.post('/members/search', { keyword, limit: 20 });
      let merged = (r.data.results || [])
        .filter(m => m.member_id !== user_id)
        .map(m => ({ ...m, _kind: 'member', peer_id: m.member_id }));
      if (recruiter_id) {
        try {
          const rr = await api.post('/recruiters/search', { keyword, limit: 15 });
          const extra = (rr.data.results || [])
            .filter(x => x.recruiter_id !== user_id)
            .map(x => ({
              member_id: x.recruiter_id,
              peer_id: x.recruiter_id,
              first_name: x.first_name,
              last_name: x.last_name,
              headline: x.company_name || x.company_industry || 'Recruiter',
              city: '',
              _kind: 'recruiter',
            }));
          merged = [...merged, ...extra];
        } catch { /* ignore */ }
      }
      setSearchRes(merged);
    } catch { setToast('Search failed'); }
    setLoading(false);
  };

  // ── Send connection request ──
  const handleConnect = async (receiver_id) => {
    try {
      await sendRequest({ requester_id: user_id, receiver_id, idempotency_key: uuid() });
      setSent(prev => [...prev, receiver_id]);
      await loadSent();
      setToast('Connection request sent');
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.error || 'Request failed';
      setToast(msg);
    }
  };

  // ── Accept ──
  const handleAccept = async (request_id) => {
    try {
      await acceptRequest(request_id);
      setToast('Connection accepted!');
      loadPending();
      loadConnections();
    } catch { setToast('Failed to accept'); }
  };

  // ── Reject ──
  const handleReject = async (request_id) => {
    try {
      await rejectRequest(request_id);
      setToast('Request declined');
      loadPending();
    } catch { setToast('Failed to decline'); }
  };

  // ── Already connected? ──
  const isConnected = (member_id) => connections.some(c => c.member_id === member_id);
  const hasSent     = (member_id) => sent.includes(member_id);
  const openProfile = async (peerId) => {
    const p = await fetchProfile(peerId);
    if (!p) return;
    if (p._type === 'recruiter') {
      navigate(`/recruiter/profile?recruiter_id=${encodeURIComponent(peerId)}`);
      return;
    }
    navigate(`/profile?member_id=${encodeURIComponent(peerId)}`);
  };

  // ── Tab style ──
  const tabStyle = (t) => ({
    padding: '9px 20px', border: 'none', cursor: 'pointer', borderRadius: 20,
    fontWeight: 600, fontSize: 14, transition: 'all 0.15s',
    background: tab === t ? '#0a66c2' : 'white',
    color:      tab === t ? 'white'   : '#374151',
    boxShadow:  tab === t ? 'none'    : '0 0 0 1px #d1d5db',
  });

  if (!user_id) {
    return (
      <div style={{ maxWidth: 960, margin: '0 auto', padding: 48, textAlign: 'center', color: '#6b7280' }}>
        Sign in to manage your network.
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <Toast msg={toast} onClose={() => setToast('')} />

      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 24, fontWeight: 700, color: '#111' }}>Network</h2>
        <p style={{ margin: 0, color: '#6b7280', fontSize: 14 }}>
          {recruiter_id ? 'Find candidates and professionals to grow your hiring network.' : 'Manage your professional connections'}
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        <button style={tabStyle('myConnections')} onClick={() => setTab('myConnections')}>
          My Connections ({connections.length})
        </button>
        <button style={tabStyle('find')} onClick={() => setTab('find')}>
          Find People
        </button>
        <button style={tabStyle('pending')} onClick={() => setTab('pending')}>
          Pending Requests {pending.length > 0 && (
            <span style={{ marginLeft: 6, background: '#ef4444', color: 'white', borderRadius: 10, padding: '1px 7px', fontSize: 12 }}>
              {pending.length}
            </span>
          )}
        </button>
        <button style={tabStyle('sent')} onClick={() => setTab('sent')}>
          Sent Requests {sentRequestsList.length > 0 && (
            <span style={{ marginLeft: 6, background: '#6b7280', color: 'white', borderRadius: 10, padding: '1px 7px', fontSize: 12 }}>
              {sentRequestsList.length}
            </span>
          )}
        </button>
      </div>

      {/* ── MY CONNECTIONS ── */}
      {tab === 'myConnections' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
          {connections.length === 0 && (
            <p style={{ color: '#6b7280', gridColumn: '1/-1' }}>No connections yet. Use "Find People" to connect.</p>
          )}
          {connections.map((c, i) => (
            <div key={c.member_id} style={{ border: '1px solid #e5e7eb', borderRadius: 10, padding: 20, background: 'white', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
              <Avatar name={`${c.first_name} ${c.last_name}`} size={52} color={COLORS[i % COLORS.length]} />
              <div style={{ marginTop: 12 }}>
                <div style={{ fontWeight: 700, fontSize: 15, color: '#111' }}>{c.first_name} {c.last_name}</div>
                {c.user_type === 'recruiter' && (
                  <span style={{ fontSize: 11, fontWeight: 600, color: '#64748b' }}>Recruiter</span>
                )}
                <div style={{ fontSize: 13, color: '#6b7280', marginTop: 2 }}>{c.headline || 'Member'}</div>
                <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>{c.city || ''}</div>
              </div>
              <button onClick={() => void openProfile(c.member_id)}
                style={{
                  marginTop: 10, width: '100%', padding: '7px', border: '1px solid #d1d5db', color: '#374151', background: 'white', borderRadius: 20,
                  cursor: 'pointer', fontWeight: 600, fontSize: 13,
                }}>
                View Profile
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── FIND PEOPLE ── */}
      {tab === 'find' && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
            <input
              placeholder="Search by name, skill, keyword..."
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              style={{ flex: 1, padding: '10px 14px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, outline: 'none' }}
            />
            <button onClick={handleSearch}
              style={{ padding: '10px 20px', background: '#0a66c2', color: 'white', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600 }}>
              {loading ? 'Searching…' : 'Search'}
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 }}>
            {searchRes.map((m, i) => {
              const pid = m.peer_id || m.member_id;
              const connected = isConnected(pid);
              const requested = hasSent(pid);
              return (
                <div key={`${pid}-${m._kind || 'member'}`} style={{ border: '1px solid #e5e7eb', borderRadius: 10, padding: 20, background: 'white', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
                  <Avatar name={`${m.first_name} ${m.last_name}`} size={52} color={COLORS[i % COLORS.length]} />
                  <div style={{ marginTop: 12, marginBottom: 14 }}>
                    <div style={{ fontWeight: 700, fontSize: 15, color: '#111' }}>{m.first_name} {m.last_name}</div>
                    {m._kind === 'recruiter' && (
                      <span style={{ fontSize: 11, fontWeight: 600, color: '#64748b' }}>Recruiter</span>
                    )}
                    <div style={{ fontSize: 13, color: '#6b7280', marginTop: 2 }}>{m.headline || 'Member'}</div>
                    <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>{m.city || ''}</div>
                  </div>
                  {connected ? (
                    <div style={{ fontSize: 13, color: '#10b981', fontWeight: 600 }}>✓ Connected</div>
                  ) : requested ? (
                    <div style={{ fontSize: 13, color: '#9ca3af', fontWeight: 600 }}>Pending…</div>
                  ) : (
                    <button onClick={() => handleConnect(pid)}
                      style={{ width: '100%', padding: '7px', border: '1px solid #0a66c2', color: '#0a66c2', background: 'white', borderRadius: 20, cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>
                      + Connect
                    </button>
                  )}
                  <button onClick={() => void openProfile(pid)}
                    style={{
                      marginTop: 8, width: '100%', padding: '7px', border: '1px solid #d1d5db', color: '#374151', background: 'white', borderRadius: 20,
                      cursor: 'pointer', fontWeight: 600, fontSize: 13,
                    }}>
                    View Profile
                  </button>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* ── PENDING REQUESTS ── */}
      {tab === 'pending' && (
        <div>
          {pending.length === 0 && (
            <div style={{ textAlign: 'center', padding: '60px 0', color: '#9ca3af' }}>
              <p style={{ fontSize: 15, fontWeight: 500, color: '#374151' }}>No pending requests</p>
              <p style={{ fontSize: 13 }}>When someone sends you a connection request, it will appear here.</p>
            </div>
          )}
          {pending.map(req => (
            <div key={req.request_id} style={{
              display: 'flex', alignItems: 'center', gap: 16,
              border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 20px',
              marginBottom: 12, background: 'white', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              <Avatar name={memberName(req.requester_id)} size={52} color="#0a66c2" />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 15, color: '#111' }}>
                  {memberName(req.requester_id)}
                </div>
                <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>
                  {req.message || 'Wants to connect with you'}
                </div>
                <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>
                  {new Date(req.created_at || req.requested_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => void openProfile(req.requester_id)}
                  style={{ padding: '8px 16px', background: 'white', color: '#374151', border: '1px solid #d1d5db', borderRadius: 20, cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>
                  View Profile
                </button>
                <button onClick={() => handleAccept(req.request_id)}
                  style={{ padding: '8px 20px', background: '#0a66c2', color: 'white', border: 'none', borderRadius: 20, cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>
                  Accept
                </button>
                <button onClick={() => handleReject(req.request_id)}
                  style={{ padding: '8px 20px', background: 'white', color: '#374151', border: '1px solid #d1d5db', borderRadius: 20, cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>
                  Decline
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── SENT REQUESTS ── */}
      {tab === 'sent' && (
        <div>
          {sentRequestsList.length === 0 && (
            <div style={{ textAlign: 'center', padding: '60px 0', color: '#9ca3af' }}>
              <p style={{ fontSize: 15, fontWeight: 500, color: '#374151' }}>No outgoing requests</p>
              <p style={{ fontSize: 13 }}>Requests you send will appear here until the other member responds.</p>
            </div>
          )}
          {sentRequestsList.map(req => (
            <div key={req.request_id} style={{
              display: 'flex', alignItems: 'center', gap: 16,
              border: '1px solid #e5e7eb', borderRadius: 10, padding: '16px 20px',
              marginBottom: 12, background: 'white', boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
              <Avatar name={memberName(req.receiver_id)} size={52} color="#6b7280" />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: 15, color: '#111' }}>{memberName(req.receiver_id)}</div>
                <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>Awaiting response</div>
                <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>
                  Sent {new Date(req.created_at || req.requested_at || Date.now()).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button onClick={() => void openProfile(req.receiver_id)}
                  style={{ padding: '8px 16px', background: 'white', color: '#374151', border: '1px solid #d1d5db', borderRadius: 20, cursor: 'pointer', fontWeight: 600, fontSize: 14 }}>
                  View Profile
                </button>
                <span style={{ padding: '4px 12px', borderRadius: 12, background: '#f3f4f6', color: '#374151', fontSize: 12, fontWeight: 600 }}>Pending</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
