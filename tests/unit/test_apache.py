# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Unit tests for Apache module."""

from subprocess import CalledProcessError
from unittest.mock import ANY, MagicMock, call, patch

import pytest

from apache import Apache


class TestBuildVhostConfig:
    """Tests for build_vhost_config method."""

    def test_build_vhost_config_substitutes_domain_and_port(self):
        """Test that domain and port are correctly substituted in template."""
        apache = Apache()
        vhost_config = apache.build_vhost_config("example.com", 8080)

        # Assert domain and port are set
        assert "ServerName example.com" in vhost_config
        assert "VirtualHost *:8080" in vhost_config

        # Assert security headers are present in config
        assert "X-Frame-Options" in vhost_config
        assert "X-Content-Type-Options" in vhost_config
        assert "X-XSS-Protection" in vhost_config
        assert "Referrer-Policy" in vhost_config

        # Assert that DocumentRoot is set correctly
        assert "DocumentRoot /var/www/html/versions" in vhost_config


class TestInstall:
    """Tests for install method."""

    @patch("apache.Apache.reload")
    @patch("apache.UBUNTU_DESKTOP_VERSIONS_SITE")
    @patch("apache.DEFAULT_SITE")
    @patch("apache.run")
    def test_install_enables_required_modules(
        self, mock_run, mock_default_site, mock_udv_site, mock_reload
    ):
        """Test that install enables headers, deflate, and expires modules."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        mock_default_site.unlink = MagicMock()
        mock_udv_site.unlink = MagicMock()
        mock_udv_site.symlink_to = MagicMock()

        apache = Apache()
        apache.install()

        # Verify a2enmod was called for each module
        expected_calls = [
            call(
                ["a2enmod", "headers"],
                check=True,
                stdout=ANY,
                stderr=ANY,
                text=True,
                timeout=60,
            ),
            call(
                ["a2enmod", "deflate"],
                check=True,
                stdout=ANY,
                stderr=ANY,
                text=True,
                timeout=60,
            ),
            call(
                ["a2enmod", "expires"],
                check=True,
                stdout=ANY,
                stderr=ANY,
                text=True,
                timeout=60,
            ),
        ]

        for expected_call in expected_calls:
            assert any(
                actual_call[0][0] == expected_call[0][0] for actual_call in mock_run.call_args_list
            ), f"Expected call {expected_call[0][0]} not found"

    @patch("apache.Apache.reload")
    @patch("apache.UBUNTU_DESKTOP_VERSIONS_SITE")
    @patch("apache.DEFAULT_SITE")
    @patch("apache.run")
    def test_install_disables_default_site(
        self, mock_run, mock_default_site, mock_udv_site, mock_reload
    ):
        """Test that install disables the default Apache site and enables the ubuntu-desktop-versions site."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        mock_default_site.unlink = MagicMock()
        mock_udv_site.unlink = MagicMock()
        mock_udv_site.symlink_to = MagicMock()

        apache = Apache()
        apache.install()

        mock_default_site.unlink.assert_called_once_with(missing_ok=True)

        mock_udv_site.unlink.assert_called_once_with(missing_ok=True)
        mock_udv_site.symlink_to.assert_called_once_with(
            "../sites-available/ubuntu-desktop-versions.conf"
        )

    @patch("apache.Apache.reload")
    @patch("apache.UBUNTU_DESKTOP_VERSIONS_SITE")
    @patch("apache.DEFAULT_SITE")
    @patch("apache.run")
    def test_install_calls_reload(self, mock_run, mock_default_site, mock_udv_site, mock_reload):
        """Test that install calls reload after configuration."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        mock_default_site.unlink = MagicMock()
        mock_udv_site.unlink = MagicMock()
        mock_udv_site.symlink_to = MagicMock()

        apache = Apache()
        apache.install()

        mock_reload.assert_called_once()

    @patch("apache.Apache.reload")
    @patch("apache.UBUNTU_DESKTOP_VERSIONS_SITE")
    @patch("apache.DEFAULT_SITE")
    @patch("apache.run")
    @patch("apache.logger")
    def test_install_logs_warning_on_module_failure(
        self, mock_logger, mock_run, mock_default_site, mock_udv_site, mock_reload
    ):
        """Test that install logs warning but continues if module enable fails."""
        error = CalledProcessError(1, "a2enmod")
        error.stdout = "Module already enabled"
        mock_run.side_effect = [
            error,
            MagicMock(stdout="", returncode=0),
            MagicMock(stdout="", returncode=0),
        ]
        mock_default_site.unlink = MagicMock()
        mock_udv_site.unlink = MagicMock()
        mock_udv_site.symlink_to = MagicMock()

        apache = Apache()
        apache.install()

        # Verify warning was logged
        assert mock_logger.warning.called


class TestConfigure:
    """Tests for configure method."""

    @patch("apache.Apache.reload")
    @patch("apache.VHOST_FILE")
    def test_configure_writes_new_config(self, mock_vhost_file, mock_reload):
        """Test that configure writes config when file doesn't exist."""
        mock_vhost_file.exists.return_value = False
        mock_vhost_file.write_text = MagicMock()

        apache = Apache()
        apache.configure("<VirtualHost>test</VirtualHost>")

        mock_vhost_file.write_text.assert_called_once_with("<VirtualHost>test</VirtualHost>")
        mock_reload.assert_called_once()

    @patch("apache.Apache.reload")
    @patch("apache.VHOST_FILE")
    def test_configure_writes_changed_config(self, mock_vhost_file, mock_reload):
        """Test that configure writes config when content has changed."""
        mock_vhost_file.exists.return_value = True
        mock_vhost_file.read_text.return_value = "<VirtualHost>old</VirtualHost>"
        mock_vhost_file.write_text = MagicMock()

        apache = Apache()
        apache.configure("<VirtualHost>new</VirtualHost>")

        mock_vhost_file.write_text.assert_called_once_with("<VirtualHost>new</VirtualHost>")
        mock_reload.assert_called_once()

    @patch("apache.Apache.reload")
    @patch("apache.VHOST_FILE")
    def test_configure_skips_unchanged_config(self, mock_vhost_file, mock_reload):
        """Test that configure skips write and reload when config unchanged."""
        config_content = "<VirtualHost>unchanged</VirtualHost>"
        mock_vhost_file.exists.return_value = True
        mock_vhost_file.read_text.return_value = config_content
        mock_vhost_file.write_text = MagicMock()

        apache = Apache()
        apache.configure(config_content)

        mock_vhost_file.write_text.assert_not_called()
        mock_reload.assert_not_called()


class TestReload:
    """Tests for reload method."""

    @patch("apache.run")
    def test_reload_calls_systemctl(self, mock_run):
        """Test that reload calls systemctl reload apache2."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        apache = Apache()
        apache.reload()

        mock_run.assert_called_once_with(
            ["systemctl", "reload", "apache2"],
            check=True,
            stdout=ANY,
            stderr=ANY,
            text=True,
            timeout=60,
        )

    @patch("apache.run")
    def test_reload_raises_on_failure(self, mock_run):
        """Test that reload raises CalledProcessError on failure."""
        error = CalledProcessError(1, "systemctl reload apache2")
        error.stdout = "Failed"
        mock_run.side_effect = error

        apache = Apache()
        with pytest.raises(CalledProcessError):
            apache.reload()
