# fargate-operator
The fargate-operator is a Kubernetes operator that allows you to manage Fargate Profiles directly from Kubernetes. 
It utilizes Zalando's kopf, a framework for writing Kubernetes operators in Python.  The operator watches for the creation,  
or deletion of a FargateProfile object.  The FargateProfile object is implemented as a Custom Resource Definition (CRD) 
that provides input for the CreateFargateProfile and DeleteFargateProfile AWS API calls.  

## Installing the operator

### Creating a IAM role and service account
Since the operator is performing input validation, it needs a Kubernetes service account that allows it to
assume an IAM role that grants it a variety of permissions.  This is accomplished using the new IAM 
Roles for Service Accounts (IRSA) feature for EKS.  

`eksctl` is far and away the easiest way to create the IAM role and corresponding Kubernetes service account.  Start by
running the following command: 

```bash
eksctl utils associate-iam-oidc-provider --name=<cluster> --approve
eksctl create iamserviceaccount --cluster=<clusterName> --name=fargate --namespace=default --attach-policy-arn=<policyARN>
```

Use the ARN of the policy created from the `IAMPolicy.json` when creating the service account. 

### Creating the RBAC roles
In order for the operator function properly, it needs a set of baseline permissions including the ability to read FargateProfile 
objects. All of these permissions are packaged in the rbac.yaml manifest. 
You can apply these permissions to the cluster by running:

```bash
kubectl apply -f rbac.yaml
```

### Creating the fargateprofiles CRD
the fargate-operator relies on a CRD that specifies the input parameters for creating a Fargate Profile. 
Create the CRD by running:

```bash
kubectl apply -f crd.yaml 
```

After the CRD has been created you can create fargateprofile objects. Below is an example of a fargateprofile that creates
a Fargate Profile for the default, system, hello, and world namespaces.  It also applies a set of selector labels that limit
the pods the profile is applied to, i.e. only pods with matching labels will be run as Fargate pods.  

```yaml
apiVersion: jicomusic.com/v1
kind: FargateProfile
metadata:
  name: new-profile-7
spec:
  subnets: [subnet-075aa287882d71709, subnet-0b36ca4d53f742857]
  podExecutionRoleArn: arn:aws:iam::123456789012:role/eksctl-cluster-workshop-cl-FargatePodExecutionRole-ZBZNZ6OBYOHE
  selectors:
  - namespace: default
    labels:
      foo: bar
      red: black
      green: blue
      orange: red
      purple: yellow
      green: white
  - namespace: system
    labels:
      foo: bar
  - namespace: hello
    labels:
      foo: bar
  - namespace: world
    labels:
      foo: bar
  tags:
      red: black
      green: blue
```
Note: the metadata name only accepts lowercase characters.

### Deploying the operator
The deployment.yaml manifest in this repository references a serviceAccountName that has to be set to the service account created 
in the Creating an IAM role and service account step above.  Once that's done, the operator can be deployed by running:

```bash
kubectl apply -f deployment.yaml 
```

### Create a fargateprofile object
With the operator running, create a new fargateprofile manifest and apply it to the cluster. For an example, see the sample-crd.yaml 
in this repository.
