// Call the canonical host directly. The apex domain responds with a 308
// redirect, which can break POST login/register requests on native clients.
const DEPLOYED_API = 'https://www.flowmate.pro/api';
const DEPLOYED_WEB = 'https://www.flowmate.pro';

const ENV_API = process.env.EXPO_PUBLIC_API_BASE_URL;

// Set EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:5000/api khi can test backend local.
export const API_BASE = ENV_API && ENV_API.trim() ? ENV_API.trim() : DEPLOYED_API;
export const PRIVACY_URL = `${DEPLOYED_WEB}/privacy`;
export const TERMS_URL = `${DEPLOYED_WEB}/terms`;
