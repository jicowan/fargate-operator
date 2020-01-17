import kopf
import requests
import asyncio
import logging
import json
from time import sleep
from boto3 import client
from boto3 import resource

#@kopf.on.startup()
#async def startup_fn(logger, **kwarg):

class FargateProfile(object):
    def __init__(self, subnets, podExecutionRoleArn, selectors, tags, *args, **kwargs):
        self.subnets = subnets
        self.podExecutionRoleArn = podExecutionRoleArn
        self.selectors = selectors
        self.tags = tags

class Cluster(object):
    def __init__(self, name, version, platformVersion, resourcesVpcConfig, *args, **kwargs):
        self.name = name
        self.version = version
        self.platformVersion = platformVersion
        self.resourcesVpcConfig = resourcesVpcConfig

def create_profile(name, cluster, executionRoleArn, subnets, selectors, tags):
    try:
        eks.create_fargate_profile(
            fargateProfileName=name,
            clusterName=cluster,
            podExecutionRoleArn=executionRoleArn,
            subnets=subnets,
            selectors=selectors,
            tags=tags
        )
    except BaseException as e:
        logging.error(e)

def is_public_subnet(subnets, vpcId):
    '''Method to determine whether the subnets referenced in the Fargate profile are public.'''
    ec2_resource = resource('ec2', region_name=region)
    vpc = ec2_resource.Vpc(vpcId)
    route_tables = vpc.route_tables.all()
    for rt in route_tables:
        for route in ec2_resource.RouteTable(rt.route_table_id).routes:
            if route.destination_cidr_block == '0.0.0.0/0':
                logging.info(f'{rt.id} has a route to 0.0.0.0/0')
                for rt_attribute in rt.associations_attribute:
                    for subnet in subnets:
                        if rt_attribute['SubnetId'] == subnet:
                            logging.error(f'{subnet} is a public subnet')

def is_valid_subnet(subnets, vpcId):
    ec2_resource = resource('ec2', region_name=region)
    valid_subnets = []
    for subnet in subnets:
        try:
            vpc_id = ec2_resource.Subnet(subnet).vpc_id
        except BaseException as e:
            logging.error(e)
            pass
        else:
            if vpc_id != vpcId:
                logging.error(f'{subnet} does not belong to the cluster VPC {vpcId}')
            else:
                valid_subnets.append(subnet)
    return valid_subnets

def check_list_size(selectors):
    '''Enforced through CRD schema.  No longer necessary'''
    if len(selectors) > 5:
        logging.error("Exceeded maximum selectors. You may only have up to 5 selectors in a Fargate profile.")
        return Exception
    else:
        logging.info(f'The list has {len(selectors)} elements')

def check_cluster_version(version, platformVersion):
    if version not in ['1.14']:
        logging.error("Cluster version has to be at 1.14.8 or above to use Fargate")
        return Exception
    elif version in ['1.14'] and platformVersion not in ['eks.5', 'eks.6', 'eks.7']:
        logging.error("Cluster version has to be at 1.14.8 and eks.5 or above to use Fargate.")
        return Exception
    else:
        logging.info(f'Cluster at the correct version and patch level.')

def is_valid_role(executionRoleArn):
    role_name = executionRoleArn[executionRoleArn.rfind("/")+1:]
    try:
        role = iam.Role(role_name)
    except BaseException as e:
        logging.error(f'Not a valid role Arn')
        return Exception
    attached_policies = role.attached_policies.all()
    ### attached_policies = role.attached_policies.filter(PathPrefix='/.*AmazonEKSForFargateServiceRolePolicy/g')
    for i in attached_policies:
        if i.policy_name == 'AmazonEKSFargatePodExecutionRolePolicy':
            logging.info(f'Role is valid')
        else:
            logging.info(f'Required policy is missing from execution role')
            return Exception

def get_metadata():
    try:
        r = requests.get("http://169.254.169.254/latest/dynamic/instance-identity/document")
    except BaseException as e:
        logging.error(f'Metadata is inaccessible: {e}')
    response_json = r.json()
    region = response_json.get('region')
    instance_id = response_json.get('instanceId')
    ec2 = resource('ec2', region_name=region)
    instance = ec2.Instance(instance_id)
    tags = instance.tags or []
    cluster_name = [i['Key'] for i in tags if 'kubernetes.io/cluster/' in i['Key']]
    cluster_name = cluster_name[0].split('/')[2]
    return cluster_name, region

@kopf.on.delete('jicomusic.com', 'v1', 'fargateprofiles')
def delete_fn(meta, spec, namespace, logger, **kwargs):
    #cluster_name, region = get_metadata()
    fargate_profile_name = meta.get('name')
    # TODO: check to see whether profile exists
    delete_fargate_profile(cluster_name, fargate_profile_name)

def delete_fargate_profile(clusterName, fargateProfileName):
    while eks.describe_fargate_profile(clusterName=clusterName, fargateProfileName=fargateProfileName)['fargateProfile']['status'] != 'ACTIVE':
        sleep(5)
    try:
        eks.delete_fargate_profile(clusterName=clusterName, fargateProfileName=fargateProfileName)
    except BaseException as e:
        logging.error(e)
    logging.info(f'Fargate profile {fargateProfileName} has been deleted.')

@kopf.on.resume('jicomusic.com', 'v1', 'fargateprofiles')
@kopf.on.create('jicomusic.com', 'v1', 'fargateprofiles', retries=3, backoff=5.0)
def create_fn(meta, spec, namespace, logger, **kwargs):
    cluster = Cluster(**eks.describe_cluster(name = cluster_name)['cluster'])
    profile_name = meta.get('name')
    # TODO: Check to see whether there is a profile with the same name
    profile_spec = FargateProfile(**spec)
    valid_subnets = is_valid_subnet(profile_spec.subnets, cluster.resourcesVpcConfig['vpcId'])
    #is_public_subnet(valid_subnets,cluster.resourcesVpcConfig['vpcId'])
    if valid_subnets != []:
        if is_valid_role(profile_spec.podExecutionRoleArn) is not Exception and \
        check_cluster_version(cluster.version, cluster.platformVersion) is not Exception:
            create_profile(profile_name, cluster_name, profile_spec.podExecutionRoleArn, valid_subnets, profile_spec.selectors, profile_spec.tags)
        else:
            logging.error(f'Invalid data in FargateProfile')
    else:
        logging.error(f'Invalid data in FargateProfile')

logging.basicConfig(format='%(asctime)s [%(levelname)s] - %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logging.INFO)
cluster_name, region = get_metadata()
eks = client('eks', region_name=region)
ec2 = client('ec2', region_name=region)
iam = resource('iam')