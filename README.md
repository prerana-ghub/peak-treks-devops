# PEAK — A Trek Booking App

A Flask-based trek booking web application with a containerized CI/CD pipeline deployed on AWS EC2 using Ansible, Jenkins, Docker, Docker Hub and Kubernetes (k8s).

## Tech Stack

### Application

| Technology       | Purpose                      |
| ---------------- | ---------------------------- |
| Python           | Application programming      |
| Flask            | Backend / web framework      |
| HTML + CSS       | User interface               |
| Jinja2           | Server-side templates        |
| SQLAlchemy       | Database interaction         |
| Gunicorn         | Application server           |
| requirements.txt | Python dependency management |

### Cloud & DevOps

| Technology         | Purpose                         |
| ------------------ | ------------------------------- |
| AWS EC2            | Cloud infrastructure            |
| Git                | Version control                 |
| GitHub             | Source-code repository          |
| GitHub Webhook     | Automatically triggers Jenkins  |
| Ansible            | Server configuration automation |
| Docker             | Application containerization    |
| Docker Hub         | Docker image registry           |
| Jenkins            | CI/CD automation                |
| Kubernetes / k8s   | Container orchestration         |
| Kubernetes Service | Exposes the application         |
| Metrics Server     | Provides resource metrics       |
| HPA                | Horizontal Pod Autoscaling      |

## Architecture

```text
Developer
   ↓
GitHub
   ↓
GitHub Webhook
   ↓
Jenkins
   ↓
Docker Build
   ↓
Docker Hub
   ↓
Kubernetes / k8s
   ↓
PEAK Pods
   ↓
Kubernetes Service
   ↓
PEAK Application
```

The DevOps environment runs on **AWS EC2** with separate servers for Jenkins, Docker, Kubernetes and Ansible.

**Ansible** is used to automate server configuration and setup.

## CI/CD Pipeline

A push to the `main` branch triggers the GitHub Webhook, which automatically starts the Jenkins pipeline.

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
   ↓
PEAK Pods
```

## Jenkins

Jenkins is used as the **CI/CD automation server** for the project.

The pipeline is defined in [`Jenkinsfile`](Jenkinsfile) and contains the following stages:

1. **Checkout** — Jenkins retrieves the latest source code from GitHub.
2. **Test** — Runs the application's test command.
3. **Docker Build** — Builds the PEAK Docker image.
4. **Docker Hub Push** — Pushes the image to Docker Hub.
5. **Kubernetes Deployment** — Updates the PEAK deployment in the Kubernetes cluster.

Jenkins uses credentials for **Docker Hub** and **Kubernetes kubeconfig** to securely access the required services.

A **GitHub Webhook** automatically triggers the pipeline whenever new changes are pushed to the repository.

## Docker

The application is containerized using [`Dockerfile`](Dockerfile).

Docker image:

```text
preranassheshadri/peak:latest
```

The Docker image packages the Flask application and its required dependencies so that it can run consistently across environments.

## Kubernetes

PEAK runs on a self-managed **Kubernetes (k8s) cluster on AWS EC2**.

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

Ansible is used to automate configuration of the AWS EC2 environment.

It was used for:

* Control Node setup
* Inventory configuration
* SSH connectivity
* Remote command execution
* Docker installation
* Docker service configuration
* Git installation on the Docker server

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
