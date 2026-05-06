import api from './apiClient';

export const startHiringAssistant  = (data)     => api.post('/agents/hiring-assistant/start', data);
export const getHiringStatus       = (trace_id) => api.post('/agents/hiring-assistant/status', { trace_id });
export const approveHiring         = (data)     => api.post('/agents/hiring-assistant/approve', data);
export const careerCoach           = (data)     => {
  if (typeof FormData !== 'undefined' && data instanceof FormData) {
    return api.post('/agents/career-coach', data, { headers: { 'Content-Type': undefined } });
  }
  return api.post('/agents/career-coach', data);
};
export const parseResume           = (data)     => api.post('/skills/parse-resume', data);

// WebSocket URL — routed through nginx /ws/ proxy, no hardcoded port needed
export const hiringWsUrl = (trace_id) => {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.host;
  return `${proto}://${host}/ws/agents/hiring-assistant/ws/${trace_id}`;
};
