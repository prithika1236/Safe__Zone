import React, { useEffect } from 'react';
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Circle,
  GeoJSON,
  useMap,
} from 'react-leaflet';
import L from 'leaflet';

// Fix default Leaflet icon paths in bundler environments
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Custom SVG Icons
const createSvgIcon = (color, text = '') =>
  L.divIcon({
    className: 'custom-map-icon',
    html: `
      <div style="
        background-color: ${color};
        width: 24px;
        height: 24px;
        border-radius: 50%;
        border: 2px solid #ffffff;
        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 10px;
        font-weight: bold;
      ">
        ${text}
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  });

const icons = {
  crimeHigh: createSvgIcon('#ef4444', '!'),
  crimeMed: createSvgIcon('#f97316', '•'),
  crimeLow: createSvgIcon('#eab308', '•'),
  prpRef: createSvgIcon('#2563eb', 'R'),
  prpDyn: createSvgIcon('#7c3aed', 'D'),
  patrol: createSvgIcon('#0284c7', 'P'),
  helpPoint: createSvgIcon('#059669', 'H'),
};

function ChangeMapView({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.setView(center, zoom || 12);
    }
  }, [center, zoom, map]);
  return null;
}

function MapAutoResize() {
  const map = useMap();
  useEffect(() => {
    map.invalidateSize();
    const timer = setTimeout(() => {
      map.invalidateSize();
    }, 200);
    return () => clearTimeout(timer);
  }, [map]);
  return null;
}

export default function LeafletMap({
  center = [13.0827, 80.2707],
  zoom = 12,
  crimes = [],
  prps = [],
  patrols = [],
  helpPoints = [],
  wardGeoJSON = null,
  showCrimes = true,
  showPRPs = true,
  showPatrols = true,
  showHelpPoints = true,
  showRiskWards = true,
  coverageRadiusKm = 3.0,
  height = '100%',
}) {
  // GeoJSON style function based on risk_level
  const getWardStyle = (feature) => {
    const level = feature.properties?.risk_level || 'LOW';
    let fillColor = '#22c55e';
    let fillOpacity = 0.15;

    if (level === 'CRITICAL') {
      fillColor = '#ef4444';
      fillOpacity = 0.45;
    } else if (level === 'HIGH') {
      fillColor = '#f97316';
      fillOpacity = 0.35;
    } else if (level === 'MEDIUM') {
      fillColor = '#eab308';
      fillOpacity = 0.25;
    }

    return {
      fillColor,
      weight: 1.2,
      opacity: 0.8,
      color: '#475569',
      fillOpacity,
    };
  };

  const onEachWard = (feature, layer) => {
    const props = feature.properties || {};
    layer.bindPopup(`
      <div style="font-family: sans-serif; min-width: 160px;">
        <strong style="font-size: 13px;">Ward ${props.Ward_No ?? props.ward_no ?? 'N/A'} (${props.Zone_Name || props.zone_name || props.Zone_No || ''})</strong>
        <hr style="margin: 4px 0; border: 0; border-top: 1px solid #e2e8f0;"/>
        <div style="font-size: 12px; color: #475569;">
          <div>Risk Grade: <strong style="color: ${props.risk_level === 'CRITICAL' ? '#ef4444' : '#2563eb'}">${props.risk_level || 'LOW'}</strong></div>
          <div>Normalized Risk: <strong>${(props.normalized_risk_score ?? 0).toFixed(3)}</strong></div>
          <div>Incidents: <strong>${props.incident_count ?? 0}</strong></div>
          <div>Dominant: <strong>${props.dominant_category || 'NONE'}</strong></div>
        </div>
      </div>
    `);
  };

  return (
    <div className="leaflet-map-wrapper" style={{ height, width: '100%', position: 'relative' }}>
      <MapContainer
        center={center}
        zoom={zoom}
        style={{ height: '100%', width: '100%', borderRadius: '8px' }}
        scrollWheelZoom={true}
      >
        <ChangeMapView center={center} zoom={zoom} />
        <MapAutoResize />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Wards Risk Choropleth Layer */}
        {showRiskWards && wardGeoJSON && (
          <GeoJSON
            key={`wards-${wardGeoJSON.features?.length || 0}-${wardGeoJSON.features?.[0]?.properties?.normalized_risk_score ?? ''}-${wardGeoJSON.features?.[0]?.properties?.risk_level ?? ''}`}
            data={wardGeoJSON}
            style={getWardStyle}
            onEachFeature={onEachWard}
          />
        )}

        {/* Safe Help Points */}
        {showHelpPoints &&
          helpPoints.map((hp, idx) => (
            <Marker key={`hp-${idx}`} position={[hp.latitude, hp.longitude]} icon={icons.helpPoint}>
              <Popup>
                <div style={{ fontFamily: 'sans-serif' }}>
                  <strong style={{ color: '#059669' }}>Safe Help Point: {hp.name}</strong>
                  <div style={{ fontSize: '11px', color: '#64748b' }}>{hp.facility_type} • Ward {hp.ward_no}</div>
                  <div style={{ fontSize: '11px', marginTop: '4px' }}>{hp.address || ''}</div>
                  <div style={{ fontSize: '11px' }}>Status: <strong>{hp.status || 'VERIFIED'}</strong></div>
                </div>
              </Popup>
            </Marker>
          ))}

        {/* Crime Incidents */}
        {showCrimes &&
          crimes.map((c, idx) => {
            const icon =
              c.severity === 'HIGH' ? icons.crimeHigh : c.severity === 'MEDIUM' ? icons.crimeMed : icons.crimeLow;
            return (
              <Marker key={`crime-${c.id || idx}`} position={[c.latitude, c.longitude]} icon={icon}>
                <Popup>
                  <div style={{ fontFamily: 'sans-serif', fontSize: '12px', maxWidth: '220px' }}>
                    <strong style={{ color: '#dc2626' }}>{c.crime_category} ({c.severity})</strong>
                    <div style={{ color: '#64748b', fontSize: '11px', marginTop: '2px' }}>
                      {c.crime_id} • Ward {c.ward_no} ({c.zone_name || ''})
                    </div>
                    <p style={{ margin: '6px 0', fontSize: '11px', color: '#1e293b' }}>{c.description}</p>
                    <div style={{ fontSize: '10px', color: '#94a3b8' }}>
                      Occurred: {c.occurred_date} {c.occurred_time || ''} • Status: {c.status}
                    </div>
                  </div>
                </Popup>
              </Marker>
            );
          })}

        {/* Patrol Response Points (PRPs) & Coverage Rings */}
        {showPRPs &&
          prps.map((p, idx) => {
            const isDyn = p.prp_type === 'DYNAMIC';
            const icon = isDyn ? icons.prpDyn : icons.prpRef;
            const ringColor = isDyn ? '#7c3aed' : '#2563eb';
            const radiusMeters = (p.coverage_radius_km || coverageRadiusKm) * 1000;

            return (
              <React.Fragment key={`prp-${p.id || idx}`}>
                <Marker position={[p.latitude, p.longitude]} icon={icon}>
                  <Popup>
                    <div style={{ fontFamily: 'sans-serif', fontSize: '12px' }}>
                      <strong style={{ color: ringColor }}>PRP Rank #{p.rank || idx + 1} ({p.prp_type || 'DYNAMIC'})</strong>
                      <div style={{ color: '#64748b', fontSize: '11px' }}>Ward {p.ward_no} • {p.zone_name}</div>
                      <div style={{ marginTop: '4px' }}>Marginal Risk Covered: <strong>{(p.risk_score || 0).toFixed(2)}</strong></div>
                      <div>Coverage Radius: <strong>{p.coverage_radius_km || coverageRadiusKm} km</strong></div>
                      <div>Status: <span className="badge badge-primary">{p.status || 'RECOMMENDED'}</span></div>
                    </div>
                  </Popup>
                </Marker>
                <Circle
                  center={[p.latitude, p.longitude]}
                  radius={radiusMeters}
                  pathOptions={{
                    color: ringColor,
                    fillColor: ringColor,
                    fillOpacity: 0.08,
                    weight: 1.5,
                    dashArray: isDyn ? '4, 4' : undefined,
                  }}
                />
              </React.Fragment>
            );
          })}

        {/* Active Patrol Units */}
        {showPatrols &&
          patrols.map((patrol, idx) => {
            if (!patrol.current_latitude || !patrol.current_longitude) return null;
            return (
              <Marker
                key={`patrol-${patrol.id || idx}`}
                position={[patrol.current_latitude, patrol.current_longitude]}
                icon={icons.patrol}
              >
                <Popup>
                  <div style={{ fontFamily: 'sans-serif', fontSize: '12px' }}>
                    <strong style={{ color: '#0284c7' }}>Patrol Unit: {patrol.unit_code}</strong>
                    <div style={{ color: '#64748b', fontSize: '11px' }}>Type: {patrol.unit_type || patrol.patrol_type || 'CAR'} • Status: {patrol.status || 'AVAILABLE'}</div>
                    <div style={{ fontSize: '11px', marginTop: '4px' }}>Lat: {patrol.current_latitude.toFixed(4)}, Lon: {patrol.current_longitude.toFixed(4)}</div>
                  </div>
                </Popup>
              </Marker>
            );
          })}
      </MapContainer>

      {/* Map Legend Overlay */}
      <div className="map-legend-card">
        <div className="legend-title">Map Layers & Legend</div>
        <div className="legend-grid">
          <div className="legend-item">
            <span className="legend-bullet" style={{ backgroundColor: '#2563eb' }} />
            <span>Ref PRP (3km)</span>
          </div>
          <div className="legend-item">
            <span className="legend-bullet" style={{ backgroundColor: '#7c3aed' }} />
            <span>Dyn PRP (3km)</span>
          </div>
          <div className="legend-item">
            <span className="legend-bullet" style={{ backgroundColor: '#0284c7' }} />
            <span>Patrol Unit</span>
          </div>
          <div className="legend-item">
            <span className="legend-bullet" style={{ backgroundColor: '#059669' }} />
            <span>Safe Help Point</span>
          </div>
          <div className="legend-item">
            <span className="legend-bullet" style={{ backgroundColor: '#ef4444' }} />
            <span>High Severity</span>
          </div>
          <div className="legend-item">
            <span className="legend-bullet" style={{ backgroundColor: '#eab308' }} />
            <span>Low Severity</span>
          </div>
        </div>
      </div>
    </div>
  );
}
