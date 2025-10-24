# Copyright 2025 Canonical
# See LICENSE file for licensing details.

import jubilant
from requests import Session

from .helpers import DNSResolverHTTPSAdapter

UBUNTU_DESKTOP_VERSIONS = "ubuntu-desktop-versions"
HAPROXY = "haproxy"
SSC = "self-signed-certificates"


def test_deploy(juju: jubilant.Juju, ubuntu_desktop_versions_charm):
    juju.deploy(ubuntu_desktop_versions_charm, app=UBUNTU_DESKTOP_VERSIONS)
    juju.deploy(HAPROXY, channel="2.8/edge", config={"external-hostname": "ubuntu-desktop-versions.internal"})
    juju.deploy(SSC, channel="1/edge")

    juju.integrate(UBUNTU_DESKTOP_VERSIONS, HAPROXY)
    juju.integrate(f"{HAPROXY}:certificates", f"{SSC}:certificates")

    juju.wait(jubilant.all_active, timeout=1800)


def test_ingress_functions_correctly(juju: jubilant.Juju):
    model_name = juju.model
    assert model_name is not None

    haproxy_ip = juju.status().apps[HAPROXY].units[f"{HAPROXY}/0"].public_address
    external_hostname = "ubuntu-desktop-versions.internal"

    session = Session()
    session.mount("https://", DNSResolverHTTPSAdapter(external_hostname, haproxy_ip))
    response = session.get(
        f"https://{haproxy_ip}/{model_name}-{UBUNTU_DESKTOP_VERSIONS}/",
        headers={"Host": external_hostname},
        verify=False,
        timeout=30,
    )

    assert response.status_code == 200
