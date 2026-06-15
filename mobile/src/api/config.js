import { Platform } from 'react-native';

const LOCAL_API =
  Platform.OS === 'android'
    ? 'http://10.0.2.2:5000/api'
    : 'http://127.0.0.1:5000/api';

// Doi thanh http://<IP-may-chay-backend>:5000/api khi dung Expo Go tren dien thoai that.
export const API_BASE = LOCAL_API;
