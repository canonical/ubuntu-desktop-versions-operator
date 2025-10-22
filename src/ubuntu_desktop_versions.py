# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Functions for managing and interacting with the workload.

The intention is that this module could be used outside the context of a charm.
"""

import logging
import os
import shutil
from pathlib import Path
from subprocess import PIPE, STDOUT, CalledProcessError, run

import lib.charms.operator_libs_linux.v0.apt as apt
from lib.charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError

logger = logging.getLogger(__name__)

# Packages to be installed
PACKAGES = [
    "python3-launchpadlib",
    "python3-apt",
    "python3-requests",
    "python3-yaml",
    "git",
]

REPO_LOCATION = Path("/app/ubuntu-desktop-versions")
REPO_URL = "https://git.launchpad.net/ubuntu-desktop-versions"
OUTPUT_DIR = Path("/var/www/html/versions")
LOG_DIR = Path("/var/log/ubuntu-desktop-versions")


class Versions:
    """Represent a Versions instance in the workload."""

    def __init__(self, launchpad_client):
        logger.debug("Versions class init")
        self.launchpad_client = launchpad_client
        self.env = os.environ.copy()
        self.proxies = {}
        juju_http_proxy = self.env.get("JUJU_CHARM_HTTP_PROXY")
        juju_https_proxy = self.env.get("JUJU_CHARM_HTTPS_PROXY")
        if juju_http_proxy:
            logger.debug("Setting HTTP_PROXY env to %s", juju_http_proxy)
            self.env["HTTP_PROXY"] = juju_http_proxy
            self.proxies["http"] = juju_http_proxy
        if juju_https_proxy:
            logger.debug("Setting HTTPS_PROXY env to %s", juju_https_proxy)
            self.env["HTTPS_PROXY"] = juju_https_proxy
            self.proxies["https"] = juju_https_proxy

    def install(self):
        """Install the versions build dependencies."""
        # Install the deb packages needed for the service
        try:
            apt.update()
            logger.debug("Apt index refreshed.")
        except CalledProcessError as e:
            logger.error("Failed to update package cache: %s", e)
            raise

        for p in PACKAGES:
            try:
                apt.add_package(p)
                logger.debug("Package %s installed", p)
            except PackageNotFoundError:
                logger.error("Failed to find package %s in package cache", p)
                raise
            except PackageError as e:
                logger.error("Failed to install %s: %s", p, e)
                raise

        try:
            run(
                [
                    "git",
                    "clone",
                    "-b",
                    "master",
                    REPO_URL,
                    REPO_LOCATION,
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                env=self.env,
            )
            logger.debug("ubuntu-desktop-versions vcs cloned.")
        except CalledProcessError as e:
            logger.debug("Git clone of the code failed: %s", e.stdout)
            raise

        # FIXME: Patch versions.py to use anonymous login instead of
        # authenticated login. Will revert when I have access to the LP
        # bot. We will be subject to increased rate-limiting until then.
        versions_file = REPO_LOCATION / "versions.py"
        try:
            run(
                [
                    "sed",
                    "-i",
                    "s/Launchpad.login_with(/Launchpad.login_anonymously(/",
                    str(versions_file),
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Patched versions.py for anonymous login")
        except CalledProcessError as e:
            logger.error("Failed to patch versions.py: %s", e)
            raise

        # Create output directory for HTML files
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug("Output directory created: %s", OUTPUT_DIR)

        # Create log directory
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug("Log directory created: %s", LOG_DIR)

        # Set ownership to www-data for both directories.
        # Apache2 runs as www-data user, so it needs to be able to read the HTML files.
        # The cron job will also run as www-data and needs to write HTML files to OUTPUT_DIR.
        # Directories created by the charm are owned by root by default, so we need to chown them.
        try:
            shutil.chown(OUTPUT_DIR, "www-data")
            shutil.chown(LOG_DIR, "www-data")
            logger.debug("Directory ownership set to www-data")
        except (LookupError, PermissionError) as e:
            logger.warning("Failed to set directory ownership: %s", e)

    def update_checkout(self):
        """Update ubuntu-desktop-versions via checking out the repository."""
        try:
            run(
                [
                    "git",
                    "-C",
                    REPO_LOCATION,
                    "pull",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                env=self.env,
            )
            logger.debug("ubuntu-desktop-versions checkout updated.")

            result = run(
                [
                    "git",
                    "-C",
                    REPO_LOCATION,
                    "describe",
                    "--tags",
                    "--always",
                    "--dirty",
                ],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                env=self.env,
            )
            workload_version = result.stdout.strip()
            logger.debug("ubuntu-desktop-versions revision: %s", workload_version)
            return workload_version

        except CalledProcessError as e:
            logger.debug("Git pull of the ubuntu-desktop-versions repository failed: %s", e.stdout)
            raise

    def setup_crontab(self):
        """Configure the crontab for the service."""
        try:
            run(
                ["crontab", "src/crontab"],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Crontab configured.")
        except CalledProcessError as e:
            logger.error("Installation of the crontab failed: %s", e.stdout)
            raise

    def disable_crontab(self):
        """Remove the crontab for the service."""
        try:
            run(
                ["crontab", "-r"],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
            )
            logger.debug("Crontab removed.")
        except CalledProcessError as e:
            # crontab -r returns error if no crontab exists, that's okay
            logger.debug("Removal of crontab failed (may not exist): %s", e.stdout)
