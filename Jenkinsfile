pipeline {
  agent any

  environment {
    IMAGE = "preranasseshadri/peak"
    TAG   = "${env.BUILD_NUMBER}"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Build Docker Image') {
      steps {
        sh 'docker build -t $IMAGE:$TAG -t $IMAGE:latest .'
      }
    }

    stage('Test') {
      steps {
        sh 'docker run --rm -e SECRET_KEY=test -e DATABASE_URL=sqlite:///:memory: $IMAGE:$TAG python -m pytest -v'
      }
    }

    stage('Security Scan') {
      steps {
        sh 'trivy image --exit-code 1 --severity CRITICAL --ignore-unfixed --no-progress $IMAGE:$TAG'
      }
    }

    stage('Push to Docker Hub') {
      steps {
        withCredentials([usernamePassword(
          credentialsId: 'dockerhub-creds',
          usernameVariable: 'DOCKER_USERNAME',
          passwordVariable: 'DOCKER_PASSWORD'
        )]) {
          sh '''
            echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
            docker push $IMAGE:$TAG
            docker push $IMAGE:latest
            docker logout
          '''
        }
      }
    }

    stage('Deploy to Kubernetes') {
      steps {
        withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
          sh '''
            kubectl set image deployment/peak peak=$IMAGE:$TAG
            kubectl rollout status deployment/peak --timeout=180s
          '''
        }
      }
    }
  }
}