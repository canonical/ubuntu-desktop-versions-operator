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
    SubordinateRelation,
)

from charm import UbuntuDesktopVersionsOperatorCharm, build_vhost_config


@pytest.fixture
def ctx():
    return Context(UbuntuDesktopVersionsOperatorCharm)


@pytest.fixture
def base_state():
    return State(leader=True)


class TestInstallEvent:
    """Tests for install event."""

    @patch("charm.Versions.setup_crontab")
    @patch("charm.Versions.install")
    def test_install_success(self, install_mock, setup_crontab_mock, ctx, base_state):
        """Test successful install event."""
        out = ctx.run(ctx.on.install(), base_state)
        assert out.unit_status == ActiveStatus()
        assert install_mock.called
        assert setup_crontab_mock.called

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


class TestStartEvent:
    """Tests for start event."""

    @patch("charm.Versions.update_checkout")
    def test_start_success(self, update_checkout_mock, ctx, base_state):
        """Test successful start event."""
        update_checkout_mock.return_value = "v1.2.3"
        out = ctx.run(ctx.on.start(), base_state)
        assert out.unit_status == ActiveStatus()
        assert update_checkout_mock.called

    @patch("charm.Versions.update_checkout")
    def test_start_failure(self, update_checkout_mock, ctx, base_state):
        """Test start event failure."""
        update_checkout_mock.side_effect = CalledProcessError(1, "git pull")
        out = ctx.run(ctx.on.start(), base_state)
        assert out.unit_status == BlockedStatus(
            "Failed to start services. Check `juju debug-log` for details."
        )
        assert update_checkout_mock.called


class TestConfigChanged:
    """Tests for config-changed event."""

    @patch("charm.UbuntuDesktopVersionsOperatorCharm._configure_apache_website")
    def test_config_changed_with_relation(self, configure_mock, ctx):
        """Test config changed event with apache-website relation."""
        rel = SubordinateRelation(
            endpoint="apache-website",
            interface="apache-website",
            remote_app_name="apache2",
        )
        state = State(relations=[rel])
        out = ctx.run(ctx.on.config_changed(), state)
        assert out.unit_status == ActiveStatus()
        assert configure_mock.called


class TestStopEvent:
    """Tests for stop event."""

    @patch("charm.Versions.disable_crontab")
    def test_stop_success(self, disable_crontab_mock, ctx, base_state):
        """Test successful stop event."""
        ctx.run(ctx.on.stop(), base_state)
        assert disable_crontab_mock.called


class TestGenerateVersionsReportAction:
    """Tests for generate-versions-report action."""

    @patch("charm.Versions.generate_reports")
    def test_generate_versions_report_success(self, generate_reports_mock, ctx, base_state):
        """Test successful generate_versions_report action."""
        generate_reports_mock.return_value = True
        out = ctx.run(ctx.on.action("generate-versions-report"), base_state)
        assert out.unit_status == ActiveStatus()
        assert generate_reports_mock.called

    @patch("charm.Versions.generate_reports")
    def test_generate_versions_report_failure(self, generate_reports_mock, ctx, base_state):
        """Test failed generate_versions_report action."""
        generate_reports_mock.return_value = False
        with pytest.raises(ActionFailed) as exc_info:
            ctx.run(ctx.on.action("generate-versions-report"), base_state)
        assert "Report generation failed" in str(exc_info.value)
        assert generate_reports_mock.called


class TestApacheWebsiteRelation:
    """Tests for apache-website relation."""

    def test_apache_website_relation_joined(self, ctx):
        """Test apache-website relation joined event."""
        rel = SubordinateRelation(
            endpoint="apache-website",
            interface="apache-website",
            remote_app_name="apache2",
        )
        state = State(relations=[rel], config={"domain": "example.com", "port": 8080})
        out = ctx.run(ctx.on.relation_joined(rel), state)
        # Verify relation data was set
        out_rel = next(iter(out.relations))
        assert out_rel.local_unit_data["domain"] == "example.com"
        assert out_rel.local_unit_data["enabled"] == "true"
        assert out_rel.local_unit_data["ports"] == "8080"
        assert out_rel.local_unit_data["site_modules"] == "headers deflate expires"
        assert "VirtualHost" in out_rel.local_unit_data["site_config"]

    def test_apache_website_relation_changed(self, ctx):
        """Test apache-website relation changed event."""
        rel = SubordinateRelation(
            endpoint="apache-website",
            interface="apache-website",
            remote_app_name="apache2",
        )
        state = State(relations=[rel], config={"domain": "test.local", "port": 80})
        out = ctx.run(ctx.on.relation_changed(rel), state)
        # Verify relation data was set
        out_rel = next(iter(out.relations))
        assert out_rel.local_unit_data["domain"] == "test.local"
        assert out_rel.local_unit_data["ports"] == "80"

    def test_apache_website_relation_default_config(self, ctx):
        """Test apache-website relation with default config values."""
        rel = SubordinateRelation(
            endpoint="apache-website",
            interface="apache-website",
            remote_app_name="apache2",
        )
        state = State(relations=[rel])
        out = ctx.run(ctx.on.relation_joined(rel), state)
        # Verify defaults are used
        out_rel = next(iter(out.relations))
        assert out_rel.local_unit_data["domain"] == "localhost"
        assert out_rel.local_unit_data["ports"] == "80"


class TestBuildVhostConfig:
    """Tests for build_vhost_config helper function."""

    def test_build_vhost_config(self):
        """Test build_vhost_config function."""
        vhost_config = build_vhost_config("example.com", 8080)

        # Verify template substitution
        assert "ServerName example.com" in vhost_config
        assert "VirtualHost *:8080" in vhost_config
