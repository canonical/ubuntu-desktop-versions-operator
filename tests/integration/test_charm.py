# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Integration tests for ubuntu-desktop-versions-operator charm."""

import jubilant

APP_NAME = "ubuntu-desktop-versions"
UNIT = f"{APP_NAME}/0"


def test_deploy(juju: jubilant.Juju, ubuntu_desktop_versions_charm):
    """Test deploying the charm."""
    # Deploy the charm
    juju.deploy(ubuntu_desktop_versions_charm, app=APP_NAME)
    juju.wait(jubilant.all_active, timeout=300)

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
    juju.wait(jubilant.all_active, timeout=120)

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
    assert result.return_code == 0, "Default site should be disabled"

    # Check ubuntu-desktop-versions site is enabled
    result = juju.exec(
        "test", "-L", "/etc/apache2/sites-enabled/ubuntu-desktop-versions.conf", unit=UNIT
    )
    assert result.return_code == 0, "ubuntu-desktop-versions site should be enabled"


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
