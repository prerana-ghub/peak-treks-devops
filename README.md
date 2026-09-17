# PEAK — Trek Booking App

A Flask-based trek booking web application with a containerized CI/CD pipeline deployed on AWS EC2 using Ansible, Jenkins, Docker, Docker Hub and Kubernetes (k3s).

## Tech Stack

### Application

| Technology | Purpose |
|---|---|
| Python | Application programming |
| Flask | Backend / web framework |
| HTML + CSS | User interface |
| Jinja2 | Server-side templates |
| SQLAlchemy | Database interaction |
| Gunicorn | Application server |
| requirements.txt | Python dependency management |

### Cloud & DevOps

| Technology | Purpose |
|---|---|
| AWS EC2 | Hosts the Cloud/DevOps environment |
| Git | Version control |
| GitHub | Source-code repository |
| GitHub Webhook | Triggers Jenkins automatically |
| Ansible | Server configuration automation |
| Docker | Application containerization |
| Docker Hub | Docker image registry |
| Kubernetes / k3s | Container orchestration |
| Kubernetes Service | Exposes the application |
| Metrics Server | Provides resource metrics |
| HPA | Horizontal pod autoscaling |
| Jenkins | CI/CD automation |

## Architecture

```text
Developer
   │
   ▼
 GitHub ── Webhook ──► Jenkins
                         │
                    Docker Build
                         │
                         ▼
                    Docker Hub
                         │
                         ▼
                 Kubernetes / k3s
                         │
                    PEAK Pods
                         │
                         ▼
                        HPA
````

The DevOps environment runs on **AWS EC2** with separate servers for Jenkins, Docker, Kubernetes and Ansible.

## CI/CD Pipeline

A push to `main` triggers the GitHub webhook and starts Jenkins automatically.

```text
GitHub
  ↓
Checkout
  ↓
Test
  ↓
Docker Build
  ↓
Docker Hub Push
  ↓
Kubernetes Deployment
  ↓
Rolling Update
```

The pipeline is defined in [`Jenkinsfile`](Jenkinsfile).

## Docker

The application is containerized using [`Dockerfile`](Dockerfile).

Docker image:

```text
preranassheshadri/peak:latest
```

## Kubernetes

PEAK runs on a self-managed **k8s cluster on AWS EC2**.

Configured components:

* Deployment
* Service
* Rolling updates
* Metrics Server
* Horizontal Pod Autoscaler (HPA)

### HPA Configuration

```text
Min replicas: 1
Max replicas: 3
CPU target: 60%
```

Autoscaling was tested from **1 → 2 → 3 pods** and back down.

## Ansible

Ansible automates configuration of the **AWS EC2 environment**.

It was used for:

* Ansible Master and Slave setup
* Inventory configuration
* SSH connectivity
* Remote execution
* Docker installation
* Docker service configuration
* Git installation on the Docker server

```text
Ansible Master
      │
      ├──→ Ansible Slave
      ├──→ Docker Server
      └──→ Other EC2 Servers
```

## Run Locally

### Clone the Repository

```bash
git clone https://github.com/prerana-ghub/peak-treks-devops.git
cd peak-treks-devops
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Application

```bash
python app1.py
```

Open:

```text
http://127.0.0.1:5000
```

For local configuration, create a `.env` file as required.
