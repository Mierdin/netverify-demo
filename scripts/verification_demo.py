import argparse
from jnpr.jsnapy import SnapAdmin
import json
import pprint
import sys
import time

from lib.k8s import get_k8s_services

from jinja2 import Environment, FileSystemLoader
from napalm import get_network_driver
import requests
import yaml

def main():
    """A simple script to retrieve application details from kubernetes and generate
    needed files for later automation
    """

    parser = argparse.ArgumentParser(description='Configure firewall')

    parser.add_argument('verification_step', metavar='verification_step', type=str,
                        help='Verification step to run ("config", "operational", or "traffic"')
    parser.add_argument('--vsrx-port', dest='vsrx_port',
                        help='NETCONF/SSH port for vSRX')

    # normally this would be a separate API call to our network provider
    # like opencontrail, but since this is minikube, this will suffice
    parser.add_argument('--minikube-ip', dest='minikube_ip',
                        help='IP address of minikube')
    args = parser.parse_args()

    services = get_k8s_services()

    if args.verification_step == "config":
        try:
            config_verification(services, args)
        except IndexError:
            print("Problem finding a part of the configuration we were checking for. This probably means the config is out of compliance.")
            raise
    elif args.verification_step == "operational":
        operational_verification(services, args)
    elif args.verification_step == "traffic":
        traffic_verification(services, args)
    else:
        print("Invalid subcommand")
    print('\033[92mALL ASSERTIONS PASSED')    


def old_config_verification(services, args):
    """Pull existing configuration as lxml Elements, and make assertions on contents via xpath

    This is a "cute" way of doing this. The easiest way to make configuration
    verification is to store or generate a "golden" configuration and simply
    compare to what's running on the router.

    However, if you're okay with slight deviations on a router configuration, and wish to perform
    "targeted" audits of a config pertinent to a specific application, this might be a bit clearer.
    It also puts Python more in the driver's seat, which some might appreciate.
    """

    junos_driver = get_network_driver("junos")
    JUNOS_CONFIG = {
        "hostname": "127.0.0.1",
        "username": "root",
        "password": "Juniper",
        "optional_args": {"port": args.vsrx_port},
    }

    def recursive_dict(element):
        return element.tag, \
                dict(map(recursive_dict, element)) or element.text

    with junos_driver(**JUNOS_CONFIG) as junos:

        # Assert that an application is configured for each k8s service
        print("Checking for application definitions...")
        for service in services:
            frontend_app = [recursive_dict(app) for app in junos.device.rpc.get_config().xpath(
                'applications/application[name="k8s%s"]' % service['name']
            )][0][1]
            assert int(frontend_app['destination-port']) == service['port']

        # Assert that policies exist and reference the correct application
        print("Checking for policy definition and proper references...")
        for service in services:
            frontend_policy = [recursive_dict(app) for app in junos.device.rpc.get_config().xpath(
                'security/policies/policy[from-zone-name="untrust"][to-zone-name="trust"]/policy'
                '[name="K8SPOLICY_ALLOW_%s"]' % service['name'].upper()
            )][0][1]
            assert "permit" in frontend_policy['then']
            assert frontend_policy['name'] == "K8SPOLICY_ALLOW_%s" % service['name'].upper()
            assert frontend_policy['match']['application'] == "k8s%s" % service['name']

        # Assert that our "outside" interface (facing the bastion VM) is in the "untrusted" zone
        print("Checking for appropriate application of the 'outside' zone...")
        zones = [recursive_dict(app) for app in junos.device.rpc.get_config().xpath(
            'security/zones/security-zone[name="untrust"]/interfaces/name')][0][1]
        assert zones=='ge-0/0/2.0'

def config_verification(services, args):
    """Perform config verification with JSNAPy
    """

    def get_test_text(name, port):

        return """
---
test_app_%s:
- rpc: get-config
- item:
    id: ./name
    xpath: 'applications/application[name="k8s%s"]'
    tests:
    - is-equal: destination-port, %s
      info: "Test Succeeded!!, destination-port is <{{post['destination-port']}}>"
      err: "Test Failed!!!, destination-port is <{{post['destination-port']}}>"
        """ % (name, name, port)

    jsnapy_config = {
        "hosts": [
            {
                "device": "127.0.0.1",
                "username": "root",
                "passwd": "Juniper",
                "port": args.vsrx_port
            }
        ],
        "tests": []
    }

    for service in services:

        # Create test file for this service
        test_filename = "scripts/jsnapytest_%s.yaml" % service["name"]
        with open(test_filename, 'w') as testfile:
            testfile.write(get_test_text(service["name"], service["port"]))

        # Add reference for this test file to config
        jsnapy_config["tests"].append(test_filename)

    # Write config file to disk
    with open('scripts/jsnapyconfig.yaml', 'w') as configfile:
        yaml.dump(jsnapy_config, configfile, default_flow_style=False)

    # Retrieve instant snapshot and run tests on result
    js = SnapAdmin()
    chk = js.snapcheck('scripts/jsnapyconfig.yaml')

    # Ensure all tests passed
    for check in chk:
        assert check.result == "Passed"

