import api from './apiClient';

export const createMember  = (data)      => api.post('/members/create', data);
export const getMember     = (member_id) => api.post('/members/get', { member_id });
export const updateMember  = (data)      => api.post('/members/update', data);
export const searchMembers = (params)    => api.post('/members/search', params);

export const getRecruiter    = (recruiter_id) => api.post('/recruiters/get', { recruiter_id });
export const updateRecruiter = (data)       => api.post('/recruiters/update', data);
