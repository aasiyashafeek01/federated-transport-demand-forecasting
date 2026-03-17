// Role-based credentials (demo auth)
const CREDENTIALS = {
  authority:   { username: 'admin',  password: 'cta2025',  role: 'authority',   label: 'Transit Authority' },
  coordinator: { username: 'coord',  password: 'fed2025',  role: 'coordinator', label: 'FL Coordinator' },
  operator0:   { username: 'op0',    password: 'transit2025', role: 'operator', operatorId: 0, label: 'South Side Transit' },
  operator1:   { username: 'op1',    password: 'transit2025', role: 'operator', operatorId: 1, label: 'West Loop Authority' },
  operator2:   { username: 'op2',    password: 'transit2025', role: 'operator', operatorId: 2, label: 'Far South Depot' },
  operator3:   { username: 'op3',    password: 'transit2025', role: 'operator', operatorId: 3, label: 'Southwest Transit' },
  operator4:   { username: 'op4',    password: 'transit2025', role: 'operator', operatorId: 4, label: 'Central Loop Operator' },
  operator5:   { username: 'op5',    password: 'transit2025', role: 'operator', operatorId: 5, label: 'North Chicago Transit' },
  operator6:   { username: 'op6',    password: 'transit2025', role: 'operator', operatorId: 6, label: 'Northwest Corridor' },
  operator7:   { username: 'op7',    password: 'transit2025', role: 'operator', operatorId: 7, label: 'Mid-South Authority' },
};

const SESSION_KEY = 'transitiq_session';

export function login(username, password) {
  const match = Object.values(CREDENTIALS).find(
    c => c.username === username.trim() && c.password === password.trim()
  );
  if (!match) return null;
  const session = { role: match.role, label: match.label, operatorId: match.operatorId ?? null };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export function getSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function logout() {
  sessionStorage.removeItem(SESSION_KEY);
}