def operational_verification(services, args):
    """Run operational verifications on our vSRX device

    Note that get_firewall_policies(), once implemented for JUNOS, will
    improve things quite a bit for us here
    """

    junos_driver = get_network_driver("junos")
    JUNOS_CONFIG = {
        "hostname": "127.0.0.1",
        "username": "root",
        "password": "Juniper",
        "optional_args": {"port": args.vsrx_port},
    }

    getfacts_check = {
        "get_facts": {
            "os_version": "",
            "interface_list": {
                "list": [
                    "ge-0/0/0",
                    "ge-0/0/1",
                    "ge-0/0/2"
                ]
            }
        }
    }

    def get_ping_statement(service_name, target):
        """Returns a napalm-verify compatible dict for a single verification statement using ping
        """

        return {
            "ping": {
                "_name": "pingtest_%s" % service_name,
                "_kwargs": {
                    "destination": target
                },
                "success": {
                    "packet_loss": 0
                },
                "_mode": "strict"
            }
        }

    # Create list of verification statements to pass to compliance_report()
    verify_doc = [
            get_ping_statement("k8s", args.minikube_ip),            # k8s
            get_ping_statement("bastionmachine", "192.168.100.10"),  # bastion
            getfacts_check
    ]
    print(yaml.dump(verify_doc))

    # Generate compliance report
    with junos_driver(**JUNOS_CONFIG) as junos:
        report = junos.compliance_report(validation_source=verify_doc)
        pprint.pprint(report)

        # This high-level assertion ensures all substatements comply
        assert report['complies'] is True


def traffic_verification(services, args):

    testruns = [
        {
            "type": "testrun",
            "label": "test-%s" % service["name"],
            "spec": {
                "targettype": "uncontrolled",
                "source": {
                    "name": "bastion_agents",
                    "app": "http",
                    "args": ""
                },
                "target": [
                    "%s:%s" % (args.minikube_ip, service['port'])
                ]
            }
        } for service in services
    ]

    groups = [
        {
            "type": "group",
            "label": "bastion_agents",
            "spec": {
                "group": "bastion_agents",
                "matches": [
                    {
                        "hostname": "todd-agent-.*"
                    }
                ]
            }
        }
    ]

    url = "http://192.168.100.10:8080/v1"

    # Upload group definitions
    for group in groups:
        group_post = requests.post('%s/object/create' % url, data=json.dumps(group))
        if group_post.status_code != 200:
            raise Exception("Problem uploading group %s" % group['label'])
        else:
            print("Uploaded group %s" % group['label'])

    # Upload testrun definitions
    for testrun in testruns:
        group_post = requests.post('%s/object/create' % url, data=json.dumps(testrun))
        if group_post.status_code != 200:
            raise Exception("Problem uploading testrun %s" % testrun['label'])
        else:
            print("Uploaded testrun %s" % testrun['label'])

    # Block until all six agents are placed in the group
    while True:
        print("Waiting to see six agents in the source group...")
        active_groups = requests.get('%s/groups' % url).json()
        if len(active_groups) >= 6:
            break
        time.sleep(5)

    for testrun in testruns:
        testrun_run_post = requests.post('%s/testrun/run' % url, data=json.dumps({"testRunName": testrun['label']}))
        
        if testrun_run_post.status_code != 200:
            raise Exception("Problem running testrun %s" % testrun['label'])

        tr_id = testrun_run_post.text

        # Block until all six agents are placed in the group
        while True:
            print("Waiting for testrun data for %s..." % tr_id)
            testdata = requests.get('%s/testdata?testUuid=%s' % (url, tr_id))
            if testdata.status_code != 404:
                break
            time.sleep(10)

        # Assert that all targets are reachable with a 200 status
        todd_report = testdata.json()
        pprint.pprint(todd_report)
        for agent, targets in todd_report.items():
            assert targets
            for target, metric in targets.items():
                assert metric['http_code'] == '200'
        print("Target service reachable from all agents")

if __name__ == "__main__":
    main()
