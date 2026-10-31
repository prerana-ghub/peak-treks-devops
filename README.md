# 🏔️ PEAK - Trek Booking Platform

PEAK is a **trek booking application** built with Flask and deployed on AWS using a containerized DevOps workflow.

**One push to GitHub automatically tests, security scans, builds and deploys the app to Kubernetes, with autoscaling.**

---

## 🏗️ Architecture

![PEAK Architecture](architecture.png)

- **Source Control** → GitHub hosts the codebase
- **CI/CD** → Jenkins automates building, testing, security scanning and deployment
- **Containerization** → Docker packages the app, stored in Docker Hub
- **Orchestration** → Kubernetes (kubeadm) manages deployment and scaling
- **Infrastructure** → AWS EC2 instances host the whole setup: the Ansible control node, the Docker server, the Jenkins server and the Kubernetes (kubeadm) node(s)
- **Configuration Management** → Ansible configures servers, run from an EC2 control node
- **Security** → Trivy scans the built image (failing on fixable CRITICAL findings) before it is pushed and deployed
- **Autoscaling** → Kubernetes HPA adjusts replicas based on load
- **Users** → Access the live application via browser

---

## 🔑 Key Features

- Trek catalog with details (difficulty, duration, pricing, dates, images)
- Secure user registration & login
- Shopping cart with participant count, GST and total calculation
- Checkout flow with demo payments (test card or UPI QR code)
- Booking dashboard to view past/current bookings
- Automated email notifications for bookings & enquiries
- Health check endpoint (`/healthz`) used by Kubernetes probes

Treks included: **Kudremukh, Kumara Parvatha, Savandurga, Skandagiri, Kodachadri and Nandi Hills**

---

## ⚙️ Tech Stack

- **Frontend**: HTML, CSS, Jinja2
- **Backend**: Python (Flask), served with Gunicorn in containers
- **Database**: PostgreSQL + SQLAlchemy (SQLite for local development)
- **Testing**: Pytest
- **Version Control**: Git, GitHub
- **Containerization**: Docker, Docker Hub
- **CI/CD**: Jenkins
- **Orchestration**: Kubernetes (kubeadm, containerd)
- **Config Management**: Ansible
- **Security**: Trivy

---

## 🚀 DevOps Pipeline

```text
GitHub (webhook) → Jenkins → Docker Build → Tests → Trivy Scan → Docker Hub → Kubernetes (kubeadm) → Application
```

**Pipeline stages:**

1. **Checkout** → pulls the code from GitHub
2. **Build Docker Image** → tags the image with the build number and `latest`
3. **Test** → runs `pytest` inside the built image (in-memory SQLite)
4. **Security Scan** → Trivy fails the build on fixable CRITICAL vulnerabilities
5. **Push to Docker Hub** → pushes both tags
6. **Deploy to Kubernetes** → updates the `peak` deployment and waits up to 180s for the rollout

---

## 🛠️ Local Development

Needs **Python 3.12** and **Git**. Local development uses **SQLite** by default, so PostgreSQL is not required.

1. **Clone the repository**

   ```bash
   git clone https://github.com/prerana-ghub/peak-treks-devops.git
   cd peak-treks-devops
   ```

2. **Create and activate a virtual environment**

   **Linux/macOS:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   **Windows (PowerShell):**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   Copy `.env.example` to `.env`:

   **Windows (PowerShell):**
   ```powershell
   Copy-Item .env.example .env
   ```

   **Linux/macOS:**
   ```bash
   cp .env.example .env
   ```

   Open `.env` and configure the variables:

   | Variable | Configuration |
   |---|---|
   | `SECRET_KEY` | Replace the placeholder with a randomly generated secret key. |
   | `DATABASE_URL` | Keep `sqlite:///peak.db` for local development. |
   | `MAIL_SERVER` | Keep `localhost` for local email testing, or use `smtp.gmail.com` for Gmail. |
   | `MAIL_PORT` | Keep `1025` for local email testing, or use `587` for Gmail. |
   | `MAIL_SENDER` | Keep the sample value for local testing or enter your sender address. |
   | `MAIL_USERNAME` | Leave blank for local testing; enter your Gmail address when using Gmail. |
   | `MAIL_PASSWORD` | Leave blank for local testing; enter your Gmail App Password when using Gmail. |
   | `MAIL_USE_TLS` | Enabled by default. Set to `0` only when using the local debug SMTP server. |

   Generate a Flask secret key:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Replace the placeholder in `.env` with the generated value.

   **Email configuration is optional.** For local email testing, run a debug SMTP server in a separate terminal:
   ```bash
   pip install aiosmtpd
   python -m aiosmtpd -n -l localhost:1025
   ```
   Add `MAIL_USE_TLS=0` to `.env` when using this local debug server.

   To use Gmail instead, enable 2-Step Verification, generate a Google App Password, set `MAIL_SERVER` to `smtp.gmail.com` and `MAIL_PORT` to `587`, then enter your Gmail address and App Password in `MAIL_USERNAME` and `MAIL_PASSWORD`. STARTTLS is enabled by default.

