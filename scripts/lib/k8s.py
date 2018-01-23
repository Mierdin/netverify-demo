from kubernetes import client, config

def get_k8s_services():

    # Retrieve client port from kubernetes
    config.load_kube_config()
    v1 = client.CoreV1Api()
    services = v1.list_service_for_all_namespaces(watch=False)

    # We want to return all services with a nodePort in a simple list of dict form
    return [
        {
            "name": i.metadata.name,
            "port": i.spec.ports[0].node_port
        } 
        for i in services.items if i.spec.ports[0].node_port
    ]
