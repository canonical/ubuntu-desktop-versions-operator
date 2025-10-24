#!/usr/bin/env python3
# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
from subprocess import CalledProcessError

import ops
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer as IngressRequirer

from apache import Apache
from ubuntu_desktop_versions import Versions

logger = logging.getLogger(__name__)


class UbuntuDesktopVersionsOperatorCharm(ops.CharmBase):
    """Charmed Operator for Ubuntu Desktop Versions scripts."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)

        # Initialize ingress integration
        port = int(self.config.get("port", 80))
        self.ingress = IngressRequirer(self, port=port, strip_prefix=True, relation_name="ingress")

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.refresh_reports_action, self._on_refresh_reports)
        self.framework.observe(self.on.update_checkout_action, self._on_update_checkout)

        # Observe ingress events
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

        self._versions = Versions()
        self._apache = Apache()

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

        self.unit.status = ops.MaintenanceStatus("Setting up crontab")
        self._versions.setup_crontab()

        self.unit.status = ops.MaintenanceStatus("Installing Apache")
        try:
            self._apache.install()
        except CalledProcessError:
            self.unit.status = ops.BlockedStatus(
                "Failed to install Apache. Check `juju debug-log` for details."
            )
            return

        self.unit.status = ops.MaintenanceStatus("Configuring Apache")
        domain = str(self.config.get("domain", "localhost"))
        port = int(self.config.get("port", 80))
        vhost_config = self._apache.build_vhost_config(domain, port)

        try:
            self._apache.configure(vhost_config)
        except CalledProcessError:
            self.unit.status = ops.BlockedStatus(
                "Failed to configure Apache. Check `juju debug-log` for details."
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
        logger.debug("Configuration changed")

        # Reconfigure Apache with the new settings
        domain = str(self.config.get("domain", "localhost"))
        port = int(self.config.get("port", 80))
        vhost_config = self._apache.build_vhost_config(domain, port)

        try:
            self._apache.configure(vhost_config)
        except CalledProcessError:
            self.unit.status = ops.BlockedStatus(
                "Failed to configure Apache. Check `juju debug-log` for details."
            )
            return

        # Reconfigure ingress with the new port
        self.ingress.provide_ingress_requirements(port=port)

        self.unit.status = ops.ActiveStatus()

    def _on_refresh_reports(self, event: ops.ActionEvent):
        """Manually refresh and regenerate package version comparison reports.

        This handler is invoked only when the user explicitly runs the refresh-reports
        action via `juju run`. It is not called during normal operation or by the cron job.
        The cron job directly invokes the report generation scripts independently.
        """
        self.unit.status = ops.MaintenanceStatus("Generating version reports")

        event.log("Generating version reports, this may take a while (15-60 minutes)")
        success = self._versions.generate_reports()

        if success:
            event.log("Report generation completed successfully")
        else:
            event.log("Report generation failed")
            event.fail("Report generation failed. Check `juju debug-log` for details.")

        self.unit.status = ops.ActiveStatus()

    def _on_update_checkout(self, event: ops.ActionEvent):
        """Manually update the ubuntu-desktop-versions git repository checkout.

        This handler is invoked when the user explicitly runs the update-checkout
        action via `juju run`. It pulls the latest changes from the upstream repository
        and updates the workload version.
        """
        self.unit.status = ops.MaintenanceStatus("Updating ubuntu-desktop-versions checkout")

        event.log("Updating ubuntu-desktop-versions git repository")
        try:
            version = self._versions.update_checkout()
            self.unit.set_workload_version(version)
            event.log(f"Update completed successfully. Current version: {version}")
            event.set_results({"version": version})
        except CalledProcessError:
            event.log("Update failed")
            event.fail("Failed to update checkout. Check `juju debug-log` for details.")
        self.unit.status = ops.ActiveStatus()

    def _on_ingress_ready(self, event):
        """Handle ingress ready event."""
        logger.info("Ingress is ready at %s", self.ingress.url)

    def _on_ingress_revoked(self, event):
        """Handle ingress revoked event."""
        logger.info("Ingress has been revoked")


if __name__ == "__main__":  # pragma: nocover
    ops.main(UbuntuDesktopVersionsOperatorCharm)
