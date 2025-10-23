# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Integration tests for ubuntu-desktop-versions-operator charm."""

import jubilant

from . import APP_NAME, retry

APACHE2 = "apache2"


def deploy_wait_func(status):
    """Wait function to ensure the app is active after deploy."""
    apache_active = status.apps[APACHE2].is_active
    desktop_versions_active = status.apps[APP_NAME].is_active
    return apache_active and desktop_versions_active


def test_deploy(juju: jubilant.Juju, ubuntu_desktop_versions_charm):
    """Test deploying the charm with apache2 as principal."""
    # Deploy apache2 principal charm
    juju.deploy(APACHE2, channel="latest/stable")

    # Deploy the subordinate charm
    juju.deploy(ubuntu_desktop_versions_charm, app=APP_NAME)

    # Integrate the charms (apache2 provides apache-website interface)
    juju.integrate(APP_NAME, APACHE2)

    # Wait for both apps to be active
    juju.wait(deploy_wait_func, timeout=600)


def test_charm_is_active(juju: jubilant.Juju):
    """Test that the charm reaches active status."""
    status = juju.status()
    assert status.apps[APP_NAME].is_active
    assert status.apps[APACHE2].is_active

    # Check that subordinate unit exists under the principal unit
    apache_units = list(status.apps[APACHE2].units.values())
    assert len(apache_units) > 0

    # Subordinate units are accessed via the principal unit
    subordinates = apache_units[0].subordinates
    assert len(subordinates) > 0

    # Check the subordinate unit is active
    subordinate_unit = list(subordinates.values())[0]
    assert subordinate_unit.is_active


@retry(retry_num=5, retry_sleep_sec=2)
def test_crontab_is_configured(juju: jubilant.Juju):
    """Test that the crontab is properly configured."""
    status = juju.status()

    # Get the apache2 unit (principal) since subordinate runs on it
    apache_units = list(status.apps[APACHE2].units.keys())
    assert len(apache_units) > 0
    principal_unit = apache_units[0]

    # Check crontab exists for www-data user (charm sets up crontab for www-data)
    result = juju.exec("sudo", "crontab", "-l", "-u", "www-data", unit=principal_unit)

    # Verify crontab contains ubuntu-desktop-versions entry
    assert "ubuntu-desktop-versions" in result.stdout


def test_config_change(juju: jubilant.Juju):
    """Test that config changes are handled correctly."""
    # Change configuration
    juju.config(APP_NAME, {"domain": "example.com", "port": 8080})

    # Wait for charm to settle
    juju.wait(jubilant.all_active, timeout=300)

    # Verify charm is still active after config change
    status = juju.status()
    assert status.apps[APP_NAME].is_active


@retry(retry_num=5, retry_sleep_sec=2)
def test_apache_vhost_configured(juju: jubilant.Juju):
    """Test that the subordinate charm's Apache vhost is configured and active."""
    status = juju.status()

    # Get the apache2 unit (principal)
    apache_units = list(status.apps[APACHE2].units.values())
    assert len(apache_units) > 0
    principal_unit = list(status.apps[APACHE2].units.keys())[0]

    # Get the unit's IP address
    unit_address = apache_units[0].public_address

    # Curl the apache2 server on port 8080 (configured in test_config_change)
    result = juju.exec("curl", "-s", "-I", f"http://{unit_address}:8080", unit=principal_unit)

    # Check for security headers that the subordinate charm's vhost configures
    headers = result.stdout
    assert "X-Frame-Options: SAMEORIGIN" in headers, (
        "X-Frame-Options header not found - vhost may not be configured"
    )
    assert "X-Content-Type-Options: nosniff" in headers, (
        "X-Content-Type-Options header not found - vhost may not be configured"
    )
    assert "X-XSS-Protection: 1; mode=block" in headers, (
        "X-XSS-Protection header not found - vhost may not be configured"
    )
