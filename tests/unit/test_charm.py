# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Unit tests for the charm.

These tests only cover those methods that do not require internet access,
and do not attempt to manipulate the underlying machine.
"""

from subprocess import CalledProcessError
from unittest.mock import patch

import pytest
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError
from ops.testing import (
    ActionFailed,
    ActiveStatus,
    BlockedStatus,
    Context,
    State,
    TCPPort,
)

from charm import UbuntuDesktopVersionsOperatorCharm


@pytest.fixture
def ctx():
    return Context(UbuntuDesktopVersionsOperatorCharm)


@pytest.fixture
def base_state():
    return State(leader=True)


class TestInstallEvent:
    """Tests for install event."""

    @patch("charm.Apache.configure")
    @patch("charm.Apache.build_vhost_config")
    @patch("charm.Apache.install")
    @patch("charm.Versions.setup_crontab")
    @patch("charm.Versions.install")
    def test_install_success(
        self,
        versions_install_mock,
        setup_crontab_mock,
        apache_install_mock,
        build_vhost_mock,
        apache_configure_mock,
        ctx,
        base_state,
    ):
        """Test successful install event."""
        build_vhost_mock.return_value = "<VirtualHost>test config</VirtualHost>"
        out = ctx.run(ctx.on.install(), base_state)
        assert out.unit_status == ActiveStatus()
        assert versions_install_mock.called
        assert setup_crontab_mock.called
        assert apache_install_mock.called
        assert build_vhost_mock.called
        assert apache_configure_mock.called

    @patch("charm.Versions.install")
    @pytest.mark.parametrize(
        "exception", [PackageError, PackageNotFoundError, CalledProcessError(1, "foo")]
    )
    def test_install_failure_during_setup(self, mock, exception, ctx, base_state):
        """Test install event failure during environment setup."""
        mock.side_effect = exception
        out = ctx.run(ctx.on.install(), base_state)
        assert out.unit_status == BlockedStatus(
            "Failed to set up the environment. Check `juju debug-log` for details."
        )

    @patch("charm.Apache.install")
    @patch("charm.Versions.setup_crontab")
    @patch("charm.Versions.install")
    def test_install_failure_during_apache_install(
        self, versions_install_mock, setup_crontab_mock, apache_install_mock, ctx, base_state
    ):
        """Test install event failure during Apache installation."""
        apache_install_mock.side_effect = CalledProcessError(1, "a2enmod")
        out = ctx.run(ctx.on.install(), base_state)
        assert out.unit_status == BlockedStatus(
            "Failed to install Apache. Check `juju debug-log` for details."
        )

    @patch("charm.Apache.configure")
    @patch("charm.Apache.build_vhost_config")
    @patch("charm.Apache.install")
    @patch("charm.Versions.setup_crontab")
    @patch("charm.Versions.install")
    def test_install_failure_during_apache_config(
        self,
        versions_install_mock,
        setup_crontab_mock,
        apache_install_mock,
        build_vhost_mock,
        apache_configure_mock,
        ctx,
        base_state,
    ):
        """Test install event failure during Apache configuration."""
        build_vhost_mock.return_value = "<VirtualHost>test config</VirtualHost>"
        apache_configure_mock.side_effect = CalledProcessError(1, "systemctl reload apache2")
        out = ctx.run(ctx.on.install(), base_state)
        assert out.unit_status == BlockedStatus(
            "Failed to configure Apache. Check `juju debug-log` for details."
        )


class TestStartEvent:
    """Tests for start event."""

    @patch("charm.Versions.update_checkout")
    def test_start_success(self, update_checkout_mock, ctx, base_state):
        """Test successful start event."""
        update_checkout_mock.return_value = "v1.2.3"
        out = ctx.run(ctx.on.start(), base_state)
        assert out.unit_status == ActiveStatus()
        assert update_checkout_mock.called
        assert out.opened_ports == {TCPPort(port=80, protocol="tcp")}

    @patch("charm.Versions.update_checkout")
    def test_start_failure(self, update_checkout_mock, ctx, base_state):
        """Test start event failure."""
        update_checkout_mock.side_effect = CalledProcessError(1, "git pull")
        out = ctx.run(ctx.on.start(), base_state)
        assert out.unit_status == BlockedStatus(
            "Failed to start services. Check `juju debug-log` for details."
        )
        assert update_checkout_mock.called
        assert out.opened_ports == set()


class TestConfigChanged:
    """Tests for config-changed event."""

    @patch("charm.IngressRequirer.provide_ingress_requirements")
    @patch("charm.Apache.configure")
    @patch("charm.Apache.build_vhost_config")
    def test_config_changed_success(
        self, build_vhost_mock, configure_mock, ingress_mock, ctx, base_state
    ):
        """Test config changed event successfully reconfigures Apache and ingress."""
        build_vhost_mock.return_value = "<VirtualHost>test config</VirtualHost>"
        out = ctx.run(ctx.on.config_changed(), base_state)
        assert out.unit_status == ActiveStatus()
        assert build_vhost_mock.called
        assert configure_mock.called
        ingress_mock.assert_called_once_with(port=80)
        assert out.opened_ports == {TCPPort(port=80, protocol="tcp")}

    @patch("charm.IngressRequirer.provide_ingress_requirements")
    @patch("charm.Apache.configure")
    @patch("charm.Apache.build_vhost_config")
    def test_config_changed_with_custom_config(
        self, build_vhost_mock, configure_mock, ingress_mock, ctx
    ):
        """Test config changed with custom domain and port."""
        build_vhost_mock.return_value = "<VirtualHost *:8080>ServerName example.com</VirtualHost>"
        state = State(config={"domain": "example.com", "port": 8080})
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ActiveStatus()
        # Verify build_vhost_config was called with the right values
        build_vhost_mock.assert_called_once_with("example.com", 8080)
        assert configure_mock.called
        # Verify ingress was updated with the new port
        ingress_mock.assert_called_once_with(port=8080)
        assert out.opened_ports == {TCPPort(port=8080, protocol="tcp")}

    @patch("charm.IngressRequirer.provide_ingress_requirements")
    @patch("charm.Apache.configure")
    @patch("charm.Apache.build_vhost_config")
    def test_config_changed_failure(
        self, build_vhost_mock, configure_mock, ingress_mock, ctx, base_state
    ):
        """Test config changed event failure during Apache reconfiguration."""
        build_vhost_mock.return_value = "<VirtualHost>test config</VirtualHost>"
        configure_mock.side_effect = CalledProcessError(1, "systemctl reload apache2")
        out = ctx.run(ctx.on.config_changed(), base_state)
        assert out.unit_status == BlockedStatus(
            "Failed to configure Apache. Check `juju debug-log` for details."
        )
        # Ingress should not be updated if Apache configuration fails
        assert not ingress_mock.called
        assert out.opened_ports == set()


class TestRefreshReportsAction:
    """Tests for refresh-reports action."""

    @patch("charm.Versions.generate_reports")
    def test_refresh_reports_success(self, generate_reports_mock, ctx, base_state):
        """Test successful manual report refresh action."""
        generate_reports_mock.return_value = True
        out = ctx.run(ctx.on.action("refresh-reports"), base_state)
        assert out.unit_status == ActiveStatus()
        assert generate_reports_mock.called

    @patch("charm.Versions.generate_reports")
    def test_refresh_reports_failure(self, generate_reports_mock, ctx, base_state):
        """Test failed manual report refresh action."""
        generate_reports_mock.return_value = False
        with pytest.raises(ActionFailed) as exc_info:
            ctx.run(ctx.on.action("refresh-reports"), base_state)
        assert "Report generation failed" in str(exc_info.value)
        assert generate_reports_mock.called


class TestUpdateCheckoutAction:
    """Tests for update-checkout action."""

    @patch("charm.Versions.update_checkout")
    def test_update_checkout_success(self, update_checkout_mock, ctx, base_state):
        """Test successful manual checkout update action."""
        update_checkout_mock.return_value = "v1.2.3"
        out = ctx.run(ctx.on.action("update-checkout"), base_state)
        assert out.unit_status == ActiveStatus()
        assert update_checkout_mock.called

    @patch("charm.Versions.update_checkout")
    def test_update_checkout_failure(self, update_checkout_mock, ctx, base_state):
        """Test failed manual checkout update action."""
        update_checkout_mock.side_effect = CalledProcessError(1, "git pull")
        with pytest.raises(ActionFailed) as exc_info:
            ctx.run(ctx.on.action("update-checkout"), base_state)
        assert "Failed to update checkout" in str(exc_info.value)


class TestApache:
    """Tests for Apache class methods."""

    def test_build_vhost_config(self):
        """Test build_vhost_config method."""
        from apache import Apache

        apache = Apache()
        vhost_config = apache.build_vhost_config("example.com", 8080)

        # Verify template substitution
        assert "ServerName example.com" in vhost_config
        assert "VirtualHost *:8080" in vhost_config
        assert "DocumentRoot /var/www/html/versions" in vhost_config
        # Verify security headers are present
        assert "X-Frame-Options" in vhost_config
        assert "X-Content-Type-Options" in vhost_config
        assert "X-XSS-Protection" in vhost_config
        assert "Referrer-Policy" in vhost_config
