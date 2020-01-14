from boto3 import resource
vpcId = 'vpc-09a6db0d1701bd5c5'
subnetId = 'subnet-070f7402dde4fdff9'
ec2 = resource('ec2', region_name='us-west-2')
vpc = ec2.Vpc(vpcId)
route_tables = vpc.route_tables.all()
for rt in route_tables:
    for route in ec2.RouteTable(rt.route_table_id).routes:
        if route.destination_cidr_block=='0.0.0.0/0':
            print(f'{rt.id} has a route to 0.0.0.0/0')
            for rt_attribute in rt.associations_attribute:
                if rt_attribute['SubnetId'] == subnetId:
                    print(f'{subnetId} is a public subnet')