5. **Run the application**

   ```bash
   python app.py
   ```
   The app prepares the database and starts at `http://localhost:5000`.

   > **macOS:** if port 5000 is busy, turn off AirPlay Receiver or run the app on another port.

6. **Run tests**

   ```bash
   pytest
   ```
   The test suite covers public pages, the `/healthz` endpoint, billing calculations, authentication, and static assets. Jenkins runs the same tests inside the built image.

---

## 📸 Screenshots

Screenshots are in the `screenshots/` folder.

<!-- Add 2 or 3 images here, using your real file names, for example:
![Jenkins pipeline](screenshots/jenkins-pipeline.png)
![Kubernetes pods and HPA](screenshots/kubectl-pods.png)
![PEAK homepage](screenshots/home.png)
-->

---

## 📚 Detailed Guides

Click a section to expand it.

<details>
<summary><b>📂 Project Structure</b></summary>

```text
peak-treks-devops/
├── app.py
├── booking_billing.py
├── booking_emails.py
├── database.py
├── models.py
├── trek_dates.py
├── requirements.txt
├── Dockerfile
├── Jenkinsfile
├── payments.py
├── pytest.ini
├── .env.example
├── .dockerignore
├── .gitignore
├── architecture.png
├── README.md
├── data/
├── helpers/
├── routes/
├── templates/
├── static/
├── tests/
├── ansible/
├── k8s/
└── screenshots/
```

The `data/`, `helpers/`, `routes/`, `templates/`, `static/`, `ansible/` and `k8s/` folders each have their own `README.md` explaining what is inside.

</details>

<details>
<summary><b>🌐 Application Routes</b></summary>

| Route | Methods | Purpose |
|---|---|---|
| `/` | GET | Home page |
| `/treks` | GET | Trek catalog |
| `/trek/<slug>` | GET | Trek details |
| `/about` | GET | About page |
| `/contact` | GET, POST | Contact and enquiry form |
| `/notifications/open/<notif_id>` | GET | Open a notification |
| `/signup` | GET, POST | User registration |
| `/signin` | GET, POST | User login |
| `/logout` | GET | Log out |
| `/cart` | GET | View cart |
| `/cart/add` | POST | Add a trek to the cart |
| `/cart/update/<item_id>` | POST | Update a cart item |
| `/cart/remove/<item_id>` | POST | Remove a cart item |
| `/checkout` | GET, POST | Checkout with demo payment |
| `/order/<order_id>/confirmation` | GET | Booking confirmation |
| `/bookings` | GET | My bookings dashboard |
| `/healthz` | GET | Health check used by Kubernetes probes |

</details>

<details>
<summary><b>📋 DevOps Prerequisites and EC2 Ports</b></summary>

- **Docker**, to build and run the container image
- **A Kubernetes cluster and `kubectl`**, for the Kubernetes deployment
- **Ansible**, installed on an EC2 control node (Linux) with SSH access to the other servers, for server provisioning (Ansible does not run natively on Windows)
- **AWS EC2 instances** for the Ansible control node and the servers defined in the Ansible inventory (`docker-server`, `jenkins-server` and `k8s-server`)
- **A Docker Hub account**, for the CI/CD pipeline

**EC2 security group ports** (adjust to your own setup):

| Port | Used for |
|---|---|
| 22 | SSH access (Ansible control node to the other servers, and administration) |
| 8080 | Jenkins web UI and the GitHub webhook |
| 30080 | PEAK application (NodePort) |
| 6443 | Kubernetes API, reachable from the Jenkins server so `kubectl` can deploy |

</details>

<details>
<summary><b>🐳 Docker Setup</b></summary>

1. **Build the image**

   ```bash
   docker build -t peak .
   ```

