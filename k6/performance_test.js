import http from 'k6/http';
import { sleep, check } from 'k6';

const targetUrl = __ENV.TARGET_URL || 'http://localhost:18080/api/leaderboard/top?limit=20';
const mode = __ENV.K6_MODE || 'stages';

function buildOptions(selectedMode) {
  if (selectedMode === 'fixed') {
    return {
      vus: Number(__ENV.K6_VUS || 1),
      duration: __ENV.K6_DURATION || '30s',
    };
  }
  return {
    stages: [
      { duration: '30s', target: 1 },     // 1 user
      { duration: '30s', target: 50 },    // 50 users
      { duration: '30s', target: 200 },   // 200 users
      { duration: '30s', target: 500 },   // 500 users
      { duration: '30s', target: 2000 },  // 2000 users
      { duration: '30s', target: 0 },     // ramp-down
    ],
  };
}

export const options = buildOptions(mode);

export default function () {
  const res = http.get(targetUrl, { timeout: '15s' });
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(1);
}
