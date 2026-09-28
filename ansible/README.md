# Ansible

The Ansible master is the control node. The servers it configures are the managed nodes.

Files:
- inventory.ini: example inventory with placeholder addresses
- setup-docker.yml: Docker and Git on the Docker server (Amazon Linux)
- setup-jenkins.yml: Java, Jenkins, Docker, kubectl and Trivy on the Jenkins server (Ubuntu)
- setup-k8s-prereqs.yml: swap, kernel settings, containerd, kubeadm, kubelet and kubectl (Ubuntu)

Check a playbook without changing anything:
ansible-playbook -i inventory.ini setup-jenkins.yml --check --diff

Run a playbook:
ansible-playbook -i inventory.ini setup-jenkins.yml

Not automated on purpose, because they run once per cluster:
- kubeadm init
- the Calico network add-on