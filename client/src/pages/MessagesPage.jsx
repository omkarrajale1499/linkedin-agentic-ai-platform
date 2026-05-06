import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/apiClient';
import { sendMessage as sendMessageApi, listMessages } from '../api/messagingApi';

// ─────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────
function initials(name = '') {
  return name.split(' ').filter(Boolean).map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?';
}

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'just now';
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7)  return `${d}d`;
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// Avatar circle
function Avatar({ name, size = 40, color = '#0a66c2' }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: color, color: 'white',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.35, fontWeight: 700, flexShrink: 0,
    }}>
      {initials(name)}
    </div>
  );
}

const AVATAR_COLORS = ['#0a66c2','#10b981','#8b5cf6','#f59e0b','#ef4444','#06b6d4','#ec4899'];

// ─────────────────────────────────────────────
//  NEW MESSAGE MODAL
// ─────────────────────────────────────────────
function NewMessageModal({ myId, isRecruiter, onOpen, onClose }) {
  const [query, setQuery]     = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openError, setOpenError] = useState('');

  const search = async (q) => {
    setQuery(q);
    setOpenError('');
    if (!q.trim()) { setResults([]); return; }
    setLoading(true);
    try {
      const memberReq = api.post('/members/search', { keyword: q, limit: 10 });
      const recruiterReq = isRecruiter
        ? api.post('/recruiters/search', { keyword: q, limit: 10 })
        : Promise.resolve({ data: { results: [] } });
      const [mr, rr] = await Promise.all([memberReq, recruiterReq]);
      const members = (mr.data.results || [])
        .filter(m => m.member_id && m.member_id !== myId)
        .map(m => ({ ...m, _kind: 'member' }));
      const recruiters = (rr.data?.results || [])
        .filter(r => r.recruiter_id && r.recruiter_id !== myId)
        .map(r => ({ ...r, _kind: 'recruiter' }));
      setResults([...members, ...recruiters].slice(0, 20));
    } catch {
      setResults([]);
    }
    setLoading(false);
  };

  const startChat = async (row) => {
    setOpenError('');
    if (!myId) {
      setOpenError('Not signed in as a member or recruiter.');
      return;
    }
    const otherId = row._kind === 'recruiter' ? row.recruiter_id : row.member_id;
    const profile = row._kind === 'recruiter'
      ? {
          member_id: row.recruiter_id,
          first_name: row.first_name,
          last_name: row.last_name,
          headline: row.company_name || row.company_industry || 'Recruiter',
          email: row.email,
          _type: 'recruiter',
        }
      : { ...row, _type: 'member' };
    try {
      const r = await api.post('/threads/open', { participant_ids: [myId, otherId] });
      onOpen(r.data.thread_id, profile, otherId);
    } catch (e) {
      setOpenError(e?.response?.data?.detail || e?.response?.data?.error || e.message || 'Could not start conversation');
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{
        background: 'white', borderRadius: 12, width: 460, maxHeight: '70vh',
        display: 'flex', flexDirection: 'column', boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
      }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>New message</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#6b7280' }}>×</button>
        </div>
        {/* Search */}
        <div style={{ padding: '12px 20px', borderBottom: '1px solid #e5e7eb' }}>
          <input
            autoFocus
            value={query}
            onChange={e => search(e.target.value)}
            placeholder="Search by name or email…"
            style={{ width: '100%', padding: '10px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, outline: 'none', boxSizing: 'border-box' }}
          />
        </div>
        {/* Results */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {loading && <p style={{ textAlign: 'center', color: '#9ca3af', padding: 20, fontSize: 14 }}>Searching…</p>}
          {!loading && results.length === 0 && query && (
            <p style={{ textAlign: 'center', color: '#9ca3af', padding: 20, fontSize: 14 }}>No people found</p>
          )}
          {openError && (
            <p style={{ textAlign: 'center', color: '#dc2626', padding: '8px 20px 0', fontSize: 13, margin: 0 }}>{openError}</p>
          )}
          {results.map((row, i) => {
            const rowKey = row._kind === 'recruiter' ? row.recruiter_id : row.member_id;
            const sub = row._kind === 'recruiter' ? (row.company_name || row.email) : (row.headline || row.email);
            return (
            <div key={rowKey} onClick={() => startChat(row)}
              style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', cursor: 'pointer', borderBottom: '1px solid #f3f4f6' }}
              onMouseEnter={e => e.currentTarget.style.background = '#f9fafb'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
              <Avatar name={`${row.first_name} ${row.last_name}`} size={42} color={AVATAR_COLORS[i % AVATAR_COLORS.length]} />
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{row.first_name} {row.last_name}</div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>{sub}{row._kind === 'recruiter' ? <span style={{ color: '#94a3b8' }}> · Recruiter</span> : null}</div>
              </div>
            </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
//  MAIN COMPONENT
// ─────────────────────────────────────────────
export default function MessagesPage() {
  const navigate = useNavigate();
  const myId = localStorage.getItem('member_id') || localStorage.getItem('recruiter_id') || '';
  const myName = localStorage.getItem('user_name') || localStorage.getItem('member_name') || 'You';
  const isRecruiter = (localStorage.getItem('role') || '') === 'recruiter';

  const [threads,      setThreads]      = useState([]);
  const [activeThread, setActiveThread] = useState(null); // full thread object
  const [messages,     setMessages]     = useState([]);
  const [text,         setText]         = useState('');
  const [memberCache,  setMemberCache]  = useState({}); // member_id → member object
  const [showModal,    setShowModal]    = useState(false);
  const [loadingMsgs,  setLoadingMsgs]  = useState(false);
  const [threadQuery,  setThreadQuery]  = useState('');
  const [threadFilter, setThreadFilter] = useState('focused');
  const [showChatMenu, setShowChatMenu] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth);
  const [showRailMobile, setShowRailMobile] = useState(false);
  const [starredThreads, setStarredThreads] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(`thread_starred_${myId}`) || '{}');
    } catch {
      return {};
    }
  });
  const [lastSeenByThread, setLastSeenByThread] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(`thread_last_seen_${myId}`) || '{}');
    } catch {
      return {};
    }
  });
  const [toastMsg, setToastMsg] = useState(null);

  const showToast = (msg, type = 'success') => {
    setToastMsg({ msg, type });
    setTimeout(() => setToastMsg(null), 4000);
  };

  const bottomRef      = useRef();
  const inputRef       = useRef();
  const pollRef        = useRef();
  const threadPollRef  = useRef();

  // ── Fetch profile by ID (member first, recruiter fallback) ──
  const fetchMember = useCallback(async (id) => {
    if (!id || memberCache[id]) return memberCache[id];
    try {
      const r = await api.post('/members/get', { member_id: id, viewer_id: myId });
      const m = { ...r.data, _type: 'member' };
      setMemberCache(prev => ({ ...prev, [id]: m }));
      return m;
    } catch (_) {
      try {
        const rr = await api.post('/recruiters/get', { recruiter_id: id });
        const r = rr.data || {};
        const recruiterProfile = {
          member_id: id,
          first_name: r.first_name || r.company_name || 'Recruiter',
          last_name: r.last_name || '',
          headline: r.company_industry || 'Recruiter',
          _type: 'recruiter',
        };
        setMemberCache(prev => ({ ...prev, [id]: recruiterProfile }));
        return recruiterProfile;
      } catch {
        const fallback = {
          member_id: id,
          first_name: id.slice(0, 8),
          last_name: '',
          headline: 'User',
          _type: 'unknown',
        };
        setMemberCache(prev => ({ ...prev, [id]: fallback }));
        return fallback;
      }
    }
  }, [memberCache]);

  const displayName = (id) => {
    const p = memberCache[id];
    if (!p) return id ? `${id.slice(0, 8)}…` : 'Unknown';
    const full = `${p.first_name || ''} ${p.last_name || ''}`.trim();
    return full || (id ? `${id.slice(0, 8)}…` : 'Unknown');
  };

  const unreadCountForThread = useCallback((thread) => {
    const threadId = thread.thread_id;
    const updatedAt = new Date(thread.updated_at || 0).getTime();
    const seenAt = new Date(lastSeenByThread[threadId] || 0).getTime();
    if (!updatedAt || updatedAt <= seenAt) return 0;
    return 1;
  }, [lastSeenByThread]);

  // ── Load all threads ──
  const loadThreads = useCallback(async () => {
    if (!myId) return;
    try {
      const r = await api.post('/threads/byUser', { user_id: myId });
      const ts = r.data.results || [];
      setThreads(ts);
      // Pre-fetch participant names
      const ids = [...new Set(ts.flatMap(t => t.participant_ids || []).filter(id => id !== myId))];
      ids.forEach(id => fetchMember(id));
    } catch { /* ignore */ }
  }, [myId, fetchMember]);

  useEffect(() => { loadThreads(); }, [loadThreads]);

  // Poll thread list every 10 s to surface new incoming messages
  useEffect(() => {
    if (!myId) return;
    threadPollRef.current = setInterval(() => loadThreads(), 10000);
    return () => clearInterval(threadPollRef.current);
  }, [loadThreads, myId]);

  // ── Open a thread ──
  const openThread = async (thread) => {
    setActiveThread(thread);
    setShowChatMenu(false);
    // Use the thread's own updated_at as the "seen" marker so clock skew
    // between server and client doesn't keep the thread appearing unread.
    const seenTs = thread.updated_at || new Date().toISOString();
    setLastSeenByThread(prev => {
      const next = { ...prev, [thread.thread_id]: seenTs };
      localStorage.setItem(`thread_last_seen_${myId}`, JSON.stringify(next));
      return next;
    });
    setLoadingMsgs(true);
    try {
      const r = await api.post('/messages/list', { thread_id: thread.thread_id });
      setMessages(r.data.results || []);
      scrollMessagesToBottom('auto');
      // Pre-fetch sender names
      const senderIds = [...new Set((r.data.results || []).map(m => m.sender_id))];
      senderIds.forEach(id => fetchMember(id));
    } catch { /* ignore */ }
    setLoadingMsgs(false);
    // Start polling for new messages every 5 s
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const r = await api.post('/messages/list', { thread_id: thread.thread_id });
        setMessages(r.data.results || []);
      } catch { /* ignore */ }
    }, 5000);
  };

  // Stop polling when unmounted
  useEffect(() => () => clearInterval(pollRef.current), []);
  useEffect(() => {
    const onResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const scrollMessagesToBottom = (behavior = 'auto') => {
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior, block: 'end' });
    });
  };

  // ── Send a message ──
  const sendMessage = async () => {
    if (!text.trim() || !activeThread) return;
    const body = text.trim();
    setText('');
    try {
      await sendMessageApi(activeThread.thread_id, myId, body);
      const r = await listMessages(activeThread.thread_id);
      setMessages(r.data.results || []);
      scrollMessagesToBottom('smooth');
      loadThreads();
    } catch (e) {
      setText(body); // restore text so user doesn't lose their message
      showToast(e?.response?.data?.detail || 'Message failed to send. Please try again.', 'error');
    }
  };

  // ── New message modal: a thread was opened ──
  const handleNewThreadOpened = async (thread_id, otherProfile, otherUserId) => {
    setShowModal(false);
    setMemberCache(prev => ({ ...prev, [otherUserId]: otherProfile }));
    await loadThreads();
    openThread({ thread_id, participant_ids: [myId, otherUserId] });
  };

  // ─────────────────────────────────────────────
  //  RENDER
  // ─────────────────────────────────────────────
  const activeOtherId = activeThread
    ? (activeThread.participant_ids || []).find(id => id !== myId)
    : null;
  const activeOther = memberCache[activeOtherId];
  const openProfile = async (userId) => {
    if (!userId) return;
    let p = memberCache[userId];
    if (!p) {
      try {
        p = await fetchMember(userId);
      } catch {
        p = null;
      }
    }
    if (p?._type === 'recruiter') {
      navigate(`/recruiter/profile?recruiter_id=${encodeURIComponent(userId)}`);
      return;
    }
    navigate(`/profile?member_id=${encodeURIComponent(userId)}`);
  };
  const activeThreadStarred = !!(activeThread && starredThreads[activeThread.thread_id]);
  const isRailCollapsed = viewportWidth < 1300;

  const toggleStarThread = () => {
    if (!activeThread) return;
    const threadId = activeThread.thread_id;
    setStarredThreads(prev => {
      const next = { ...prev, [threadId]: !prev[threadId] };
      localStorage.setItem(`thread_starred_${myId}`, JSON.stringify(next));
      return next;
    });
    setShowChatMenu(false);
  };

  const chatMenuAction = (label) => {
    showToast(`${label} is not connected yet`, 'error');
    setShowChatMenu(false);
  };

  const filterButtonStyle = (active) => ({
    padding: '5px 12px',
    borderRadius: 999,
    border: `1px solid ${active ? '#0a66c2' : '#d1d5db'}`,
    background: active ? '#eff6ff' : 'white',
    color: active ? '#0a66c2' : '#374151',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  });

  const filteredThreads = threads.filter((t) => {
    const otherId = (t.participant_ids || []).find(id => id !== myId);
    const other = memberCache[otherId];
    const name = other ? displayName(otherId) : otherId || 'Unknown';
    const headline = other?.headline || '';
    const q = threadQuery.trim().toLowerCase();
    const matchesQuery = !q || name.toLowerCase().includes(q) || headline.toLowerCase().includes(q) || (t.last_message || '').toLowerCase().includes(q);
    if (!matchesQuery) return false;

    if (threadFilter === 'unread') return unreadCountForThread(t) > 0;
    if (threadFilter === 'connections') return other?._type === 'member';
    return true; // focused / all
  });

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {showModal && (
        <NewMessageModal myId={myId} isRecruiter={isRecruiter} onOpen={handleNewThreadOpened} onClose={() => setShowModal(false)} />
      )}

      <div style={{
        display: 'grid',
        gridTemplateColumns: isRailCollapsed ? 'minmax(0, 1fr)' : 'minmax(0, 1fr) 280px',
        height: 'calc(100vh - 140px)',
        minHeight: 500,
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        overflow: 'hidden',
        background: 'white',
        boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
        position: 'relative',
      }}>

        {/* ── PRIMARY REGION (shared header + list/chat) ── */}
        <div style={{ display: 'grid', gridTemplateRows: 'auto minmax(0,1fr)', minHeight: 0 }}>
          <div style={{ padding: '12px 14px 10px', borderBottom: '1px solid #e5e7eb', background: 'white' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#111' }}>Messaging</h2>
              <input
                value={threadQuery}
                onChange={(e) => setThreadQuery(e.target.value)}
                placeholder="Search messages"
                style={{ flex: 1, minWidth: 160, padding: '9px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, outline: 'none', boxSizing: 'border-box' }}
              />
              <button
                onClick={() => setShowModal(true)}
                title="New message"
                style={{
                  width: 34, height: 34, borderRadius: '50%', border: '1px solid #d1d5db',
                  background: 'white', cursor: 'pointer', fontSize: 18, display: 'flex',
                  alignItems: 'center', justifyContent: 'center', color: '#374151',
                }}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
              </button>
            </div>
            <div style={{ marginTop: 10, display: 'flex', gap: 6, overflowX: 'auto' }}>
              <button onClick={() => setThreadFilter('focused')} style={filterButtonStyle(threadFilter === 'focused')}>Focused</button>
              <button onClick={() => setThreadFilter('unread')} style={filterButtonStyle(threadFilter === 'unread')}>Unread</button>
              <button onClick={() => setThreadFilter('connections')} style={filterButtonStyle(threadFilter === 'connections')}>Connections</button>
              <button onClick={() => setThreadFilter('all')} style={filterButtonStyle(threadFilter === 'all')}>All</button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '340px minmax(0,1fr)', minHeight: 0 }}>
        {/* ── LEFT SIDEBAR ── */}
        <div style={{ borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

          {/* Thread list */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {filteredThreads.length === 0 && (
              <div style={{ padding: 32, textAlign: 'center', color: '#9ca3af' }}>
                <p style={{ margin: 0, fontSize: 14 }}>
                  {threads.length === 0 ? 'No conversations yet' : 'No conversations match this filter'}
                </p>
                <p style={{ margin: '8px 0 0', fontSize: 13 }}>
                  {threads.length === 0 ? 'Click + to start a new message' : 'Try changing search or filter'}
                </p>
              </div>
            )}
            {filteredThreads.map((t, i) => {
              const otherId = (t.participant_ids || []).find(id => id !== myId);
              const other   = memberCache[otherId];
              const name    = other ? displayName(otherId) : (otherId ? `${otherId.slice(0, 8)}…` : 'Unknown');
              const isActive = activeThread?.thread_id === t.thread_id;
              const unreadCount = unreadCountForThread(t);

              return (
                <div
                  key={t.thread_id}
                  onClick={() => openThread(t)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '12px 16px', cursor: 'pointer',
                    background: isActive ? '#eef3fb' : 'transparent',
                    borderBottom: '1px solid #f3f4f6',
                    borderLeft: isActive ? '3px solid #0a66c2' : '3px solid transparent',
                  }}
                  onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = '#f9fafb'; }}
                  onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
                >
                  <Avatar name={name} size={48} color={AVATAR_COLORS[i % AVATAR_COLORS.length]} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                      <span style={{ fontWeight: 600, fontSize: 14, color: '#111', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 160 }}>
                        {name}
                      </span>
                      <span style={{ fontSize: 11, color: unreadCount > 0 ? '#0a66c2' : '#9ca3af', fontWeight: unreadCount > 0 ? 700 : 400, flexShrink: 0 }}>
                        {timeAgo(t.updated_at)}
                      </span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                      <div style={{ fontSize: 13, color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {t.last_message || 'Start a conversation'}
                      </div>
                      {unreadCount > 0 && (
                        <span style={{
                          minWidth: 18, height: 18, borderRadius: 9,
                          background: '#0a66c2', color: 'white',
                          fontSize: 11, fontWeight: 700,
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          padding: '0 5px',
                        }}>
                          {unreadCount}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── CENTER PANEL ── */}
        {!activeThread ? (
          /* Empty state */
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#9ca3af' }}>
            <h3 style={{ margin: '0 0 8px', fontSize: 20, fontWeight: 700, color: '#374151' }}>Your Messages</h3>
            <p style={{ margin: '0 0 24px', fontSize: 14 }}>Select a conversation or start a new one.</p>
            <button
              onClick={() => setShowModal(true)}
              style={{ padding: '10px 24px', background: '#0a66c2', color: 'white', border: 'none', borderRadius: 20, fontSize: 14, fontWeight: 600, cursor: 'pointer' }}>
              New message
            </button>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>

            {/* Chat header */}
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 12, background: 'white', position: 'relative' }}>
              <Avatar name={activeOther ? `${activeOther.first_name} ${activeOther.last_name}` : '…'} size={44} color="#0a66c2" />
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, color: '#111' }}>
                  {activeOther ? displayName(activeOtherId) : (activeOtherId ? `${activeOtherId.slice(0, 8)}…` : 'Unknown')}
                </div>
                {activeOther?.headline && (
                  <div style={{ fontSize: 12, color: '#6b7280' }}>{activeOther.headline}</div>
                )}
              </div>
              <button onClick={() => toggleStarThread()}
                title={activeThreadStarred ? 'Unstar conversation' : 'Star conversation'}
                style={{ marginLeft: 'auto', width: 34, height: 34, borderRadius: '50%', border: '1px solid #d1d5db', background: 'white', cursor: 'pointer', color: activeThreadStarred ? '#f59e0b' : '#6b7280', fontSize: 16 }}>
                {activeThreadStarred ? '★' : '☆'}
              </button>
              <button
                onClick={() => openProfile(activeOtherId)}
                style={{ padding: '7px 14px', border: '1px solid #d1d5db', background: 'white', borderRadius: 20, cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151' }}>
                View Profile
              </button>
              <button
                onClick={() => setShowChatMenu(v => !v)}
                title="More actions"
                style={{ width: 34, height: 34, borderRadius: '50%', border: '1px solid #d1d5db', background: 'white', cursor: 'pointer', color: '#6b7280', fontSize: 18, lineHeight: 1 }}>
                ⋯
              </button>
              {isRailCollapsed && (
                <button
                  onClick={() => setShowRailMobile(true)}
                  title="Open details panel"
                  style={{ width: 34, height: 34, borderRadius: '50%', border: '1px solid #d1d5db', background: 'white', cursor: 'pointer', color: '#6b7280', fontSize: 16 }}>
                  i
                </button>
              )}
              {showChatMenu && (
                <div style={{
                  position: 'absolute',
                  top: 54,
                  right: 20,
                  width: 170,
                  background: 'white',
                  border: '1px solid #e5e7eb',
                  borderRadius: 10,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                  zIndex: 20,
                  overflow: 'hidden',
                }}>
                  <button onClick={toggleStarThread} style={menuItemStyle()}>
                    {activeThreadStarred ? 'Unstar conversation' : 'Star conversation'}
                  </button>
                  <button onClick={() => chatMenuAction('Archive')} style={menuItemStyle()}>Archive</button>
                  <button onClick={() => chatMenuAction('Mute')} style={menuItemStyle()}>Mute notifications</button>
                  <button onClick={() => chatMenuAction('Delete')} style={menuItemStyle({ danger: true })}>Delete conversation</button>
                </div>
              )}
            </div>

            {/* Messages area */}
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '20px 24px', background: '#f9fafb', display: 'flex', flexDirection: 'column', gap: 4 }}>
              {loadingMsgs && (
                <div style={{ textAlign: 'center', color: '#9ca3af', padding: 20, fontSize: 14 }}>Loading messages…</div>
              )}
              {!loadingMsgs && messages.length === 0 && (
                <div style={{ textAlign: 'center', color: '#9ca3af', padding: 40 }}>
                  <p style={{ fontSize: 14 }}>No messages yet. Say hello!</p>
                </div>
              )}

              {messages.map((m, i) => {
                const isMe = m.sender_id === myId;
                const sender = memberCache[m.sender_id];
                const senderName = sender ? displayName(m.sender_id) : (isMe ? myName : `${(m.sender_id || '').slice(0, 8)}…`);
                const prevMsg = messages[i - 1];
                const showSender = !prevMsg || prevMsg.sender_id !== m.sender_id;
                const showTime = !messages[i + 1] || messages[i + 1].sender_id !== m.sender_id;

                return (
                  <div key={m.message_id} style={{ display: 'flex', flexDirection: isMe ? 'row-reverse' : 'row', alignItems: 'flex-end', gap: 8, marginTop: showSender ? 12 : 2 }}>
                    {/* Avatar — only show for last consecutive message from same sender */}
                    {!isMe && (
                      <div style={{ width: 32, flexShrink: 0 }}>
                        {showTime && <Avatar name={senderName} size={32} color="#0a66c2" />}
                      </div>
                    )}
                    <div style={{ maxWidth: '60%', display: 'flex', flexDirection: 'column', alignItems: isMe ? 'flex-end' : 'flex-start' }}>
                      {showSender && !isMe && (
                        <span style={{ fontSize: 12, color: '#6b7280', marginBottom: 4, marginLeft: 4 }}>{senderName}</span>
                      )}
                      <div style={{
                        padding: '10px 14px',
                        borderRadius: isMe ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                        background: isMe ? '#0a66c2' : 'white',
                        color: isMe ? 'white' : '#111',
                        fontSize: 14, lineHeight: 1.45,
                        boxShadow: '0 1px 2px rgba(0,0,0,0.08)',
                        wordBreak: 'break-word',
                      }}>
                        {m.message_text}
                      </div>
                      {showTime && (
                        <span style={{ fontSize: 11, color: '#9ca3af', margin: '4px 4px 0' }}>
                          {timeAgo(m.sent_at)}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>

            {/* Input area */}
            <div style={{ padding: '10px 14px 12px', borderTop: '1px solid #e5e7eb', background: 'white' }}>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10 }}>
              <div style={{ flex: 1, background: '#f3f4f6', borderRadius: 24, padding: '10px 16px', minHeight: 42, display: 'flex', alignItems: 'center' }}>
                <textarea
                  ref={inputRef}
                  value={text}
                  onChange={e => { setText(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'; }}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                  placeholder="Write a message…"
                  rows={1}
                  style={{
                    width: '100%', background: 'none', border: 'none', outline: 'none',
                    fontSize: 14, resize: 'none', lineHeight: 1.4, fontFamily: 'inherit',
                    color: '#111', maxHeight: 120,
                  }}
                />
              </div>
              <button
                onClick={sendMessage}
                disabled={!text.trim()}
                style={{
                  width: 42, height: 42, borderRadius: '50%', border: 'none',
                  background: text.trim() ? '#0a66c2' : '#e5e7eb',
                  color: text.trim() ? 'white' : '#9ca3af',
                  cursor: text.trim() ? 'pointer' : 'default',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, transition: 'background 0.15s',
                }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
              </button>
              </div>
              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center' }}>
                <span style={{ marginLeft: 'auto', fontSize: 11, color: '#9ca3af' }}>Enter to send · Shift+Enter for new line</span>
              </div>
            </div>

          </div>
        )}
          </div>
        </div>

        {/* ── RIGHT INFO RAIL (desktop) ── */}
        {!isRailCollapsed && (
        <div style={{ borderLeft: '1px solid #e5e7eb', background: '#fafafa', overflowY: 'auto' }}>
          <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: 14 }}>
              <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>Conversation details</div>
              {activeThread ? (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Avatar name={activeOther ? `${activeOther.first_name} ${activeOther.last_name}` : 'Unknown'} size={44} color="#0a66c2" />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, fontSize: 14, color: '#111', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {activeOther ? displayName(activeOtherId) : 'Unknown user'}
                      </div>
                      <div style={{ fontSize: 12, color: '#6b7280', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {activeOther?.headline || 'No headline available'}
                      </div>
                    </div>
                  </div>
                  <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
                    <button onClick={() => openProfile(activeOtherId)} style={railButtonStyle()}>View profile</button>
                    <button disabled title="Coming soon" style={railButtonStyle({ disabled: true })}>Mute conversation (Coming soon)</button>
                    <button disabled title="Coming soon" style={railButtonStyle({ disabled: true })}>Archive chat (Coming soon)</button>
                  </div>
                </>
              ) : (
                <p style={{ margin: 0, fontSize: 13, color: '#6b7280' }}>Open a thread to see participant info and actions.</p>
              )}
            </div>

            <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: 14 }}>
              <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>Quick filters</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                <button onClick={() => setThreadFilter('focused')} style={chipStyle(threadFilter === 'focused')}>Focused</button>
                <button onClick={() => setThreadFilter('unread')} style={chipStyle(threadFilter === 'unread')}>Unread</button>
                <button onClick={() => setThreadFilter('connections')} style={chipStyle(threadFilter === 'connections')}>Connections</button>
                <button onClick={() => setThreadFilter('all')} style={chipStyle(threadFilter === 'all')}>All</button>
              </div>
            </div>

            <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: 14 }}>
              <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>Tips</div>
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#6b7280', lineHeight: 1.6 }}>
                <li>Use search to find old messages faster.</li>
                <li>Unread highlights help prioritize replies.</li>
                <li>Shift+Enter inserts a new line.</li>
              </ul>
            </div>
          </div>
        </div>
        )}

        {/* ── RIGHT INFO RAIL (mobile/tablet drawer) ── */}
        {isRailCollapsed && showRailMobile && (
          <>
            <div
              onClick={() => setShowRailMobile(false)}
              style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.28)', zIndex: 30 }}
            />
            <div style={{
              position: 'absolute',
              top: 0,
              right: 0,
              bottom: 0,
              width: 300,
              background: '#fafafa',
              borderLeft: '1px solid #e5e7eb',
              zIndex: 31,
              overflowY: 'auto',
            }}>
              <div style={{ padding: 12, borderBottom: '1px solid #e5e7eb', background: 'white', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong style={{ fontSize: 14, color: '#111' }}>Details</strong>
                <button onClick={() => setShowRailMobile(false)} style={{ border: '1px solid #d1d5db', background: 'white', width: 30, height: 30, borderRadius: 15, cursor: 'pointer' }}>×</button>
              </div>
              <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: 14 }}>
                  <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>Conversation details</div>
                  {activeThread ? (
                    <>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <Avatar name={activeOther ? `${activeOther.first_name} ${activeOther.last_name}` : 'Unknown'} size={44} color="#0a66c2" />
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontWeight: 700, fontSize: 14, color: '#111', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {activeOther ? displayName(activeOtherId) : 'Unknown user'}
                          </div>
                          <div style={{ fontSize: 12, color: '#6b7280', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {activeOther?.headline || 'No headline available'}
                          </div>
                        </div>
                      </div>
                      <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
                        <button onClick={() => openProfile(activeOtherId)} style={railButtonStyle()}>View profile</button>
                        <button disabled title="Coming soon" style={railButtonStyle({ disabled: true })}>Mute conversation (Coming soon)</button>
                        <button disabled title="Coming soon" style={railButtonStyle({ disabled: true })}>Archive chat (Coming soon)</button>
                      </div>
                    </>
                  ) : (
                    <p style={{ margin: 0, fontSize: 13, color: '#6b7280' }}>Open a thread to see participant info and actions.</p>
                  )}
                </div>
                <div style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 10, padding: 14 }}>
                  <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>Quick filters</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    <button onClick={() => setThreadFilter('focused')} style={chipStyle(threadFilter === 'focused')}>Focused</button>
                    <button onClick={() => setThreadFilter('unread')} style={chipStyle(threadFilter === 'unread')}>Unread</button>
                    <button onClick={() => setThreadFilter('connections')} style={chipStyle(threadFilter === 'connections')}>Connections</button>
                    <button onClick={() => setThreadFilter('all')} style={chipStyle(threadFilter === 'all')}>All</button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {toastMsg && (
        <div style={{
          position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
          background: toastMsg.type === 'error' ? '#ef4444' : '#22c55e',
          color: 'white', padding: '10px 20px', borderRadius: 8,
          fontSize: 14, fontWeight: 500, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          zIndex: 9999,
        }}>
          {toastMsg.msg}
        </div>
      )}
    </div>
  );
}

function menuItemStyle(opts = {}) {
  return {
    width: '100%',
    textAlign: 'left',
    padding: '9px 12px',
    border: 'none',
    borderBottom: '1px solid #f3f4f6',
    background: 'white',
    cursor: 'pointer',
    fontSize: 13,
    color: opts.danger ? '#dc2626' : '#374151',
  };
}

function toolButtonStyle() {
  return {
    height: 28,
    minWidth: 28,
    borderRadius: 14,
    border: '1px solid #d1d5db',
    background: 'white',
    color: '#4b5563',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    padding: '0 8px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  };
}

function railButtonStyle(opts = {}) {
  const disabled = Boolean(opts.disabled);
  return {
    width: '100%',
    height: 34,
    borderRadius: 8,
    border: '1px solid #d1d5db',
    background: disabled ? '#f9fafb' : 'white',
    color: disabled ? '#9ca3af' : '#374151',
    fontSize: 12,
    fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    textAlign: 'left',
    padding: '0 10px',
    opacity: disabled ? 0.9 : 1,
  };
}

function chipStyle(active) {
  return {
    height: 30,
    padding: '0 10px',
    borderRadius: 999,
    border: `1px solid ${active ? '#93c5fd' : '#dbe2ea'}`,
    background: active ? '#eff6ff' : '#fff',
    color: active ? '#0a66c2' : '#475569',
    fontSize: 12,
    fontWeight: active ? 600 : 500,
    cursor: 'pointer',
  };
}
