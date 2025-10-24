# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Functions for managing and interacting with Apache."""

import logging
from pathlib import Path
from string import Template
from subprocess import PIPE, STDOUT, CalledProcessError, run

logger = logging.getLogger(__name__)

SHORT_TIMEOUT = 60

VHOST_TEMPLATE = Path(__file__).parent / "templates" / "apache-vhost.conf"
VHOST_FILE = Path("/etc/apache2/sites-available/ubuntu-desktop-versions.conf")
SITES_ENABLED_DIR = Path("/etc/apache2/sites-enabled")
DEFAULT_SITE = SITES_ENABLED_DIR / "000-default.conf"
UBUNTU_DESKTOP_VERSIONS_SITE = SITES_ENABLED_DIR / "ubuntu-desktop-versions.conf"


class Apache:
    """Represent an Apache instance for serving content."""

    def __init__(self):
        logger.debug("Apache class init")

    def build_vhost_config(self, domain: str, port: int) -> str:
        """Build Apache VirtualHost configuration from template.

        Args:
            domain: The domain name for the virtual host
            port: The port number for the virtual host

        Returns:
            The rendered Apache VirtualHost configuration
        """
        template_content = VHOST_TEMPLATE.read_text()
        template = Template(template_content)
        return template.substitute(domain=domain, port=port)

    def install(self):
        """Perform one-time Apache setup during charm installation."""
        # Enable required Apache modules
        modules = ["headers", "deflate", "expires"]
        for module in modules:
            try:
                run(
                    ["a2enmod", module],
                    check=True,
                    stdout=PIPE,
                    stderr=STDOUT,
                    text=True,
                    timeout=SHORT_TIMEOUT,
                )
                logger.debug("Apache module %s enabled", module)
            except CalledProcessError as e:
                logger.warning("Failed to enable Apache module %s: %s", module, e.stdout)

        # Disable default site by removing symlink
        DEFAULT_SITE.unlink(missing_ok=True)
        logger.debug("Default Apache site disabled")

        # Enable ubuntu-desktop-versions site by creating symlink
        UBUNTU_DESKTOP_VERSIONS_SITE.unlink(missing_ok=True)
        UBUNTU_DESKTOP_VERSIONS_SITE.symlink_to("../sites-available/ubuntu-desktop-versions.conf")
        logger.debug("ubuntu-desktop-versions site enabled")

        # Reload Apache to apply changes
        self.reload()

    def configure(self, vhost_config: str):
        """Configure Apache with the provided virtual host configuration.

        Only writes and reloads if the configuration has changed.

        Args:
            vhost_config: The Apache VirtualHost configuration content
        """
        # Check if configuration has changed
        if VHOST_FILE.exists() and VHOST_FILE.read_text() == vhost_config:
            logger.debug("Apache vhost configuration unchanged, skipping reload")
            return

        # Write the vhost configuration
        VHOST_FILE.write_text(vhost_config)
        logger.debug("Apache vhost configuration written to %s", VHOST_FILE)

        # Reload Apache to apply changes
        self.reload()

    def reload(self):
        """Reload Apache configuration."""
        try:
            run(
                ["systemctl", "reload", "apache2"],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                timeout=SHORT_TIMEOUT,
            )
            logger.debug("Apache reloaded")
        except CalledProcessError as e:
            logger.error("Failed to reload Apache: %s", e.stdout)
            raise
