# -*- mode: ruby -*-
# vi: set ft=ruby :

# ge-0/0/0.0 defaults to NAT for SSH + management connectivity
# over Vagrant's forwarded ports.  This should configure ge-0/0/1.0
# through ge-0/0/7.0 on VirtualBox.

######### WARNING: testing only! #########
#
# this Vagrantfile can and will wreak havoc on your VBox setup, so please
# use the Vagrant boxes at https://atlas.hashicorp.com/juniper unless you're
# attempting to extend this plugin (and can lose your VBox network config)
# TODO: launch VMs from something other than travis to CI all features
#
# Note: VMware can't name interfaces, but also supports 10 interfaces
# (through ge-0/0/9.0), so you should adjust accordingly to test
#
# Note: interface descriptions in Junos don't work yet, but you woud set them
# here with 'description:'.


Vagrant.configure(2) do |config|

  config.vm.define "vsrx01" do |vsrx01|
    vsrx01.vm.box = "juniper/ffp-12.1X47-D15.4-packetmode"
    # config.vm.box_version = "0.2.0"

    vsrx01.vm.host_name = "vsrx01"

    # This is fragile. Need to figure out a way to statically set minikubes network and IP preferably,
    # so you can statically set them here.
    vsrx01.vm.network :private_network, ip: "192.168.99.150",
                   virtualbox_intnet: "vboxnet7"
    vsrx01.vm.network :private_network, ip: "192.168.100.150",
                   virtualbox_intnet: "vboxnet8"
  end

  config.vm.define "bastion" do |bastion|
    bastion.vm.provider "virtualbox" do |v|
      v.memory = 2048
      v.cpus = 2
    end
    bastion.vm.box = "ubuntu/trusty64"
    # bastion.vm.box_url = "http://cloud-images.ubuntu.com/vagrant/trusty/current/trusty-server-cloudimg-amd64-vagrant-disk1.box"
    bastion.vm.host_name = "bastion"
    bastion.vm.network :private_network, ip: "192.168.100.10",
                   virtualbox_intnet: "vboxnet8"
    bastion.vm.provision "ansible" do |ansible|
        ansible.playbook = "bastion_setup.yml"
    end

    # Make sure our bastion machine knows how to get to kubernetes
    config.vm.provision "shell", run: "always",
      inline: "ip route replace 192.168.99.0/24 via 192.168.100.150 dev eth1"

  end

end


