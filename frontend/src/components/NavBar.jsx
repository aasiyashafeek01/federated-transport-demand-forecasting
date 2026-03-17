import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { logout } from '../api/auth';

const ROLE_LINKS = {
  authority:   [{ to: '/authority', label: 'Network Dashboard' }],
  coordinator: [{ to: '/flhub',     label: 'FL Hub' }],
  operator:    [],
};

export default function NavBar({ session, onLogout }) {
  const navigate  = useNavigate();
  const { pathname } = useLocation();

  const links = ROLE_LINKS[session?.role] || [];

  const handleLogout = () => {
    logout();
    onLogout();
    navigate('/login');
  };

  return (
    <nav className="navbar">
      <div className="nav-logo">Transit<span>IQ</span></div>
      <div style={{ flex: 1 }} />
      {links.map(l => (
        <button
          key={l.to}
          className={`nav-link ${pathname === l.to ? 'active' : ''}`}
          onClick={() => navigate(l.to)}
        >{l.label}</button>
      ))}
      {session?.role === 'coordinator' && (
        <button
          className={`nav-link ${pathname.startsWith('/operator') ? 'active' : ''}`}
          onClick={() => navigate('/operator/0')}
        >Operator View</button>
      )}
      <div className="nav-role">{session?.label}</div>
      <button
        onClick={handleLogout}
        style={{
          background: 'none',
          border: '1px solid var(--border)',
          borderRadius: 3,
          color: 'var(--t2)',
          padding: '4px 12px',
          fontFamily: 'var(--ff-mono)',
          fontSize: 10,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          cursor: 'pointer',
          transition: 'var(--tr)',
        }}
        onMouseEnter={e => { e.target.style.color = 'var(--red)'; e.target.style.borderColor = 'rgba(255,68,68,0.4)'; }}
        onMouseLeave={e => { e.target.style.color = 'var(--t2)';  e.target.style.borderColor = 'var(--border)'; }}
      >Sign Out</button>
    </nav>
  );
}
