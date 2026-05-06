import api from './apiClient';

export const searchJobs   = (params) => api.post('/jobs/search', params);
export const getJob       = (job_id) => api.post('/jobs/get', { job_id });
export const createJob    = (data)   => api.post('/jobs/create', data);
export const updateJob    = (data)   => api.post('/jobs/update', data);
export const closeJob     = (data)   => api.post('/jobs/close', data);
export const jobsByRecruiter = (recruiter_id) => api.post('/jobs/byRecruiter', { recruiter_id });
export const saveJob      = (member_id, job_id) => api.post('/jobs/save', { member_id, job_id });
export const unsaveJob    = (member_id, job_id) => api.post('/jobs/unsave', { member_id, job_id });
export const savedJobs    = (member_id) => api.post('/jobs/saved', { member_id });
