import React from 'react';
import { UserCircle, RefreshCw, LogOut } from 'lucide-react';

export default function Header({ title, subtitle, onRefresh, isRefreshing, user, onLogout }) {
  const displayName = user?.full_name || user?.email || 'Administrator';
  const displayRole = user?.role ? user.role.toUpperCase() : 'ADMIN';

  return (
    <header className="header">
      <div className="header-left">
        <h1 className="header-title">{title}</h1>
        {subtitle && <p className="header-subtitle">{subtitle}</p>}
      </div>

      <div className="header-right">
        {onRefresh && (
          <button
            className="btn btn-secondary btn-sm"
            onClick={onRefresh}
            disabled={isRefreshing}
            title="Refresh active telemetry"
          >
            <RefreshCw size={14} className={isRefreshing ? 'spin' : ''} />
            <span>{isRefreshing ? 'Refreshing...' : 'Refresh'}</span>
          </button>
        )}

        <div className="status-pill status-pill-live">
          <span className="live-dot" />
          <span>Chennai Central Grid</span>
        </div>

        <div className="user-profile-widget">
          <UserCircle size={24} color="#94a3b8" />
          <div className="user-info">
            <span className="user-name" title={user?.email || displayName}>{displayName}</span>
            <span className="user-role">{displayRole}</span>
          </div>
          {onLogout && (
            <button
              className="btn btn-secondary btn-sm logout-btn"
              onClick={onLogout}
              title="Sign Out of Admin Session"
            >
              <LogOut size={13} />
              <span>Logout</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

