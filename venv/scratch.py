from boto3 import resource

subnets = ['subnet-060c726ac6e95750', 'subnet-075aa287882d71709']
ec2 = resource('ec2', region_name='us-east-2')
vpcId = 'vpc-087f823209a323c2e'
valid_subnets = []
for subnet in subnets:
    try:
        vpc_id = ec2.Subnet(subnet).vpc_id
    except BaseException:
        print('subnet does not exist')
        pass
    else:
        if vpc_id != vpcId:
            print(f'{subnet} does not belong to the cluster VPC {vpcId}')
            #raise Exception(f'{subnet} does not belong to the cluster VPC')
            ### TODO: Only return valid subnets
        else:
            valid_subnets.append(subnet)
print(valid_subnets)