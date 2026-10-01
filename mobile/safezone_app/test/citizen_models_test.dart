import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:safezone_app/models/citizen_models.dart';
import 'package:safezone_app/shared/config.dart';

void main() {
  group('Citizen Models JSON Deserialization & Serialization', () {
    test('EmergencyContact.fromJson parses contact payload correctly', () {
      final json = {
        'id': 15,
        'user_id': 42,
        'name': 'Priya Sharma',
        'phone_number': '9876543210',
        'relationship_type': 'Spouse',
        'is_primary': true,
        'created_at': '2026-09-22T00:00:00Z',
      };

      final contact = EmergencyContact.fromJson(json);
      expect(contact.id, 15);
      expect(contact.userId, 42);
      expect(contact.name, 'Priya Sharma');
      expect(contact.phoneNumber, '9876543210');
      expect(contact.relationshipType, 'Spouse');
      expect(contact.isPrimary, true);
      expect(contact.createdAt, DateTime.parse('2026-09-22T00:00:00Z'));
    });

    test('EmergencyContact.toJson generates valid dictionary', () {
      final contact = EmergencyContact(
        id: 1,
        userId: 42,
        name: 'John Doe',
        phoneNumber: '9123456780',
        relationshipType: 'Parent',
        isPrimary: false,
        createdAt: DateTime.parse('2026-09-22T00:00:00Z'),
      );

      final map = contact.toJson();
      expect(map['id'], 1);
      expect(map['user_id'], 42);
      expect(map['name'], 'John Doe');
      expect(map['phone_number'], '9123456780');
      expect(map['relationship_type'], 'Parent');
      expect(map['is_primary'], false);
    });

    test('SafeHelpPoint.fromJson parses verified help point and coordinates', () {
      final json = {
        'id': 3,
        'name': 'Kilpauk 24x7 Help Booth',
        'facility_type': 'POLICE_BOOTH',
        'latitude': 13.0800,
        'longitude': 80.2400,
        'address': 'Kilpauk Garden Road, Chennai',
        'phone_number': '044-26441122',
        'is_verified': true,
        'is_active': true,
        'created_at': '2026-09-22T00:00:00Z',
      };

      final shp = SafeHelpPoint.fromJson(json);
      expect(shp.id, 3);
      expect(shp.name, 'Kilpauk 24x7 Help Booth');
      expect(shp.facilityType, 'POLICE_BOOTH');
      expect(shp.latitude, 13.0800);
      expect(shp.longitude, 80.2400);
      expect(shp.coordinates, const LatLng(13.0800, 80.2400));
      expect(shp.address, 'Kilpauk Garden Road, Chennai');
      expect(shp.phoneNumber, '044-26441122');
      expect(shp.isVerified, true);
      expect(shp.isActive, true);
    });

    test('CitizenSOSResponse.fromJson parses active SOS and responder details without leaking strategic PRP data', () {
      final json = {
        'id': 10,
        'status': 'EN_ROUTE',
        'triggered_at': '2026-09-22T00:10:00Z',
        'notes': 'Immediate assistance requested',
        'approximate_distance_km': 1.45,
        'estimated_arrival_minutes': 3,
      };

      final sos = CitizenSOSResponse.fromJson(json);
      expect(sos.id, 10);
      expect(sos.status, 'EN_ROUTE');
      expect(sos.notes, 'Immediate assistance requested');
      expect(sos.approximateDistanceKm, 1.45);
      expect(sos.estimatedArrivalMinutes, 3);
      expect(sos.isActive, true);
    });

    test('CitizenSOSResponse.isActive is false for RESOLVED or NO_AVAILABLE_PATROL status', () {
      final resolvedJson = {
        'id': 11,
        'status': 'RESOLVED',
        'triggered_at': '2026-09-22T00:10:00Z',
      };
      expect(CitizenSOSResponse.fromJson(resolvedJson).isActive, false);

      final unassignedJson = {
        'id': 12,
        'status': 'NO_AVAILABLE_PATROL',
        'triggered_at': '2026-09-22T00:10:00Z',
      };
      expect(CitizenSOSResponse.fromJson(unassignedJson).isActive, false);
    });

    test('CitizenSOSResponse parses history payload with resolved_at correctly', () {
      final json = {
        'id': 105,
        'status': 'RESOLVED',
        'triggered_at': '2026-09-22T00:10:00Z',
        'resolved_at': '2026-09-22T00:25:00Z',
        'notes': 'Resolved on site',
        'approximate_distance_km': 2.1,
      };

      final sos = CitizenSOSResponse.fromJson(json);
      expect(sos.id, 105);
      expect(sos.status, 'RESOLVED');
      expect(sos.resolvedAt, isNotNull);
      expect(sos.resolvedAt, DateTime.parse('2026-09-22T00:25:00Z'));
      expect(sos.notes, 'Resolved on site');
      expect(sos.approximateDistanceKm, 2.1);
      expect(sos.isActive, false);
    });

    test('AppConfig.healthUrl correctly derives root /health endpoint from /api/v1', () {
      expect(AppConfig.healthUrl.endsWith('/health'), true);
      expect(AppConfig.healthUrl.contains('/api/v1/health'), false);
    });

    test('AppConfig.getSosWebSocketUrl derives correct ws:// protocol and endpoint', () {
      final wsUrl = AppConfig.getSosWebSocketUrl(42);
      expect(wsUrl.startsWith('ws://') || wsUrl.startsWith('wss://'), true);
      expect(wsUrl.contains('/sos/ws/42'), true);
    });

    test('AppConfig.formatAndValidateApiUrl formats valid IPv4 and URLs correctly', () {
      expect(AppConfig.formatAndValidateApiUrl('192.168.1.5'), 'http://192.168.1.5:8000/api/v1');
      expect(AppConfig.formatAndValidateApiUrl('192.168.1.5:8080'), 'http://192.168.1.5:8080/api/v1');
      expect(AppConfig.formatAndValidateApiUrl('http://192.168.1.5:8000'), 'http://192.168.1.5:8000/api/v1');
      expect(AppConfig.formatAndValidateApiUrl('http://192.168.1.5:8000/api/v1'), 'http://192.168.1.5:8000/api/v1');
      expect(AppConfig.formatAndValidateApiUrl('http://192.168.1.5:8000/api/v1/'), 'http://192.168.1.5:8000/api/v1');
      expect(AppConfig.formatAndValidateApiUrl('localhost'), 'http://localhost:8000/api/v1');
      expect(AppConfig.formatAndValidateApiUrl('localhost:3000'), 'http://localhost:3000/api/v1');
      expect(AppConfig.formatAndValidateApiUrl('https://api.safezone.app/api/v1'), 'https://api.safezone.app/api/v1');
    });

    test('AppConfig.formatAndValidateApiUrl rejects invalid inputs', () {
      expect(() => AppConfig.formatAndValidateApiUrl(''), throwsA(isA<FormatException>()));
      expect(() => AppConfig.formatAndValidateApiUrl('   '), throwsA(isA<FormatException>()));
      expect(() => AppConfig.formatAndValidateApiUrl('999.1.1.1'), throwsA(isA<FormatException>()));
      expect(() => AppConfig.formatAndValidateApiUrl('192.168.1.1:70000'), throwsA(isA<FormatException>()));
      expect(() => AppConfig.formatAndValidateApiUrl('invalid_host'), throwsA(isA<FormatException>()));
    });

    test('AppConfig.deriveHealthUrl handles various base URLs correctly', () {
      expect(AppConfig.deriveHealthUrl('http://192.168.1.5:8000/api/v1'), 'http://192.168.1.5:8000/health');
      expect(AppConfig.deriveHealthUrl('http://192.168.1.5:8000/api/v1/'), 'http://192.168.1.5:8000/health');
      expect(AppConfig.deriveHealthUrl('http://10.0.2.2:8000/api/v1'), 'http://10.0.2.2:8000/health');
      expect(AppConfig.deriveHealthUrl('https://api.safezone.app/api/v1'), 'https://api.safezone.app/health');
    });

    test('AppConfig custom URL override and reset functionality', () async {
      final defaultUrl = AppConfig.defaultApiBaseUrl;
      expect(AppConfig.apiBaseUrl, isNotEmpty);

      await AppConfig.setCustomApiBaseUrl('192.168.1.99');
      expect(AppConfig.apiBaseUrl, 'http://192.168.1.99:8000/api/v1');
      expect(AppConfig.isCustomConfigured, true);

      await AppConfig.resetApiBaseUrl();
      expect(AppConfig.apiBaseUrl, defaultUrl);
      expect(AppConfig.isCustomConfigured, false);
    });
  });
}

