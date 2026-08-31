import pytest
from fastapi import HTTPException
from apps.core import security

def test_provision_limits_accept_normal_plan():
    security.settings.max_vps_ram_mb = 65536
    security.settings.max_vps_cpu_percent = 1200
    security.settings.max_vps_disk_mb = 262144
    security.validate_provision_limits(4096, 200, 20480)

def test_provision_limits_reject_excessive_ram():
    security.settings.max_vps_ram_mb = 8192
    with pytest.raises(HTTPException):
        security.validate_provision_limits(16384, 200, 20480)

def test_signature_is_not_equal_for_different_body():
    security.settings.internal_api_secret = "test-secret-012345678901234567890123"
    a = security._signature("123", "100", "POST", "/api/v1/servers", b"a")
    b = security._signature("123", "100", "POST", "/api/v1/servers", b"b")
    assert a != b
