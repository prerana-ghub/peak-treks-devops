# 🏔️ PEAK - Trek Booking Platform  

PEAK is a **trek booking application** built with Flask and deployed on AWS using a containerized DevOps workflow.  

It demonstrates how a modern application can move through the **complete DevOps lifecycle** - from source code to automated deployment - while staying secure, scalable, and cloud‑ready.  

---

## 🔑 Key Features  

- Trek catalog with details (difficulty, duration, pricing, dates, images)  
- Secure user registration & login  
- Shopping cart with participant count & total calculation  
- Checkout flow with demo payment integration  
- Booking dashboard to view past/current bookings  
- Automated email notifications for bookings & enquiries  

Treks included: **Kudremukh, Kumara Parvatha, Savandurga, Skandagiri, Kodachadri and Nandi Hills**  

---

## ⚙️ Tech Stack  

- **Frontend**: HTML, CSS, Jinja2  
- **Backend**: Python (Flask)  
- **Database**: PostgreSQL + SQLAlchemy  
- **Testing**: Pytest  
- **Version Control**: Git, GitHub  
- **Containerization**: Docker, Docker Hub  
- **CI/CD**: Jenkins  
- **Orchestration**: Kubernetes (k8s)   
- **Config Management**: Ansible  
- **Security**: Trivy  

---

## 🚀 DevOps Pipeline  

```text
GitHub → Jenkins → Tests → Trivy Scan → Docker Build → Docker Hub → Kubernetes → Application
```

- **Automated testing** ensures code quality  
- **Security scanning** catches vulnerabilities early  
- **Containerization** makes deployments portable  
- **Kubernetes orchestration** enables scaling and resilience  
- **Ansible** automates server setup  

---

## 🏗️ Architecture  

The PEAK platform follows a modern DevOps pipeline and cloud‑native deployment model:

![PEAK Architecture](architecture.png)

- **Source Control** → GitHub hosts the codebase  
- **CI/CD** → Jenkins automates testing, security scanning, and builds  
- **Containerization** → Docker packages the app, stored in Docker Hub  
- **Orchestration** → Kubernetes (k8s) manages deployment and scaling  
- **Infrastructure** → AWS EC2 hosts the cluster  
- **Configuration Management** → Ansible configures servers  
- **Security** → Trivy scans images before deployment  
- **Autoscaling** → Kubernetes HPA adjusts replicas based on load  
- **Users** → Access the live application via browser  

---

## 📂 Project Structure  

### # Root  
```
peak/
├── app.py
├── booking_billing.py
├── booking_emails.py
├── database.py
├── models.py
├── trek_dates.py
├── requirements.txt
├── Dockerfile
├── Jenkinsfile
├── pytest.ini
└── README.md
```

### # helpers/  
```
helpers/
├── shopping_cart.py
├── user_authentication.py
└── user_notifications.py
```

### # routes/  
```
routes/
├── trek_booking.py
├── user_authentication.py
└── website_pages.py
```

### # templates/  
```
templates/
├── base.html
├── home.html
├── trek_list.html
├── trek_detail.html
├── cart.html
├── checkout.html
├── booking_confirmation.html
├── my_bookings.html
└── email_*.html
```

### # static/  
```
static/
├── home-hero.jpg
├── kudremukh.jpg
├── kumara-parvatha.jpg
└── savandurga.png
```

### # tests/  
```
tests/
└── test_app.py
```

### # ansible/
```
ansible/
├── inventory.ini
├── setup-docker.yml
├── setup-jenkins.yml
└── setup-k8s-prereqs.yml
````

**Ansible Purpose:**

* Automates server configuration
* Playbooks included:

  * `setup-docker.yml` → Installs Docker and dependencies
  * `setup-jenkins.yml` → Configures the Jenkins server
  * `setup-k8s-prereqs.yml` → Prepares nodes for Kubernetes deployment
  * `inventory.ini` → Lists target hosts for the playbooks

### # k8s/
```
k8s/
├── deployment.yml
├── service.yml
├── postgres.yml
├── db-init-job.yml
├── hpa.yml
└── jenkins-rbac.yml
```

**Kubernetes Purpose:**

* Deploys and manages the PEAK application on the k3s cluster
* Manifests included:

  * `deployment.yml` → Deploys the PEAK application
  * `service.yml` → Exposes the PEAK application
  * `postgres.yml` → Deploys the PostgreSQL database
  * `db-init-job.yml` → Initializes the application database
  * `hpa.yml` → Configures horizontal pod autoscaling for the PEAK application
  * `jenkins-rbac.yml` → Grants Jenkins the permissions required to deploy to Kubernetes

## 🛠️ Setup  

### # Local Development  

1. **Clone the repository**  
   ```bash
   git clone https://github.com/prerana-ghub/peak-treks-devops.git
   cd peak-treks-devops
   ```

2. **Create a virtual environment**  
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**  
   ```bash
   python app.py
   ```
   Access via Flask dev server at `http://localhost:5000`.

5. **Run tests**  
   ```bash
   pytest
   ```

---

### # Docker Setup

1. **Build the image**
   ```bash
   docker build -t peak .
   ```

2. **Run the container** (needs a secret key and a database URL)
   ```bash
   docker run -p 5000:5000 \
     -e SECRET_KEY=your-secret-key \
     -e DATABASE_URL=postgresql://user:password@host:5432/peak \
     peak
   ```

3. **Push to Docker Hub** (after login)
   ```bash
   docker tag peak <your-dockerhub-username>/peak:v1
   docker push <your-dockerhub-username>/peak:v1
   ```

---

### # Kubernetes Deployment  

1. **Apply manifests**  
   ```bash
   kubectl apply -f k8s/postgres.yml
   kubectl apply -f k8s/db-init-job.yml
   kubectl apply -f k8s/deployment.yml
   kubectl apply -f k8s/service.yml
   kubectl apply -f k8s/hpa.yml
   ```

2. **Check pods**  
   ```bash
   kubectl get pods
   ```

3. **Access service**  
   Expose via LoadBalancer or NodePort depending on cluster setup.  

---

## 🎯 Project Goal  

PEAK is a **hands‑on showcase of DevOps practices**:  

- End‑to‑end CI/CD automation  
- Secure, containerized deployments  
- Cloud-based infrastructure using AWS EC2 and Ansible  
- Scalable orchestration with Kubernetes   

---

## 📸 Visuals  

Screenshots and diagrams are available in the `screenshots/` folder
