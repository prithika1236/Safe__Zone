import React from 'react';
import {
  LayoutDashboard,
  FileText,
  Map,
  Compass,
  Car,
  Radio,
  ShieldCheck,
  Users,
  BarChart3,
  ShieldAlert,
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab }) {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'crimes', label: 'Crime Management', icon: FileText },
    { id: 'map', label: 'SafeZone Map', icon: Map },
    { id: 'prp', label: 'PRP Optimization', icon: Compass },
    { id: 'patrols', label: 'Patrols & Units', icon: Car },
    { id: 'police', label: 'Police Management', icon: Users },
    { id: 'sos', label: 'SOS Monitoring', icon: Radio },
    { id: 'help_points', label: 'Safe Help Points', icon: ShieldCheck },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-badge">
          <ShieldAlert size={22} color="#3b82f6" />
        </div>
        <div className="logo-text">
          <span className="brand-title">SAFEZONE</span>
          <span className="brand-sub">OPERATIONS CENTER</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-group-title">COMMAND & CONTROL</div>
        <ul className="nav-links">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <li
                key={item.id}
                className={`nav-item ${isActive ? 'active' : ''}`}
                onClick={() => setActiveTab(item.id)}
              >
                <Icon size={18} className="nav-icon" />
                <span className="nav-label">{item.label}</span>
                {isActive && <div className="active-indicator" />}
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <div className="system-pill">
          <div className="status-dot-pulse" />
          <span>PostGIS • DL BiLSTM • OR-Tools</span>
        </div>
      </div>
    </aside>
  );
}
