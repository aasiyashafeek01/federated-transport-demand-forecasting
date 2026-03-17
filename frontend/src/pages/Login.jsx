import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../api/auth';

const ROLES = [
  {
    key: 'authority',
    icon: '◈',
    title: 'Transit Authority',
    desc: 'Network-wide dashboard — health scores, anomaly alerts, priority routes across all operators.',
    hint: 'admin / cta2025',
    color: 'var(--amber)',
    glow: 'rgba(255,179,0,0.12)',
  },
  {
    key: 'coordinator',
    icon: '⬡',
    title: 'FL Coordinator',
    desc: 'Federated learning control — run training rounds, compare algorithms, manage operator onboarding.',
    hint: 'coord / fed2025',
    color: 'var(--cyan)',
    glow: 'rgba(0,229,255,0.12)',
  },
  {
    key: 'operator',
    icon: '◉',
    title: 'Operator',
    desc: 'Operator-level analytics — local demand forecasts, service patterns, route performance.',
    hint: 'op0–op7 / transit2025',
    color: 'var(--green)',
    glow: 'rgba(0,230,118,0.12)',
  },
];

export default function Login({ onLogin }) {
  const navigate = useNavigate();
  const [selected, setSelected] = useState(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');

  const handleSubmit = () => {
    setError('');
    const session = login(username, password);
    if (!session) { setError('Invalid credentials. Please try again.'); return; }
    onLogin(session);
    if (session.role === 'authority')   navigate('/authority');
    else if (session.role === 'coordinator') navigate('/flhub');
    else navigate(`/operator/${session.operatorId}`);
  };

  return (
    <div className="grid-bg" style={{
      minHeight: '100vh',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 32, position: 'relative', overflow: 'hidden',
    }}>
      {/* Centre radial glow */}
      <div style={{
        position: 'absolute', width: 700, height: 700, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0,229,255,0.04) 0%, transparent 65%)',
        pointerEvents: 'none',
      }} />

      <div style={{ position: 'relative', zIndex: 1, width: '100%', maxWidth: 880 }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            width: 52, height: 52, margin: '0 auto 16px',
            border: '1px solid var(--cyan)', borderRadius: 6,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22, color: 'var(--cyan)',
            background: 'rgba(0,229,255,0.08)',
            boxShadow: '0 0 20px rgba(0,229,255,0.15)',
          }}>⬡</div>
          <h1 style={{
            fontFamily: 'var(--ff-head)', fontSize: 42, fontWeight: 700,
            letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--t0)',
          }}>Transit<span style={{ color: 'var(--cyan)' }}>IQ</span></h1>
          <p style={{ fontFamily: 'var(--ff-mono)', fontSize: 11, color: 'var(--cyan)', letterSpacing: '0.2em', textTransform: 'uppercase', marginTop: 6 }}>
            Federated Transit Intelligence Platform
          </p>
        </div>

        {!selected ? (
          <>
            <p style={{ textAlign: 'center', color: 'var(--t1)', marginBottom: 28, fontSize: 13 }}>
              Select your role to continue
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16 }}>
              {ROLES.map(r => (
                <div
                  key={r.key}
                  onClick={() => { setSelected(r.key); setUsername(''); setPassword(''); setError(''); }}
                  style={{
                    background: 'var(--bg2)', border: `1px solid var(--border)`,
                    borderRadius: 6, padding: 28, cursor: 'pointer',
                    transition: 'var(--tr)',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.background = r.glow;
                    e.currentTarget.style.borderColor = r.color;
                    e.currentTarget.style.boxShadow = `0 0 20px ${r.glow}`;
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.background = 'var(--bg2)';
                    e.currentTarget.style.borderColor = 'var(--border)';
                    e.currentTarget.style.boxShadow = 'none';
                  }}
                >
                  <div style={{ fontSize: 28, color: r.color, marginBottom: 14, fontFamily: 'var(--ff-head)' }}>{r.icon}</div>
                  <div style={{ fontFamily: 'var(--ff-head)', fontSize: 18, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--t0)', marginBottom: 8 }}>
                    {r.title}
                  </div>
                  <p style={{ color: 'var(--t1)', fontSize: 12, lineHeight: 1.6, marginBottom: 14 }}>{r.desc}</p>
                  
                </div>
              ))}
            </div>
          </>
        ) : (
          <div style={{ maxWidth: 400, margin: '0 auto' }}>
            <button
              onClick={() => { setSelected(null); setError(''); }}
              style={{ background: 'none', border: 'none', color: 'var(--t2)', fontFamily: 'var(--ff-mono)', fontSize: 11, marginBottom: 24, cursor: 'pointer', letterSpacing: '0.1em' }}
            >← Back</button>

            <div className="card" style={{ padding: 32 }}>
              {(() => {
                const r = ROLES.find(x => x.key === selected);
                return (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
                      <div style={{ fontSize: 24, color: r.color }}>{r.icon}</div>
                      <div>
                        <div style={{ fontFamily: 'var(--ff-head)', fontSize: 16, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: r.color }}>
                          {r.title}
                        </div>
                        <div style={{ fontFamily: 'var(--ff-mono)', fontSize: 10, color: 'var(--t2)', marginTop: 2 }}>Sign in to continue</div>
                      </div>
                    </div>

                    <div style={{ marginBottom: 14 }}>
                      <div className="label" style={{ marginBottom: 6 }}>Username</div>
                      <input
                        className="input"
                        placeholder="Enter username"
                        value={username}
                        onChange={e => setUsername(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                        autoFocus
                      />
                    </div>

                    <div style={{ marginBottom: 20 }}>
                      <div className="label" style={{ marginBottom: 6 }}>Password</div>
                      <input
                        className="input"
                        type="password"
                        placeholder="Enter password"
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                      />
                    </div>

                    {error && (
                      <div style={{ fontFamily: 'var(--ff-mono)', fontSize: 11, color: 'var(--red)', marginBottom: 14 }}>
                        {error}
                      </div>
                    )}

                    <button className="btn btn-primary" style={{ width: '100%', borderColor: r.color, color: r.color }} onClick={handleSubmit}>
                      Sign In →
                    </button>

                    
                  </>
                );
              })()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
