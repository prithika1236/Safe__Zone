import React, { useState, useEffect } from 'react';
import { authApi } from './services/api';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import CrimeManagementPage from './pages/CrimeManagementPage';
import SafeZoneMapPage from './pages/SafeZoneMapPage';
import PRPOptimizationPage from './pages/PRPOptimizationPage';
import PatrolsPage from './pages/PatrolsPage';
import PolicePage from './pages/PolicePage';
import SOSMonitoringPage from './pages/SOSMonitoringPage';
import SafeHelpPointsPage from './pages/SafeHelpPointsPage';
import AnalyticsPage from './pages/AnalyticsPage';

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [isVerifyingAuth, setIsVerifyingAuth] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [refreshKey, setRefreshKey] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    const verifySession = async () => {
      const token = localStorage.getItem('safezone_token');
      if (!token) {
        setCurrentUser(null);
        setIsVerifyingAuth(false);
        return;
      }

      try {
        const user = await authApi.me();
        if (user && user.role?.toUpperCase() === 'ADMIN') {
          setCurrentUser(user);
        } else {
          // Token belongs to non-admin or is unauthorized for dashboard
          authApi.logout();
          setCurrentUser(null);
        }
      } catch (err) {
        authApi.logout();
        setCurrentUser(null);
      } finally {
        setIsVerifyingAuth(false);
      }
    };

    verifySession();
  }, []);

  const handleGlobalRefresh = () => {
    setIsRefreshing(true);
    setRefreshKey((prev) => prev + 1);
    setTimeout(() => {
      setIsRefreshing(false);
    }, 600);
  };

  const handleLoginSuccess = (user) => {
    setCurrentUser(user);
  };

  const handleLogout = () => {
    authApi.logout();
    setCurrentUser(null);
  };

  const getPageHeader = () => {
    switch (activeTab) {
      case 'dashboard':
        return {
          title: 'Operations Dashboard',
          subtitle: 'Real-time city security overview, live deployment grid, and critical metrics',
        };
      case 'crimes':
        return {
          title: 'Crime Incident Management',
          subtitle: 'BiLSTM AI classification, human-in-the-loop review, and incident verification',
        };
      case 'map':
        return {
          title: 'SafeZone Geospatial GIS Map',
          subtitle: 'Interactive risk heatmaps, ward choropleth boundaries, PRPs, and fleet positioning',
        };
      case 'prp':
        return {
          title: 'Patrol Required Point (PRP) Optimization',
          subtitle: 'Google OR-Tools Integer Linear Programming for maximal unique crime-risk coverage',
        };
      case 'patrols':
        return {
          title: 'Patrol Resources & Dispatch',
          subtitle: 'Patrol vehicle fleet, field readiness, shift management, and active assignments',
        };
      case 'police':
        return {
          title: 'Police Force Administration',
          subtitle: 'Officer accounts, credentials, rank permissions, and station duty status',
        };
      case 'sos':
        return {
          title: 'Emergency SOS Incident Monitoring',
          subtitle: 'Live distress beacons, citizen panic alerts, and urgent police dispatch',
        };
      case 'help_points':
        return {
          title: 'Safe Help Points & Public Sanctuaries',
          subtitle: '24/7 designated safety shelters, emergency medical facilities, and police kiosks',
        };
      case 'analytics':
        return {
          title: 'Analytics & Evaluation Benchmarks',
          subtitle: 'AI classifier accuracy, mathematical coverage gains, and response time evaluation',
        };
      default:
        return {
          title: 'SafeZone Command Center',
          subtitle: 'AI-Assisted Police Patrol Deployment & Emergency Response System',
        };
    }
  };

  // 1. Initial startup token/session verification screen
  if (isVerifyingAuth) {
    return (
      <div className="auth-loading-screen">
        <div className="auth-loading-card">
          <div className="auth-loading-spinner" />
          <p className="auth-loading-title">SAFEZONE COMMAND CENTER</p>
          <p className="auth-loading-sub">Verifying administrative security credentials...</p>
        </div>
      </div>
    );
  }

  // 2. Unauthenticated / Non-Admin screen -> Render Admin Login
  if (!currentUser) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  // 3. Authenticated Admin Session -> Render Dashboard
  const { title, subtitle } = getPageHeader();

  return (
    <div className="app-container">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      <div className="main-content">
        <Header
          title={title}
          subtitle={subtitle}
          onRefresh={handleGlobalRefresh}
          isRefreshing={isRefreshing}
          user={currentUser}
          onLogout={handleLogout}
        />

        <main className="page-body" key={refreshKey}>
          {activeTab === 'dashboard' && <DashboardPage />}
          {activeTab === 'crimes' && <CrimeManagementPage />}
          {activeTab === 'map' && <SafeZoneMapPage />}
          {activeTab === 'prp' && <PRPOptimizationPage />}
          {activeTab === 'patrols' && <PatrolsPage />}
          {activeTab === 'police' && <PolicePage />}
          {activeTab === 'sos' && <SOSMonitoringPage />}
          {activeTab === 'help_points' && <SafeHelpPointsPage />}
          {activeTab === 'analytics' && <AnalyticsPage />}
        </main>
      </div>
    </div>
  );
}