2. **Run the container**

   The container needs a secret key and a database URL. The example below uses a PostgreSQL database, which must be running and reachable from the container. Gunicorn does not run `prepare_database()` (the app only calls it when started with `python app.py`), so initialize the tables once first. This is the same command the Kubernetes `db-init` job runs:

   ```bash
   docker run --rm \
     -e SECRET_KEY=your-secret-key \
     -e DATABASE_URL=postgresql://user:password@host:5432/peak \
     peak python -c "from app import app, prepare_database; app.app_context().push(); prepare_database()"
   docker run -p 5000:5000 \
     -e SECRET_KEY=your-secret-key \
     -e DATABASE_URL=postgresql://user:password@host:5432/peak \
     peak
   ```

   For a quick test without PostgreSQL, you can use SQLite inside the container instead (data is lost when the container is removed):

   ```bash
   docker run -p 5000:5000 \
     -e SECRET_KEY=your-secret-key \
     -e DATABASE_URL=sqlite:///peak.db \
     peak sh -c "python -c 'from app import app, prepare_database; app.app_context().push(); prepare_database()' && gunicorn --bind 0.0.0.0:5000 app:app"
   ```

   The container runs the app with Gunicorn, bound to `0.0.0.0:5000`, as a non-root user.

3. **Push to Docker Hub** (after `docker login`)

   ```bash
   docker tag peak <your-dockerhub-username>/peak:v1
   docker push <your-dockerhub-username>/peak:v1
   ```

</details>

<details>
<summary><b>☸️ Kubernetes Deployment</b></summary>

These steps assume a running kubeadm-based Kubernetes cluster with `kubectl` configured. The Jenkins pipeline publishes to `preranasseshadri/peak`. If you forked this project, change `IMAGE` in the `Jenkinsfile` and the image in `k8s/deployment.yml` and `k8s/db-init-job.yml` to your own Docker Hub image.

The manifests are applied manually once. After that, Jenkins only updates the image with `kubectl set image deployment/peak peak=<image>:<tag>`, so the Deployment and its container must both be named `peak`.

**Cluster notes (kubeadm):**

- `setup-k8s-prereqs.yml` only prepares the node (swap, kernel settings, containerd, kubeadm packages). Initializing the cluster with `kubeadm init` and installing a pod network (CNI) plugin are separate steps; on a single-node cluster, also remove the control-plane taint so application pods can be scheduled.
- kubeadm does not install a default StorageClass, so `postgres-pvc` needs a storage provisioner or a matching PersistentVolume to bind.
- kubeadm does not install metrics-server, which the HPA needs.

**Manifests included:**

- `deployment.yml` → Deploys the PEAK application (image pulled with `imagePullPolicy: Always`, configuration from the `peak-secrets` Secret, `/healthz` readiness and liveness probes, CPU request/limit 100m/500m, memory request/limit 128Mi/512Mi)
- `service.yml` → Exposes the PEAK application as a NodePort service on port 30080
- `postgres.yml` → Deploys PostgreSQL 16 with a PersistentVolumeClaim (`postgres-pvc`), so data survives pod restarts
- `db-init-job.yml` → Runs `prepare_database()` from the application image to initialize the database (retries up to 6 times)
- `hpa.yml` → Scales the PEAK deployment between 1 and 3 replicas at 60% average CPU utilization
- `jenkins-rbac.yml` → Grants Jenkins the permissions required to deploy to Kubernetes

**Steps:**

1. **Create the application secret**

   The application needs its configuration at runtime. Create a Kubernetes Secret instead of hardcoding values in the manifests:

   ```bash
   kubectl create secret generic peak-secrets \
     --from-literal=SECRET_KEY=<your-secret-key> \
     --from-literal=DATABASE_URL=postgresql://peak:<password>@postgres:5432/peak \
     --from-literal=POSTGRES_PASSWORD=<password> \
     --from-literal=MAIL_USERNAME=<your-gmail-address> \
     --from-literal=MAIL_PASSWORD=<your-gmail-app-password>
   ```

   - `k8s/postgres.yml` creates the database user `peak` and database `peak`, and reads `POSTGRES_PASSWORD` from this Secret. The password in `DATABASE_URL` must be the same.
   - Every key in this Secret is loaded into the app as an environment variable.
   - Emails are only delivered if real Gmail credentials are provided. When `MAIL_USERNAME` is set, the app defaults to `smtp.gmail.com:587` with TLS; without it, it falls back to `localhost:1025`, where no mail server runs in the cluster.

