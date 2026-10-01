import React, { useState } from 'react';
import { ShieldAlert, Lock, Mail, AlertCircle, Loader2 } from 'lucide-react';
import { authApi } from '../services/api';

export default function LoginPage({ onLoginSuccess }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!email.trim() || !password) {
      setError('Please enter both email and password.');
      return;
    }

    setLoading(true);
    try {
      const data = await authApi.login(email.trim(), password);
      // Validate returned user role against actual backend value
      const user = data?.user || (await authApi.me());
      if (!user || user.role?.toUpperCase() !== 'ADMIN') {
        authApi.logout();
        setError('Access denied: Your account does not have Administrator privileges.');
        setLoading(false);
        return;
      }

      onLoginSuccess(user);
    } catch (err) {
      authApi.logout();
      if (err.response) {
        if (err.response.status === 401 || err.response.status === 400) {
          setError(err.response.data?.detail || 'Incorrect email or password.');
        } else if (err.response.status === 403) {
          setError(err.response.data?.detail || 'Access denied: Admin credentials required.');
        } else {
          setError(err.response.data?.detail || `Authentication failed (HTTP ${err.response.status}).`);
        }
      } else if (err.request) {
        setError('Unable to reach SafeZone server. Please ensure the backend is running.');
      } else {
        setError(err.message || 'An unexpected error occurred during login.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page-wrapper">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo-badge">
            <ShieldAlert size={28} color="#3b82f6" />
          </div>
          <h1 className="login-title">SAFEZONE</h1>
          <p className="login-subtitle">OPERATIONS COMMAND CENTER</p>
          <div className="login-tagline">Administrative Authentication Required</div>
        </div>

        {error && (
          <div className="login-error-banner">
            <AlertCircle size={18} className="error-icon" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="admin-email">Administrator Email</label>
            <div className="input-icon-wrapper">
              <Mail size={16} className="input-icon" />
              <input
                id="admin-email"
                type="email"
                placeholder="admin@safezone.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                disabled={loading}
                required
                className="form-input"
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="admin-password">Password</label>
            <div className="input-icon-wrapper">
              <Lock size={16} className="input-icon" />
              <input
                id="admin-password"
                type="password"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                disabled={loading}
                required
                className="form-input"
              />
            </div>
          </div>

          <button type="submit" className="btn-login" disabled={loading}>
            {loading ? (
              <>
                <Loader2 size={16} className="spin" />
                <span>Authenticating Session...</span>
              </>
            ) : (
              <span>Sign In to Command Center</span>
            )}
          </button>
        </form>

        <div className="login-footer">
          <div className="security-notice">
            <span className="security-dot" />
            <span>Authorized Law Enforcement & Admin Access Only</span>
          </div>
          <div className="system-spec">PostGIS • BiLSTM • OR-Tools Gateway</div>
        </div>
      </div>
    </div>
  );
}
