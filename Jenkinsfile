pipeline {
    agent any

    stages {
        stage('Test Kubernetes Connection') {
            steps {
                withCredentials([file(credentialsId: 'kubeconfig', variable: 'KUBECONFIG')]) {
                    sh '''
                        kubectl get nodes
                        kubectl get pods
                    '''
                }
            }
        }
    }
}
