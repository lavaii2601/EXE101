import { Platform } from 'react-native';

const LOCAL_API =
  Platform.OS === 'android'
    ? 'http://10.0.2.2:5000/api'
    : 'http://127.0.0.1:5000/api';

const ENV_API = process.env.EXPO_PUBLIC_API_BASE_URL;

// Set EXPO_PUBLIC_API_BASE_URL=http://<IP-may-chay-backend>:5000/api
// khi dung Expo Go tren dien thoai that hoac backend deploy rieng.
export const API_BASE = ENV_API && ENV_API.trim() ? ENV_API.trim() : LOCAL_API;
