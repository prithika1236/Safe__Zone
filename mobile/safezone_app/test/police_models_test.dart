import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:safezone_app/models/police_models.dart';
import 'package:safezone_app/services/location_service.dart';

void main() {
  group('Police Models JSON Deserialization', () {
    test('OfficerProfile.fromJson parses valid payload correctly', () {
      final json = {
        'id': 101,
        'user_id': 42,
        'email': 'officer@safezone.gov',
        'full_name': 'Inspector R. Kumar',
        'phone_number': '9840112233',
        'badge_number': 'TN-POL-1001',
        'rank': 'Inspector',
        'station_name': 'T. Nagar Police Station',
        'on_duty': true,
        'is_available': true,
      };

      final profile = OfficerProfile.fromJson(json);
      expect(profile.id, 101);
      expect(profile.userId, 42);
      expect(profile.email, 'officer@safezone.gov');
      expect(profile.fullName, 'Inspector R. Kumar');
      expect(profile.badgeNumber, 'TN-POL-1001');
      expect(profile.rank, 'Inspector');
      expect(profile.stationName, 'T. Nagar Police Station');
      expect(profile.onDuty, true);
      expect(profile.isAvailable, true);
    });

    test('PRPDetails.fromJson parses coordinates and risk metrics', () {
      final json = {
        'id': 5,
        'rank': 1,
        'latitude': 13.0827,
        'longitude': 80.2707,
        'ward_no': 105,
        'zone_no': 'VI',
        'zone_name': 'Teynampet',
        'risk_score': 8.75,
        'coverage_radius_km': 3.0,
        'status': 'ACTIVE',
      };

      final prp = PRPDetails.fromJson(json);
      expect(prp.id, 5);
      expect(prp.rank, 1);
      expect(prp.latitude, 13.0827);
      expect(prp.longitude, 80.2707);
      expect(prp.coordinates, const LatLng(13.0827, 80.2707));
      expect(prp.wardNo, 105);
      expect(prp.zoneNo, 'VI');
      expect(prp.zoneName, 'Teynampet');
      expect(prp.riskScore, 8.75);
      expect(prp.coverageRadiusKm, 3.0);
    });

    test('PRPDetails.fromJson handles numeric zone_no conversion', () {
      final json = {
        'id': 6,
        'latitude': 13.0827,
        'longitude': 80.2707,
        'zone_no': 9,
      };

      final prp = PRPDetails.fromJson(json);
      expect(prp.zoneNo, '9');
    });

    test('PatrolAssignment.fromJson parses assignment lifecycle and nested PRP', () {
      final json = {
        'id': 12,
        'prp_id': 5,
        'patrol_unit_id': 3,
        'officer_id': 101,
        'shift_start': '2026-09-22T06:00:00Z',
        'shift_end': '2026-09-22T14:00:00Z',
        'status': 'ASSIGNED',
        'prp_details': {
          'id': 5,
          'latitude': 13.0827,
          'longitude': 80.2707,
          'ward_no': 105,
        },
      };

      final assignment = PatrolAssignment.fromJson(json);
      expect(assignment.id, 12);
      expect(assignment.prpId, 5);
      expect(assignment.patrolUnitId, 3);
      expect(assignment.officerId, 101);
      expect(assignment.status, 'ASSIGNED');
      expect(assignment.prpDetails, isNotNull);
      expect(assignment.prpDetails!.latitude, 13.0827);
    });

    test('PatrolAssignment.fromJson handles ACKNOWLEDGED and AT_PRP lifecycle statuses', () {
      final ackJson = {
        'id': 1,
        'prp_id': 10,
        'shift_start': '2026-09-22T06:00:00Z',
        'shift_end': '2026-09-22T14:00:00Z',
        'status': 'ACKNOWLEDGED',
      };
      final ackAssignment = PatrolAssignment.fromJson(ackJson);
      expect(ackAssignment.status, 'ACKNOWLEDGED');

      final atPrpJson = {
        'id': 1,
        'prp_id': 10,
        'shift_start': '2026-09-22T06:00:00Z',
        'shift_end': '2026-09-22T14:00:00Z',
        'status': 'AT_PRP',
      };
      final atPrpAssignment = PatrolAssignment.fromJson(atPrpJson);
      expect(atPrpAssignment.status, 'AT_PRP');
    });

    test('SOSEmergencyAlert.fromJson parses emergency alert data', () {
      final json = {
        'id': 7,
        'citizen_id': 88,
        'latitude': 13.0400,
        'longitude': 80.2500,
        'status': 'ACTIVE',
        'triggered_at': '2026-09-22T00:15:00Z',
        'notes': 'Urgent distress signal',
      };

      final sos = SOSEmergencyAlert.fromJson(json);
      expect(sos.id, 7);
      expect(sos.citizenId, 88);
      expect(sos.latitude, 13.0400);
      expect(sos.longitude, 80.2500);
      expect(sos.coordinates, const LatLng(13.0400, 80.2500));
      expect(sos.status, 'ACTIVE');
      expect(sos.notes, 'Urgent distress signal');
    });

    test('SOSEmergencyAlert.fromJson handles ASSIGNED, ACCEPTED, EN_ROUTE, ARRIVED and RESOLVED statuses', () {
      final statuses = ['ASSIGNED', 'ACCEPTED', 'EN_ROUTE', 'ARRIVED', 'RESOLVED'];
      for (final s in statuses) {
        final json = {
          'id': 10,
          'citizen_id': 99,
          'latitude': 13.0827,
          'longitude': 80.2707,
          'status': s,
          'triggered_at': '2026-09-22T01:00:00Z',
        };
        final alert = SOSEmergencyAlert.fromJson(json);
        expect(alert.status, s);
      }
    });

    test('SOSEmergencyAlert status progression model checks', () {
      // 1. Initial assigned state
      final alertAssigned = SOSEmergencyAlert.fromJson({
        'id': 1,
        'citizen_id': 10,
        'latitude': 13.0827,
        'longitude': 80.2707,
        'status': 'ASSIGNED',
        'triggered_at': '2026-09-22T01:00:00Z',
      });
      expect(alertAssigned.status, 'ASSIGNED');

      // 2. Intermediate accepted state
      final alertAccepted = SOSEmergencyAlert.fromJson({
        'id': 1,
        'citizen_id': 10,
        'latitude': 13.0827,
        'longitude': 80.2707,
        'status': 'ACCEPTED',
        'triggered_at': '2026-09-22T01:00:00Z',
      });
      expect(alertAccepted.status, 'ACCEPTED');

      // 3. En route state
      final alertEnRoute = SOSEmergencyAlert.fromJson({
        'id': 1,
        'citizen_id': 10,
        'latitude': 13.0827,
        'longitude': 80.2707,
        'status': 'EN_ROUTE',
        'triggered_at': '2026-09-22T01:00:00Z',
      });
      expect(alertEnRoute.status, 'EN_ROUTE');

      // 4. Arrived state
      final alertArrived = SOSEmergencyAlert.fromJson({
        'id': 1,
        'citizen_id': 10,
        'latitude': 13.0827,
        'longitude': 80.2707,
        'status': 'ARRIVED',
        'triggered_at': '2026-09-22T01:00:00Z',
      });
      expect(alertArrived.status, 'ARRIVED');

      // 5. Resolved state
      final alertResolved = SOSEmergencyAlert.fromJson({
        'id': 1,
        'citizen_id': 10,
        'latitude': 13.0827,
        'longitude': 80.2707,
        'status': 'RESOLVED',
        'assigned_officer_id': 101,
        'assigned_patrol_id': 3,
        'triggered_at': '2026-09-22T01:00:00Z',
        'resolved_at': '2026-09-22T01:15:00Z',
        'notes': 'All cleared',
      });
      expect(alertResolved.status, 'RESOLVED');
      expect(alertResolved.resolvedAt, isNotNull);
      expect(alertResolved.resolvedAt, DateTime.parse('2026-09-22T01:15:00Z'));
      expect(alertResolved.notes, 'All cleared');
    });
  });

  group('LocationService Distance Calculations', () {
    test('calculateDistanceKm returns accurate geodesic distance', () {
      final service = LocationService();
      // Chennai Central (13.0827, 80.2707) to T. Nagar (13.0405, 80.2337) ~ 6.1 km
      const p1 = LatLng(13.0827, 80.2707);
      const p2 = LatLng(13.0405, 80.2337);

      final distance = service.calculateDistanceKm(p1, p2);
      expect(distance, greaterThan(5.5));
      expect(distance, lessThan(6.5));
    });

    test('calculateDistanceKm returns 0 for identical coordinates', () {
      final service = LocationService();
      const p = LatLng(13.0827, 80.2707);
      final distance = service.calculateDistanceKm(p, p);
      expect(distance, closeTo(0.0, 0.001));
    });
  });
}
