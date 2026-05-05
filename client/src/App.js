import { useEffect, useRef, useState } from 'react';
import { Routes, Route, Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import api from './api/apiClient';
import LoginPage        from './pages/LoginPage';
import HomeFeedPage     from './pages/HomeFeedPage';
import CareerResourcesPage from './pages/CareerResourcesPage';
import JobsPage, { JobsBrowsePage } from './pages/JobsPage';
import ProfilePage      from './pages/ProfilePage';
import MessagesPage     from './pages/MessagesPage';
import AnalyticsDashboard from './pages/AnalyticsDashboard';
import ConnectionsPage  from './pages/ConnectionsPage';
import RecruiterPage    from './pages/RecruiterPage';
import RecruiterProfileViewPage from './pages/RecruiterProfileViewPage';
import AIAssistantPage  from './pages/AIAssistantPage';

function BrandMark() {
  return (
    <span style={{ width:34, height:34, borderRadius:4, background:'#0a66c2', color:'white', display:'inline-flex', alignItems:'center', justifyContent:'center', fontWeight:800, fontSize:21, lineHeight:1 }}>in</span>
  );
}

function NavIcon({ children }) {
  return (
    <span style={{ width: 24, height: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        {children}
      </svg>
    </span>
  );
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const profileMenuRef = useRef(null);
  const [navSearch, setNavSearch] = useState('');
  const [user, setUser] = useState(() => {
    const id   = localStorage.getItem('member_id') || localStorage.getItem('recruiter_id');
    const name = localStorage.getItem('user_name');
    const role = localStorage.getItem('role');
    return id ? { id, name, role } : null;
  });
  const [profileInfo, setProfileInfo] = useState(null);
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  const handleLogin = (userData) => setUser(userData);

  const handleLogout = () => {
    ['member_id', 'recruiter_id', 'user_name', 'role', 'token'].forEach(k => localStorage.removeItem(k));
    setUser(null);
  };

  useEffect(() => {
    const validateSession = async () => {
      if (!user?.id || !user?.role) return;
      try {
        if (user.role === 'recruiter') {
          const rr = await api.post('/recruiters/get', { recruiter_id: user.id });
          const r = rr.data || {};
          setProfileInfo({
            name: user.name || r.company_name || 'Recruiter',
            description: r.company_industry || 'Recruiter',
            photoUrl: '',
          });
        } else {
          const mr = await api.post('/members/get', { member_id: user.id });
          const m = mr.data || {};
          setProfileInfo({
            name: user.name || `${m.first_name || ''} ${m.last_name || ''}`.trim() || 'Member',
            description: m.headline || '',
            photoUrl: m.profile_photo_url || '',
          });
        }
      } catch (_) {
        // Session points to non-existent user (common after reseed/restart) -> reset to login.
        ['member_id', 'recruiter_id', 'user_name', 'role', 'token'].forEach(k => localStorage.removeItem(k));
        setUser(null);
      }
    };
    validateSession();
  }, [user]);

  useEffect(() => {
    const onDocClick = (e) => {
      if (!profileMenuRef.current?.contains(e.target)) setShowProfileMenu(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  if (!user) return <LoginPage onLogin={handleLogin} />;

  const isRecruiter = user.role === 'recruiter';
  const isJobsBrowseRoute = !isRecruiter && location.pathname.startsWith('/jobs/browse');
  const contentWrapperStyle = isJobsBrowseRoute
    ? {
        maxWidth: 1200,
        margin: '0 auto',
        padding: '16px 20px',
        height: 'calc(100vh - 52px)',
        overflow: 'hidden',
        boxSizing: 'border-box',
      }
    : { maxWidth: 1200, margin: '0 auto', padding: '24px 20px' };

  const isActiveNav = (path) => location.pathname === path;
  const navItemStyle = (active) => ({
    color: active ? '#111827' : '#6b7280',
    textDecoration: 'none',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
    minWidth: 72,
    height: 52,
    borderBottom: active ? '1.5px solid #111827' : '1.5px solid transparent',
    fontSize: 12,
    fontWeight: active ? 600 : 500,
    paddingTop: 2,
    boxSizing: 'border-box',
  });

  return (
    <div style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', background: '#f3f2ef', minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <nav style={{ background: 'white', height: 52, position: 'sticky', top: 0, zIndex: 100, borderBottom: '1px solid #e5e7eb' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', height: '100%', padding: '0 20px', boxSizing: 'border-box', display: 'flex', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginRight: 16 }}>
          <Link to={isRecruiter ? '/recruiter' : '/home'} style={{ textDecoration: 'none', display: 'inline-flex' }}><BrandMark /></Link>
          <input
            placeholder="Search"
            value={navSearch}
            onChange={e => setNavSearch(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && navSearch.trim()) {
                navigate(`/connections?tab=find&q=${encodeURIComponent(navSearch.trim())}`);
                setNavSearch('');
              }
            }}
            style={{
              width: 'clamp(170px, 18vw, 280px)',
              height: 34,
              borderRadius: 17,
              border: '1px solid #d1d5db',
              padding: '0 12px',
              fontSize: 13,
              outline: 'none',
              background: '#f9fafb',
            }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'stretch', marginLeft: 'auto', marginRight: 6 }}>
          {!isRecruiter && (
            <>
              <Link to="/home" style={navItemStyle(location.pathname.startsWith('/home') || location.pathname === '/career-resources')}>
                <NavIcon><path d="M12 3.2L3.2 10.4a1 1 0 0 0 .63 1.76H6V20a1 1 0 0 0 1 1h3.8a1 1 0 0 0 1-1v-4h.4v4a1 1 0 0 0 1 1H17a1 1 0 0 0 1-1v-7.84h2.17a1 1 0 0 0 .63-1.76L12 3.2z" /></NavIcon>
                <span>Home</span>
              </Link>
              <Link to="/connections" style={navItemStyle(isActiveNav('/connections'))}>
                <NavIcon><path d="M15 13.5a3.5 3.5 0 1 0-2.65-5.78 4.2 4.2 0 0 1 0 5.56A3.49 3.49 0 0 0 15 13.5zM8.5 13a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm7.1 1.9c-1.1 0-2.06.34-2.76.92A6.57 6.57 0 0 1 15.4 20h4.9a1 1 0 0 0 .94-1.34c-.8-2.2-2.88-3.76-5.64-3.76zM8.5 15c-3.3 0-6 2.02-6.73 4.78A1 1 0 0 0 2.73 21h11.54a1 1 0 0 0 .96-1.22C14.5 17.02 11.8 15 8.5 15z" /></NavIcon>
                <span>My Network</span>
              </Link>
              <Link to="/jobs" style={navItemStyle(isActiveNav('/jobs'))}>
                <NavIcon><path d="M9 4a3 3 0 0 0-3 3v1H4a2 2 0 0 0-2 2v2h20v-2a2 2 0 0 0-2-2h-2V7a3 3 0 0 0-3-3H9zm1 4V7a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1h-4zm12 6H2v5a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5z" /></NavIcon>
                <span>Jobs</span>
              </Link>
              <Link to="/messages" style={navItemStyle(isActiveNav('/messages'))}>
                <NavIcon><path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8.4L7 21v-4H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm3.2 5a1 1 0 1 0 0 2h9.6a1 1 0 1 0 0-2H7.2zm0 3.5a1 1 0 1 0 0 2h6.4a1 1 0 1 0 0-2H7.2z" /></NavIcon>
                <span>Messaging</span>
              </Link>
              <Link to="/analytics" style={navItemStyle(isActiveNav('/analytics'))}>
                <NavIcon><path d="M3 20h18a1 1 0 1 0 0-2h-1V9a1 1 0 0 0-1-1h-3a1 1 0 0 0-1 1v9h-2V5a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v13H6v-7a1 1 0 0 0-1-1H2v9a1 1 0 0 0 1 1z" /></NavIcon>
                <span>Analytics</span>
              </Link>
            </>
          )}
          {isRecruiter && (
            <>
              <Link to="/home" style={navItemStyle(location.pathname.startsWith('/home'))}>
                <NavIcon><path d="M12 3.2L3.2 10.4a1 1 0 0 0 .63 1.76H6V20a1 1 0 0 0 1 1h3.8a1 1 0 0 0 1-1v-4h.4v4a1 1 0 0 0 1 1H17a1 1 0 0 0 1-1v-7.84h2.17a1 1 0 0 0 .63-1.76L12 3.2z" /></NavIcon>
                <span>Home</span>
              </Link>
              <Link to="/recruiter" style={navItemStyle(isActiveNav('/recruiter'))}>
                <NavIcon><path d="M3 20h18a1 1 0 1 0 0-2h-1V9a1 1 0 0 0-1-1h-3a1 1 0 0 0-1 1v9h-2V5a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v13H6v-7a1 1 0 0 0-1-1H2v9a1 1 0 0 0 1 1z" /></NavIcon>
                <span>Dashboard</span>
              </Link>
              <Link to="/connections" style={navItemStyle(isActiveNav('/connections'))}>
                <NavIcon><path d="M15 13.5a3.5 3.5 0 1 0-2.65-5.78 4.2 4.2 0 0 1 0 5.56A3.49 3.49 0 0 0 15 13.5zM8.5 13a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm7.1 1.9c-1.1 0-2.06.34-2.76.92A6.57 6.57 0 0 1 15.4 20h4.9a1 1 0 0 0 .94-1.34c-.8-2.2-2.88-3.76-5.64-3.76zM8.5 15c-3.3 0-6 2.02-6.73 4.78A1 1 0 0 0 2.73 21h11.54a1 1 0 0 0 .96-1.22C14.5 17.02 11.8 15 8.5 15z" /></NavIcon>
                <span>My Network</span>
              </Link>
              <Link to="/messages" style={navItemStyle(isActiveNav('/messages'))}>
                <NavIcon><path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8.4L7 21v-4H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm3.2 5a1 1 0 1 0 0 2h9.6a1 1 0 1 0 0-2H7.2zm0 3.5a1 1 0 1 0 0 2h6.4a1 1 0 1 0 0-2H7.2z" /></NavIcon>
                <span>Messaging</span>
              </Link>
            </>
          )}
          <Link to="/ai" style={navItemStyle(isActiveNav('/ai'))}>
            <NavIcon><path d="M8 4a1 1 0 0 1 1 1v1h6V5a1 1 0 1 1 2 0v1a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3h-2v1.5a1 1 0 1 1-2 0V17h-2v1.5a1 1 0 1 1-2 0V17H8a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3V5a1 1 0 0 1 1-1zm1.8 6.5a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4zm4.4 0a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4z" /></NavIcon>
            <span>AI</span>
          </Link>
        </div>

        <div ref={profileMenuRef} style={{ marginLeft: 6, position: 'relative' }}>
          <button
            onClick={() => setShowProfileMenu(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '4px 8px', borderRadius: 18,
              border: '1px solid #d1d5db',
              background: 'white',
              color: '#374151', cursor: 'pointer', fontSize: 13, height: 34,
            }}>
            {profileInfo?.photoUrl ? (
              <img src={profileInfo.photoUrl} alt="Profile" style={{ width: 24, height: 24, borderRadius: '50%', objectFit: 'cover' }} />
            ) : (
              <span style={{ width: 24, height: 24, borderRadius: '50%', background: '#dbeafe', color: '#1d4ed8', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>
                {(user.name || 'U').charAt(0).toUpperCase()}
              </span>
            )}
            <span>Me</span>
            <span style={{ fontSize: 10 }}>▼</span>
          </button>

          {showProfileMenu && (
            <div style={{
              position: 'absolute', right: 0, top: 44, width: 332,
              background: 'white', border: '1px solid #dde3ea', borderRadius: 10,
              boxShadow: '0 6px 18px rgba(0,0,0,0.14)', overflow: 'hidden', zIndex: 200,
            }}>
              <div style={{ display: 'flex', gap: 12, padding: '12px 14px 10px', borderBottom: '1px solid #eef0f2' }}>
                {profileInfo?.photoUrl ? (
                  <img src={profileInfo.photoUrl} alt="Profile" style={{ width: 66, height: 66, borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }} />
                ) : (
                  <div style={{ width: 66, height: 66, borderRadius: '50%', background: '#0a66c2', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 24, flexShrink: 0 }}>
                    {(profileInfo?.name || user.name || 'U').charAt(0).toUpperCase()}
                  </div>
                )}
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 21, fontWeight: 700, color: '#1f2328', lineHeight: 1.1 }}>
                    {profileInfo?.name || user.name}
                  </div>
                  {profileInfo?.description && (
                    <div style={{ marginTop: 6, fontSize: 13, color: '#5f6670', lineHeight: 1.35 }}>
                      {profileInfo.description}
                    </div>
                  )}
                </div>
              </div>
              <div style={{ padding: '9px 14px 10px', borderBottom: '1px solid #eef0f2' }}>
                <Link
                  to={isRecruiter ? `/recruiter/profile?recruiter_id=${encodeURIComponent(user.id)}` : '/profile'}
                  onClick={() => setShowProfileMenu(false)}
                  style={{
                    display: 'block',
                    width: '100%',
                    boxSizing: 'border-box',
                    textAlign: 'center',
                    padding: '6px 10px',
                    borderRadius: 999,
                    border: '1.5px solid #0a66c2',
                    color: '#0a66c2',
                    textDecoration: 'none',
                    fontWeight: 700,
                    fontSize: 15,
                    lineHeight: 1.1,
                  }}>
                  View profile
                </Link>
              </div>
              <button
                onClick={handleLogout}
                style={{
                  width: '100%', border: 'none', background: 'white',
                  textAlign: 'left', padding: '11px 14px', fontSize: 15, lineHeight: 1.2,
                  color: '#3f4650', cursor: 'pointer',
                }}>
                Sign Out
              </button>
            </div>
          )}
        </div>
        </div>
      </nav>

      <div style={{ ...contentWrapperStyle, width: '100%', flex: 1 }}>
        <Routes>
          <Route path="/"            element={<Navigate to={isRecruiter ? '/recruiter' : '/home'} replace />} />
          <Route path="/home"        element={<HomeFeedPage />} />
          <Route path="/home/saved"  element={<HomeFeedPage />} />
          <Route path="/career-resources" element={<CareerResourcesPage />} />
          <Route path="/jobs"        element={<JobsPage />} />
          <Route path="/jobs/browse" element={<JobsBrowsePage />} />
          <Route path="/profile"     element={<ProfilePage />} />
          <Route path="/messages"    element={<MessagesPage />} />
          <Route path="/analytics"   element={<AnalyticsDashboard />} />
          <Route path="/connections" element={<ConnectionsPage />} />
          <Route path="/recruiter"   element={isRecruiter ? <RecruiterPage /> : <Navigate to="/home" replace />} />
          <Route path="/recruiter/profile" element={<RecruiterProfileViewPage />} />
          <Route path="/ai"          element={<AIAssistantPage />} />
        </Routes>
      </div>

      <footer style={{ background: '#fff', borderTop: '1px solid #e5e7eb' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 10, color: '#6b7280', fontSize: 13 }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontWeight: 700, color: '#0a66c2' }}>
            <span style={{ width: 22, height: 22, borderRadius: 4, background: '#0a66c2', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 14, lineHeight: 1 }}>in</span>
            <span style={{ color: '#0a66c2' }}>LinkedIn</span>
          </div>
          <span style={{ color: '#6b7280' }}>LinkedIn Corporation © {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
}
