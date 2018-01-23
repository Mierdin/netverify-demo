import argparse
import pprint
import sys

from lib.k8s import get_k8s_services

from jinja2 import Environment, FileSystemLoader
from napalm import get_network_driver


def main():
    """This script handles vSRX configuration, including initial configuration
    as well as added policies for kubernetes services
    """

    parser = argparse.ArgumentParser(description='Configure firewall')
    parser.add_argument('config_mode', metavar='config_mode', type=str,
                        help='which configuration to run')
    parser.add_argument('--port', dest='port',
                        help='NETCONF/SSH port for vSRX')

    args = parser.parse_args()

    junos_driver = get_network_driver("junos")
    junos_config = {
        "hostname": "127.0.0.1",
        "username": "root",
        "password": "Juniper",
        "optional_args": {"port": args.port},
    }

    with junos_driver(**junos_config) as junos:
        if args.config_mode == "initial":
            junos.load_merge_candidate(filename='vsrx_configs/initial_config.xml')
            junos.commit_config()
        elif args.config_mode == "policy":

            env = Environment(loader=FileSystemLoader('vsrx_configs/'))
            template = env.get_template('policies.xml')
            rendered = template.render(services=get_k8s_services())

            # Uploaded rendered configuration
            junos.load_merge_candidate(config=rendered)
            junos.commit_config()
        else:
            print("Invalid subcommand")

if __name__ == "__main__":
    main()
