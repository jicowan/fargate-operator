# group-operator
The fargate-operator is a Kubernetes operator that allows you to manage Fargate Profiles from Kubernetes. 
It utilizes Zalando's kopf, a framework for writing Kubernetes operators in Python.  The operator watches for the creation,  
or deletion of a FargateProfile object.  The FargateProfile object is implemented as a Custom Resource Definition (CRD) 
that provides input for the CreateFargateProfile and DeleteFargateProfile AWS API calls.  

## Installing the operator

### Creating a IAM role and service account
Since the operator is performing input validation, it needs a Kubernetes service account that allows it to
assume an IAM role that grants it a variety of different permissions.  This is accomplished using the new IAM 
Roles for Service Accounts (IRSA) feature for EKS which requires Kubernetes v1.13 or higher.  

`eksctl` is far and away the easiest way to create the IAM role and corresponding Kubernetes service account.  Start by
running the following command: 

```bash
eksctl utils associate-iam-oidc-provider --name=<cluster> --approve
eksctl create iamserviceaccount --cluster=<clusterName> --name=fargate --namespace=default --attach-policy-arn=<policyARN>
```

Use the ARN of the policy that is created from the `IAMPolicy.json` when creating the service account. 

To be continued...