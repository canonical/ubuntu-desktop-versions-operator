# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Unit tests for the ubuntu_desktop_versions module."""

from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import MagicMock, patch

import pytest

from ubuntu_desktop_versions import (
    LOG_DIR,
    OUTPUT_DIR,
    PACKAGES,
    REPO_LOCATION,
    REPO_URL,
    Versions,
)


@pytest.fixture
def versions():
    """Create a Versions instance."""
    return Versions()


class TestVersionsInit:
    """Tests for Versions.__init__()."""

    def test_init_with_http_proxy(self, monkeypatch):
        """Test that HTTP proxy is configured from environment."""
        monkeypatch.setenv("JUJU_CHARM_HTTP_PROXY", "http://proxy.example.com:8080")
        monkeypatch.setenv("JUJU_CHARM_HTTPS_PROXY", "https://proxy.example.com:8443")
        versions = Versions()

        assert versions.env["HTTP_PROXY"] == "http://proxy.example.com:8080"
        assert versions.proxies["http"] == "http://proxy.example.com:8080"
        assert versions.env["HTTPS_PROXY"] == "https://proxy.example.com:8443"
        assert versions.proxies["https"] == "https://proxy.example.com:8443"


class TestInstall:
    """Tests for Versions.install()."""

    @patch("ubuntu_desktop_versions.apt")
    @patch("ubuntu_desktop_versions.run")
    @patch("ubuntu_desktop_versions.shutil.chown")
    @patch.object(Path, "mkdir")
    def test_install_success(self, mock_mkdir, mock_chown, mock_run, mock_apt, versions):
        """Test successful installation."""
        # Mock subprocess.run for git clone
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        # Run install
        versions.install()

        # Verify apt operations
        mock_apt.update.assert_called_once()
        assert mock_apt.add_package.call_count == len(PACKAGES)
        for package in PACKAGES:
            mock_apt.add_package.assert_any_call(package)

        # Verify git clone
        call_args = mock_run.call_args_list[0]
        assert call_args[0][0] == ["git", "clone", "-b", "master", REPO_URL, REPO_LOCATION]
        assert call_args[1]["env"] == versions.env

        # Verify directories created
        assert mock_mkdir.call_count == 2

        # Verify ownership changed
        assert mock_chown.call_count == 2
        mock_chown.assert_any_call(OUTPUT_DIR, "www-data")
        mock_chown.assert_any_call(LOG_DIR, "www-data")

    @patch("ubuntu_desktop_versions.apt")
    def test_install_apt_update_fails(self, mock_apt, versions):
        """Test that install raises when apt update fails."""
        from subprocess import CalledProcessError

        mock_apt.update.side_effect = CalledProcessError(1, "apt-get update")

        with pytest.raises(CalledProcessError):
            versions.install()

    @patch("ubuntu_desktop_versions.apt")
    def test_install_package_not_found(self, mock_apt, versions):
        """Test that install raises when package is not found."""
        from lib.charms.operator_libs_linux.v0.apt import PackageNotFoundError

        mock_apt.add_package.side_effect = PackageNotFoundError("test-package")

        with pytest.raises(PackageNotFoundError):
            versions.install()


class TestUpdateCheckout:
    """Tests for Versions.update_checkout()."""

    @patch("ubuntu_desktop_versions.run")
    def test_update_checkout_success(self, mock_run, versions):
        """Test successful repository update."""
        # Mock git pull
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="Already up to date."),
            MagicMock(returncode=0, stdout="v1.2.3-4-gabcdef\n"),
        ]

        version = versions.update_checkout()

        assert version == "v1.2.3-4-gabcdef"
        assert mock_run.call_count == 2

        # Verify git pull command
        first_call = mock_run.call_args_list[0]
        assert first_call[0][0] == ["git", "-C", REPO_LOCATION, "pull"]

        # Verify git describe command
        second_call = mock_run.call_args_list[1]
        assert second_call[0][0] == [
            "git",
            "-C",
            REPO_LOCATION,
            "describe",
            "--tags",
            "--always",
            "--dirty",
        ]

    @patch("ubuntu_desktop_versions.run")
    def test_update_checkout_git_pull_fails(self, mock_run, versions):
        """Test that update_checkout raises when git pull fails."""
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "git pull", output="error")

        with pytest.raises(CalledProcessError):
            versions.update_checkout()


class TestSetupCrontab:
    """Tests for Versions.setup_crontab() and Versions.disable_crontab()."""

    @patch("ubuntu_desktop_versions.run")
    def test_setup_crontab_success(self, mock_run, versions):
        """Test successful crontab setup."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        versions.setup_crontab()

        # Verify crontab command was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["crontab", "src/crontab"]
        assert call_args[1]["check"] is True

    @patch("ubuntu_desktop_versions.run")
    def test_setup_crontab_fails(self, mock_run, versions):
        """Test that setup_crontab raises when crontab installation fails."""
        mock_run.side_effect = CalledProcessError(1, "crontab", output="error")

        with pytest.raises(CalledProcessError):
            versions.setup_crontab()

    @patch("ubuntu_desktop_versions.run")
    def test_disable_crontab_success(self, mock_run, versions):
        """Test successful crontab removal."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        versions.disable_crontab()

        # Verify crontab -r was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["crontab", "-r"]
        assert call_args[1]["check"] is True
