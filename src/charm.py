#!/usr/bin/env python3
# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
from pathlib import Path
from string import Template
from subprocess import CalledProcessError

import ops
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError

from ubuntu_desktop_versions import Versions

logger = logging.getLogger(__name__)

APACHE_VHOST_TEMPLATE = Path(__file__).parent / "templates" / "apache-vhost.conf"


def build_vhost_config(domain: str, port: int) -> str:
    """Build Apache VirtualHost configuration from template.

    Args:
        domain: The domain name for the virtual host
        port: The port number for the virtual host

    Returns:
        The rendered Apache VirtualHost configuration
    """
    template_content = APACHE_VHOST_TEMPLATE.read_text()
    template = Template(template_content)
    return template.substitute(domain=domain, port=port)


class UbuntuDesktopVersionsOperatorCharm(ops.CharmBase):
    """Charmed Operator for Ubuntu Desktop Versions scripts."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(
            self.on.generate_versions_report_action, self._on_generate_versions_report
        )
        self.framework.observe(
            self.on.apache_website_relation_joined, self._on_apache_website_relation_joined
        )
        self.framework.observe(
            self.on.apache_website_relation_changed, self._on_apache_website_relation_changed
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

        self.unit.status = ops.MaintenanceStatus("Setting up crontab")
        self._versions.setup_crontab()

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

        # Update apache-website relation if it exists
        for relation in self.model.relations.get("apache-website", []):
            self._configure_apache_website(relation)

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

    def _on_apache_website_relation_joined(self, event: ops.RelationJoinedEvent):
        """Handle apache-website relation joined."""
        logger.info("Apache website relation joined")
        self._configure_apache_website(event.relation)

    def _on_apache_website_relation_changed(self, event: ops.RelationChangedEvent):
        """Handle apache-website relation changed."""
        logger.info("Apache website relation changed")
        self._configure_apache_website(event.relation)

    def _configure_apache_website(self, relation: ops.Relation):
        """Configure the apache-website relation."""
        domain = str(self.config.get("domain", "localhost"))
        port = int(self.config.get("port", 80))

        # Build Apache VirtualHost configuration
        vhost_config = build_vhost_config(domain, port)

        # Set relation data
        relation.data[self.unit]["domain"] = domain
        relation.data[self.unit]["enabled"] = "true"
        relation.data[self.unit]["site_config"] = vhost_config
        relation.data[self.unit]["site_modules"] = "headers deflate expires"
        relation.data[self.unit]["ports"] = str(port)

        logger.info("Configured apache-website relation for domain: %s on port %s", domain, port)

    def _on_stop(self, event: ops.StopEvent):
        """Handle stop event."""
        self.unit.status = ops.MaintenanceStatus("Removing crontab")

        try:
            self._versions.disable_crontab()
        except CalledProcessError as e:
            logger.exception("Failed to disable the crontab: %s", e)
            return


if __name__ == "__main__":  # pragma: nocover
    ops.main(UbuntuDesktopVersionsOperatorCharm)
