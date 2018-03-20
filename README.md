# Network Verification

These days, being able to verify the changes you've made to a network are crucial, especially if those changes were automated. This forms a nice feedback loop you can iterate on over time.

This repo houses slides and demo material for exploring this, all based on application metadata already defined in Kubernetes.

> An early version of this session at NFD17 was recorded, and is available [here](https://vimeo.com/252900298)

We will verify that the network is configured appropriately using three methods:

1. Configuration data using JSNAPy
2. Operational data and basic reachability using NAPALM
3. Application connectivity using ToDD

## Demo Dependencies

- Ansible
- Vagrant
- Virtualbox

## Demo Setup

> All commands are run from this repo's directory. Before starting setup, make sure you clone this repository and navigate to the resulting directory.

First, clone this repository and navigate to the resulting directory. Unless otherwise stated, commands below are run from within this directory.

```
git clone https://github.com/Mierdin/netverify-demo
cd netverify-demo
```

Next, set up [minikube](https://github.com/kubernetes/minikube). I use VirtualBox on MacOS, but there are multiple options for running minikube on the project's README.

Once finished, start your cluster. This may take some time if you're running for the first time, as it must download binaries and ISOs.

```
minikube start
```

Once finished, `kubectl` should be configured automatically. Confirm this is true, and the cluster is healthy:

```
kubectl get cs
kubectl get nodes
kubectl version
```

Upload manifests:

```
kubectl create -R -f ./guestbook/
```

Verify the guestbook pods are running. Should see three pods for the frontend service, and three others for redis. Eventually all should go to a `Running` status. This may also take a little time, as Kubernetes needs to download the container images.

```
kubectl get pods
```

Ensure the `frontend` application is running properly by running this to open the application in your browser:

```
minikube service frontend
```

Finally, SSH into minikube and configure network settings so that it will be able to reach the VM we'll set up in a few steps:

```
minikube ssh
sudo ip route add 192.168.100.0/24 via 192.168.99.150 dev eth1
exit
```

> If you restart the minikube VM, these settings will not persist between VM reboots. So if you are going to restart minikube, you may want to consider writing these persistently via `/etc/network/interfaces`. In addition, you should ensure that the minikube VM is connected on its second network adapter to the `vboxnet7` network.

Next, start the Vagrant environment. This will instantiate two virtual machines - one will run Ubuntu Trusty, and is where we'll run all of our code.
Note that this may take some time while any plugins or boxes are downloaded, and while provisioning steps take place. Be patient. :smile:

```
vagrant plugin install vagrant-junos
vagrant plugin install vagrant-host-shell
vagrant up
```

Once our VMs are spun up and provisioned run the following commands to SSH into the bastion VM and finish spinning up ToDD for our traffic tests:

```
vagrant ssh bastion
cd /home/vagrant/go/src/github.com/toddproject/todd/
make && sudo -E make install
scripts/start-containers.sh demo > /dev/null
exit
```

Next, we'll want to set up our virtualenv so we can run our Python scripts:

> Note that I'm explicitly using `/usr/local/bin/python` as the location for my Python interpreter. You may want to omit or change this based on the way you have your system configured.

```
virtualenv venv -p /usr/local/bin/python && source venv/bin/activate && pip install -r requirements.txt > /dev/null
```

Because of a current bug with the pip-installable version of `jsnapy`, we need to install this manually from the repo:

```
git clone https://github.com/Juniper/jsnapy
cd jsnapy && python setup.py install > /dev/null && cd ..
```

Next, let's initially configure our vSRX device so that it by default, blocks all traffic from the bastion machine to the Kubernetes cluster. To do this, we'll run a python script that uses NAPALM to load(merge) a configuration snippet. We'll then restart our vSRX so that the new forwarding options can take place.

```
python scripts/config_firewall.py initial --port=$(vagrant ssh-config vsrx01 | grep Port | awk '{print $2}')
vagrant reload vsrx01
```

# Initial Verification (Expected Failure)

The configuration we just applied to the vSRX doesn't include any policies for our kubernetes service. We can use our `verification_demo.py` script to run through our verifications, and they should all fail because of this.

First, let's do some basic config linting. This should fail because our vSRX doesn't have the expected configurations:

```
python scripts/verification_demo.py --vsrx-port=$(vagrant ssh-config vsrx01 | grep Port | awk '{print $2}') --minikube-ip=$(minikube ip) config
```

> Normally, we could(should) retrieve the service IP address via an API call to our virtual network controller like Contrail, or our cloud provider. However, since we're running minikube, this will suffice for the time being.

Next, our operational verification should also show a failure:

```
python scripts/verification_demo.py --vsrx-port=$(vagrant ssh-config vsrx01 | grep Port | awk '{print $2}') --minikube-ip=$(minikube ip) operational
```

Third, if we use ToDD to make HTTP requests to our kubernetes cluster, this will also fail:

```
python scripts/verification_demo.py --vsrx-port=$(vagrant ssh-config vsrx01 | grep Port | awk '{print $2}') --minikube-ip=$(minikube ip) traffic
```

# Remediation and Successful Verification

We can use the `policy` subcommand for our `config_firewall.py` script to place the right policies on our vSRX:

```
python scripts/config_firewall.py policy --port=$(vagrant ssh-config vsrx01 | grep Port | awk '{print $2}')
```

> Use `vagrant ssh vsrx01` to inspect the vSRX for the new policies that are installed and applied to the appropriate zones

We can now re-run our verification script through all three stages, and they should now pass.

```
python scripts/verification_demo.py --vsrx-port=$(vagrant ssh-config vsrx01 | grep Port | awk '{print $2}') --minikube-ip=$(minikube ip) config
python scripts/verification_demo.py --vsrx-port=$(vagrant ssh-config vsrx01 | grep Port | awk '{print $2}') --minikube-ip=$(minikube ip) operational
python scripts/verification_demo.py --vsrx-port=$(vagrant ssh-config vsrx01 | grep Port | awk '{print $2}') --minikube-ip=$(minikube ip) traffic
```

# Deleting Demo

Resetting to the beginning is possible with just a few commands. Mostly just deleting our Vagrant VMs, Minikube instance, and Python virtualenv.

```
vagrant destroy -f
minikube delete
deactivate && rm -rf venv/
rm -rf jsnapy/
rm -f scripts/jsnapy*
```
