import React, { useState, useEffect } from 'react';
import {
  Layers,
  MapPin,
  Shield,
  Car,
  FileText,
  Compass,
  RefreshCw,
  Eye,
  EyeOff,
} from 'lucide-react';
import { crimesApi, prpApi, policeApi, riskApi, helpPointsApi } from '../services/api';
import LeafletMap from '../components/LeafletMap';

export default function SafeZoneMapPage() {
  const [crimes, setCrimes] = useState([]);
  const [prps, setPRPs] = useState([]);
  const [patrols, setPatrols] = useState([]);
  const [helpPoints, setHelpPoints] = useState([]);
  const [wardGeoJSON, setWardGeoJSON] = useState(null);
  const [loading, setLoading] = useState(false);

  // Layer Visibility Controls
  const [showCrimes, setShowCrimes] = useState(true);
  const [showPRPs, setShowPRPs] = useState(true);
  const [showPatrols, setShowPatrols] = useState(true);
  const [showHelpPoints, setShowHelpPoints] = useState(true);
  const [showRiskWards, setShowRiskWards] = useState(true);

  // Risk Mode Controls
  const [riskMode, setRiskMode] = useState('DYNAMIC');
  const [riskShift, setRiskShift] = useState('ALL');

  useEffect(() => {
    loadMapLayers();
  }, [riskMode, riskShift]);

  const loadMapLayers = async () => {
    setLoading(true);
    try {
      // 1. Fetch crimes
      const crimeRes = await crimesApi.list({ limit: 200 }).catch(() => ({ items: [] }));
      setCrimes(crimeRes.items || []);

      // 2. Fetch active PRPs
      const prpRes = await prpApi.getActive().catch(() => []);
      setPRPs(Array.isArray(prpRes) ? prpRes : []);

      // 3. Fetch patrol units
      const unitRes = await policeApi.listUnits().catch(() => []);
      setPatrols(Array.isArray(unitRes) ? unitRes : []);

      // 4. Fetch risk geojson
      const geo = await riskApi.getGeoJSON({ mode: riskMode, time_period: riskShift }).catch(() => null);
      if (geo) setWardGeoJSON(geo);

      // 5. Load safe help points
      const defaultHelpPoints = [
        { name: 'Rajiv Gandhi General Hospital', facility_type: 'HOSPITAL', ward_no: 60, latitude: 13.0818, longitude: 80.2785, status: 'VERIFIED' },
        { name: 'Teynampet Police Station', facility_type: 'POLICE_STATION', ward_no: 119, latitude: 13.0415, longitude: 80.2520, status: 'VERIFIED' },
        { name: 'Apollo 24/7 Emergency Pharmacy', facility_type: 'PHARMACY_24_7', ward_no: 111, latitude: 13.0600, longitude: 80.2500, status: 'VERIFIED' },
        { name: 'Marina Beach Help Kiosk', facility_type: 'COMMUNITY_KIOSK', ward_no: 115, latitude: 13.0500, longitude: 80.2824, status: 'VERIFIED' },
      ];
      try {
        const hpRes = await helpPointsApi.list().catch(() => []);
        const pts = Array.isArray(hpRes) ? hpRes : hpRes?.items || [];
        setHelpPoints(pts.length > 0 ? pts : defaultHelpPoints);
      } catch {
        setHelpPoints(defaultHelpPoints);
      }
    } catch (err) {
      console.error('Map layers fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-container map-page-layout">
      {/* Top Map Controls Bar */}
      <div className="map-toolbar">
        <div className="toolbar-left">
          <div className="layer-toggles">
            <button
              className={`layer-btn ${showRiskWards ? 'active' : ''}`}
              onClick={() => setShowRiskWards(!showRiskWards)}
            >
              <Layers size={14} />
              <span>Ward Risk ({riskMode})</span>
            </button>

            <button
              className={`layer-btn ${showPRPs ? 'active' : ''}`}
              onClick={() => setShowPRPs(!showPRPs)}
            >
              <Compass size={14} />
              <span>PRP Circles ({prps.length})</span>
            </button>

            <button
              className={`layer-btn ${showCrimes ? 'active' : ''}`}
              onClick={() => setShowCrimes(!showCrimes)}
            >
              <FileText size={14} />
              <span>Crimes ({crimes.length})</span>
            </button>

            <button
              className={`layer-btn ${showPatrols ? 'active' : ''}`}
              onClick={() => setShowPatrols(!showPatrols)}
            >
              <Car size={14} />
              <span>Patrol Units ({patrols.length})</span>
            </button>

            <button
              className={`layer-btn ${showHelpPoints ? 'active' : ''}`}
              onClick={() => setShowHelpPoints(!showHelpPoints)}
            >
              <Shield size={14} />
              <span>Help Points ({helpPoints.length})</span>
            </button>
          </div>
        </div>

        <div className="toolbar-right">
          <div className="form-group-inline">
            <label>Mode:</label>
            <select
              className="form-control form-control-sm"
              value={riskMode}
              onChange={(e) => setRiskMode(e.target.value)}
            >
              <option value="DYNAMIC">DYNAMIC (Recent/Shift)</option>
              <option value="REFERENCE">REFERENCE (Historical)</option>
            </select>
          </div>

          <div className="form-group-inline">
            <label>Shift:</label>
            <select
              className="form-control form-control-sm"
              value={riskShift}
              onChange={(e) => setRiskShift(e.target.value)}
            >
              <option value="ALL">ALL SHIFTS</option>
              <option value="MORNING">MORNING (06:00 - 12:00)</option>
              <option value="AFTERNOON">AFTERNOON (12:00 - 18:00)</option>
              <option value="EVENING">EVENING (18:00 - 22:00)</option>
              <option value="NIGHT">NIGHT (22:00 - 06:00)</option>
            </select>
          </div>

          <button className="btn btn-secondary btn-sm" onClick={loadMapLayers} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {/* Main Full View Map */}
      <div className="map-view-container">
        <LeafletMap
          crimes={crimes}
          prps={prps}
          patrols={patrols}
          helpPoints={helpPoints}
          wardGeoJSON={wardGeoJSON}
          showCrimes={showCrimes}
          showPRPs={showPRPs}
          showPatrols={showPatrols}
          showHelpPoints={showHelpPoints}
          showRiskWards={showRiskWards}
          height="100%"
        />
      </div>
    </div>
  );
}
