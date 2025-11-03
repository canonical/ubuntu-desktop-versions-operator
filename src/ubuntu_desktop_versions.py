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

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError

logger = logging.getLogger(__name__)

SHORT_TIMEOUT = 60
MEDIUM_TIMEOUT = 300
LONG_TIMEOUT = 3600

# Packages to be installed
PACKAGES = [
    "python3-launchpadlib",
    "python3-apt",
    "python3-requests",
    "python3-yaml",
    "git",
    "apache2",
]

REPO_LOCATION = Path("/app/ubuntu-desktop-versions")
REPO_URL = "https://git.launchpad.net/ubuntu-desktop-versions"
OUTPUT_DIR = Path("/var/www/html/versions")
LOG_DIR = Path("/var/log/ubuntu-desktop-versions")
LOGROTATE_CONFIG_DST = Path("/etc/logrotate.d/ubuntu-desktop-versions")
LP_CREDENTIALS_DIR = Path("/var/lib/ubuntu-desktop-versions")
LP_CREDENTIALS_FILE = LP_CREDENTIALS_DIR / "launchpad-credentials"


class Versions:
    """Represent a Versions instance in the workload."""

    def __init__(self, launchpad_credentials: str | None = None):
        logger.debug("Versions class init")
        self.launchpad_credentials = launchpad_credentials
        self.env = os.environ.copy()
        self.env["GIT_TERMINAL_PROMPT"] = "0"
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

    def install_launchpad_credentials(self):
        """Install Launchpad credentials for authenticated access.

        The credentials must be provided during initialization.
        They will be written to a file that launchpadlib can use.
        """
        if not self.launchpad_credentials:
            logger.info("No Launchpad credentials provided")
            return

        # Create the credentials directory
        LP_CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        logger.debug("Launchpad credentials directory created: %s", LP_CREDENTIALS_DIR)

        # Write the credentials to the file
        LP_CREDENTIALS_FILE.write_text(self.launchpad_credentials)
        LP_CREDENTIALS_FILE.chmod(0o600)
        logger.debug("Launchpad credentials installed at: %s", LP_CREDENTIALS_FILE)

        # Set ownership to www-data for the credentials directory and file
        # The cron job runs as www-data and needs to read the credentials
        try:
            shutil.chown(LP_CREDENTIALS_DIR, "www-data")
            shutil.chown(LP_CREDENTIALS_FILE, "www-data")
            logger.debug("Credentials directory and file ownership set to www-data")
        except (LookupError, PermissionError) as e:
            logger.error("Failed to set credentials ownership: %s", e)
            raise

        # Set the environment variable for launchpadlib to find the credentials
        self.env["LP_CREDENTIALS_FILE"] = str(LP_CREDENTIALS_FILE)
        logger.debug("LP_CREDENTIALS_FILE environment variable set")

    def install(self):
        """Install the versions build dependencies."""
        # Install Launchpad credentials if provided
        self.install_launchpad_credentials()

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
                timeout=MEDIUM_TIMEOUT,
            )
            logger.debug("ubuntu-desktop-versions vcs cloned.")
        except CalledProcessError as e:
            logger.debug("Git clone of the code failed: %s", e.stdout)
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

        # Install logrotate configuration to prevent logs from growing infinitely
        logrotate_config_src = Path(__file__).parent / "logrotate.conf"
        shutil.copy2(logrotate_config_src, LOGROTATE_CONFIG_DST)
        LOGROTATE_CONFIG_DST.chmod(0o644)
        logger.debug("Logrotate configuration installed: %s", LOGROTATE_CONFIG_DST)

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
                timeout=MEDIUM_TIMEOUT,
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
                timeout=SHORT_TIMEOUT,
            )
            workload_version = result.stdout.strip()
            logger.debug("ubuntu-desktop-versions revision: %s", workload_version)
            return workload_version

        except CalledProcessError as e:
            logger.debug("Git pull of the ubuntu-desktop-versions repository failed: %s", e.stdout)
            raise

    def setup_crontab(self):
        """Configure the crontab for the service."""
        crontab_file = Path(__file__).parent / "crontab"
        try:
            run(
                ["crontab", "-u", "www-data", str(crontab_file)],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                timeout=SHORT_TIMEOUT,
            )
            logger.debug("Crontab configured for www-data user.")
        except CalledProcessError as e:
            logger.error("Installation of the crontab failed: %s", e.stdout)
            raise

    def disable_crontab(self):
        """Remove the crontab for the service."""
        try:
            run(
                ["crontab", "-u", "www-data", "-r"],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                timeout=SHORT_TIMEOUT,
            )
            logger.debug("Crontab removed for www-data user.")
        except CalledProcessError as e:
            # crontab -r returns error if no crontab exists, that's okay
            logger.debug("Removal of crontab failed (may not exist): %s", e.stdout)

    def generate_reports(self):
        """Generate package version comparison reports.

        Returns:
            bool: True if report generation succeeded, False otherwise
        """
        logger.info("Starting report generation")

        report_env = self.env.copy()
        report_env["FLAVOR"] = "ubuntu"
        report_env["DISTRO_SERIES"] = "resolute"

        command = (
            f"cd {REPO_LOCATION} && "
            f"/usr/bin/python3 versions.py && "
            f"cp *.html *.yaml *.yml {OUTPUT_DIR}/"
        )

        try:
            result = run(
                ["bash", "-c", command],
                check=True,
                stdout=PIPE,
                stderr=STDOUT,
                text=True,
                env=report_env,
                timeout=LONG_TIMEOUT,
            )
            logger.info("Report generation completed successfully")
            logger.debug("Output: %s", result.stdout)

            return True

        except CalledProcessError as e:
            logger.error("Report generation failed: %s", e.stdout)

            return False
