import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { getSession } from './api/auth';
import Login from './pages/Login';
import FLHub from './pages/FLHub';
import AuthorityDashboard from './pages/AuthorityDashboard';
import OperatorPortal from './pages/OperatorPortal';

function RequireAuth({ children, session }) {
  if (!session) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const [session, setSession] = useState(getSession());

  const handleLogin  = (s) => setSession(s);
  const handleLogout = () => setSession(null);

  // After login redirect based on role
  function DefaultRedirect() {
    if (!session) return <Navigate to="/login" replace />;
    if (session.role === 'authority')   return <Navigate to="/authority" replace />;
    if (session.role === 'coordinator') return <Navigate to="/flhub" replace />;
    if (session.role === 'operator')    return <Navigate to={`/operator/${session.operatorId}`} replace />;
    return <Navigate to="/login" replace />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login onLogin={handleLogin} />} />
        <Route path="/" element={<DefaultRedirect />} />
        <Route path="/flhub" element={
          <RequireAuth session={session}>
            <FLHub session={session} onLogout={handleLogout} />
          </RequireAuth>
        } />
        <Route path="/authority" element={
          <RequireAuth session={session}>
            <AuthorityDashboard session={session} onLogout={handleLogout} />
          </RequireAuth>
        } />
        <Route path="/operator/:id" element={
          <RequireAuth session={session}>
            <OperatorPortal session={session} onLogout={handleLogout} />
          </RequireAuth>
        } />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
