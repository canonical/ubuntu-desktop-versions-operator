#!/usr/bin/env python3
# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
from subprocess import CalledProcessError

import ops
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError

from ubuntu_desktop_versions import Versions

logger = logging.getLogger(__name__)


class UbuntuDesktopVersionsOperatorCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.on.generate_versions_report_action, self._on_generate_versions_report
        )

        self._versions = Versions()

    def _on_install(self, event: ops.InstallEvent):
        """Handle install event."""
        self.unit.status = ops.MaintenanceStatus("Setting up environment")
        try:
            self._versions.install()
        except (CalledProcessError, PackageError, PackageNotFoundError):
            self.unit.status = ops.BlockedStatus(
                "Failed to set up the environment. Check `juju debug-log` for details."
            )
            return

        self.unit.status = ops.ActiveStatus()

    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""
        self.unit.status = ops.MaintenanceStatus("Updating ubuntu-desktop-versions checkout")

        try:
            version = self._versions.update_checkout()
            self.unit.set_workload_version(version)
        except CalledProcessError:
            self.unit.status = ops.BlockedStatus(
                "Failed to start services. Check `juju debug-log` for details."
            )
            return

        self.unit.status = ops.ActiveStatus()

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        """Handle configuration changes."""
        # Placeholder for future configuration handling
        # Will be used for domain, flavor, distro-series, etc.
        logger.debug("Configuration changed")
        self.unit.status = ops.ActiveStatus()

    def _on_generate_versions_report(self, event: ops.ActionEvent):
        """Generate package version comparison reports."""
        self.unit.status = ops.MaintenanceStatus("Generating version reports")

        event.log("Generating version reports, this may take a while (15-60 minutes)")
        success = self._versions.generate_reports()

        if success:
            event.log("Report generation completed successfully")
            self.unit.status = ops.ActiveStatus()
        else:
            event.log("Report generation failed")
            event.fail("Report generation failed. Check `juju debug-log` for details.")
            self.unit.status = ops.ActiveStatus()


if __name__ == "__main__":  # pragma: nocover
    ops.main(UbuntuDesktopVersionsOperatorCharm)