2. **Deploy PostgreSQL and wait until it is ready**

   ```bash
   kubectl apply -f k8s/postgres.yml
   kubectl wait --for=condition=ready pod -l app=postgres --timeout=120s
   ```

3. **Initialize the database**

   ```bash
   kubectl apply -f k8s/db-init-job.yml
   kubectl wait --for=condition=complete job/peak-db-init --timeout=120s
   ```

   The job retries up to 6 times if Postgres is not ready yet.

   Jenkins deployments only update the image and do not re-run this job. If a release changes the database models, delete and re-apply it:

   ```bash
   kubectl delete job peak-db-init
   kubectl apply -f k8s/db-init-job.yml
   ```

4. **Deploy the application, service and autoscaler**

   ```bash
   kubectl apply -f k8s/deployment.yml
   kubectl apply -f k8s/service.yml
   kubectl apply -f k8s/hpa.yml
   ```

   The HPA scales the `peak` deployment between 1 and 3 replicas at 60% average CPU, and needs metrics-server installed (see the cluster notes above). The deployment uses `/healthz` for its readiness and liveness probes.

5. **(CI/CD only) Grant Jenkins deploy permissions**

   Needed only if Jenkins deploys to this cluster:

   ```bash
   kubectl apply -f k8s/jenkins-rbac.yml
   ```

6. **Check pods and access the service**

   ```bash
   kubectl get pods
   kubectl get svc
   ```

   `peak-service` is a NodePort service, so open the application at `http://<node-public-ip>:30080`. On AWS EC2, make sure the security group allows inbound TCP traffic on port 30080.

</details>

<details>
<summary><b>⚙️ Server Provisioning with Ansible</b></summary>

Run these from the Ansible control node (an EC2 instance) with SSH access to the other servers. The inventory defines `docker-server`, `jenkins-server` and `k8s-server`; the Jenkins and Kubernetes servers are Ubuntu hosts (`ansible_user=ubuntu`), while the Docker playbook uses `dnf` and `ec2-user`. Edit `ansible/inventory.ini` with your own hosts, then run the playbooks as needed:

```bash
ansible-playbook -i ansible/inventory.ini ansible/setup-docker.yml
ansible-playbook -i ansible/inventory.ini ansible/setup-jenkins.yml
ansible-playbook -i ansible/inventory.ini ansible/setup-k8s-prereqs.yml
```

**Playbooks included:**

- `setup-docker.yml` → Installs Docker and Git (dnf-based host, `ec2-user`), starts and enables Docker, and lets `ec2-user` run Docker without sudo
- `setup-jenkins.yml` → Configures the Jenkins server (Ubuntu): installs Java 21, Jenkins, Docker, kubectl and Trivy, and lets the `jenkins` user run Docker
- `setup-k8s-prereqs.yml` → Prepares an Ubuntu node for kubeadm: turns swap off, loads kernel modules and network settings, installs containerd (systemd cgroup driver), kubelet, kubeadm and kubectl (v1.34 repository, versions held)
- `inventory.ini` → Lists target hosts for the playbooks (`docker-server`, `jenkins-server`, `k8s-server`)

</details>

<details>
<summary><b>🔁 Jenkins Setup</b></summary>

After provisioning the Jenkins server:

1. Add these credentials in Jenkins (**Manage Jenkins → Credentials**), using these exact IDs:

   - `dockerhub-creds` → **Username with password** (Docker Hub username and password/access token)
   - `kubeconfig` → **Secret file** (kubeconfig for the Kubernetes cluster, using the `jenkins-deployer` service account token created by `k8s/jenkins-rbac.yml`; make sure the server address in it is reachable from the Jenkins server)

2. `setup-jenkins.yml` installs Java 21, Jenkins, Docker, kubectl and Trivy, and adds the `jenkins` user to the `docker` group. If you set Jenkins up another way, make sure all of these are available.

3. Create a **Pipeline** job from SCM pointing to this repository so it uses the `Jenkinsfile` in the repo root, and enable the GitHub hook trigger.

4. Add a GitHub webhook pointing to `http://<jenkins-host>:8080/github-webhook/` so each push starts a build.

5. Apply `k8s/jenkins-rbac.yml` so Jenkins can update the deployment.

</details>
