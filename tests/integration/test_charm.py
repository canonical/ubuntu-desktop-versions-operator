# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Integration tests for ubuntu-desktop-versions-operator charm."""

import jubilant
import requests

APP_NAME = "ubuntu-desktop-versions"
UNIT = f"{APP_NAME}/0"


def test_deploy(juju: jubilant.Juju, ubuntu_desktop_versions_charm):
    """Test deploying the charm."""
    # Deploy the charm
    juju.deploy(ubuntu_desktop_versions_charm, app=APP_NAME)
    juju.wait(jubilant.all_active, timeout=600)

    # Check that the unit exists and is active
    status = juju.status()
    assert status.apps[APP_NAME].is_active
    assert status.apps[APP_NAME].units[f"{APP_NAME}/0"].is_active


def test_crontab_is_configured(juju: jubilant.Juju):
    """Test that the crontab is properly configured."""
    # Check crontab exists for www-data user (charm sets up crontab for www-data)
    result = juju.exec("sudo", "crontab", "-l", "-u", "www-data", unit=UNIT)

    # Verify crontab contains ubuntu-desktop-versions entry
    assert "ubuntu-desktop-versions" in result.stdout


def test_config_change(juju: jubilant.Juju):
    """Test that config changes are handled correctly."""
    # Change configuration
    juju.config(APP_NAME, {"domain": "example.com", "port": 8080})

    # Wait for charm to settle
    juju.wait(jubilant.all_active, timeout=300)

    # Verify charm is still active after config change
    assert juju.status().apps[APP_NAME].is_active


def test_apache_service_running(juju: jubilant.Juju):
    """Test that Apache service is running."""
    result = juju.exec("systemctl", "is-active", "apache2", unit=UNIT)
    assert result.stdout.strip() == "active"


def test_apache_modules_enabled(juju: jubilant.Juju):
    """Test that required Apache modules are enabled."""
    required_modules = ["headers", "deflate", "expires"]
    for module in required_modules:
        result = juju.exec("apache2ctl", "-M", unit=UNIT)
        assert f"{module}_module" in result.stdout, f"Module {module} not enabled"


def test_apache_site_configuration(juju: jubilant.Juju):
    """Test that Apache site is properly configured."""
    # Check default site is disabled
    result = juju.exec("test", "!", "-L", "/etc/apache2/sites-enabled/000-default.conf", unit=UNIT)
    assert result.exit_code == 0, "Default site should be disabled"

    # Check ubuntu-desktop-versions site is enabled
    result = juju.exec(
        "test", "-L", "/etc/apache2/sites-enabled/ubuntu-desktop-versions.conf", unit=UNIT
    )
    assert result.exit_code == 0, "ubuntu-desktop-versions site should be enabled"


def test_apache_vhost_config_content(juju: jubilant.Juju):
    """Test that Apache vhost config file has correct content."""
    result = juju.exec(
        "cat", "/etc/apache2/sites-available/ubuntu-desktop-versions.conf", unit=UNIT
    )
    vhost_config = result.stdout

    # Verify config reflects changes from test_config_change
    assert "ServerName example.com" in vhost_config
    assert "VirtualHost *:8080" in vhost_config
    assert "DocumentRoot /var/www/html/versions" in vhost_config


def test_apache_vhost_configured(juju: jubilant.Juju):
    """Test that the charm's Apache vhost is configured and active."""
    unit_address = juju.status().apps[APP_NAME].units[f"{APP_NAME}/0"].public_address

    # Make HEAD request to the apache2 server on port 8080 (configured in test_config_change)
    response = requests.head(f"http://{unit_address}:8080", timeout=10)
    response.raise_for_status()

    # Check for security headers that the charm's vhost configures
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
