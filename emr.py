#!/usr/bin/env python3
#
# cluster_info.py:
# A module of useful EMR cluster management tools.
# We've had to build our own to work within the Census Environment
# This script appears in:
#   das-vm-config/bin/cluster_info.py
#   emr_stats/cluster_info.py
#
# Currently we manually sync the two; perhaps it should be moved to ctools.

import os
import sys
from pathlib import Path
import json

import subprocess
from subprocess import Popen,PIPE,call,check_call,check_output
import multiprocessing
import time


# Bring in aws from the current directory
sys.path.append( os.path.dirname(__file__))
import aws

# Beware!
# An error occurred (ThrottlingException) when calling the ListInstances operation (reached max retries: 4): Rate exceeded
# We experienced throttling with DEFAULT_WORKERS=20
# So we use 4
DEFAULT_WORKERS=4

# Bring in ec2. It's either in the current directory, or its found through
# the ctools.ec2 module

try:
    import ec2
except ImportError as e:
    try:
        import ctools.ec2 as ec2
    except ImportError as e:
        raise RuntimeError("Cannot import ec2")

# Proxy is controlled in aws

Status='Status'


def show_credentials():
    subprocess.call(['aws','configure','list'])

def describe_cluster(clusterId):
    return json.loads(subprocess.check_output(['aws','emr','describe-cluster',
                                               '--output','json','--cluster-id',clusterId]))['Cluster']

def list_instances(clusterId):
    return json.loads(subprocess.check_output(['aws','emr','list-instances',
                                               '--output','json','--cluster-id',clusterId]))['Instances']

def get_url(url):
    import urllib.request
    with urllib.request.urlopen(url) as response:
        return response.read().decode('utf-8')

def user_data():
    return json.loads(get_url("http://169.254.169.254/2016-09-02/user-data/"))

def isMaster():
    """Returns true if running on master"""
    return user_data()['isMaster']

def isSlave():
    """Returns true if running on master"""
    return user_data()['isSlave']

def decode_status(meminfo):
    return { line[:line.find(":")] : line[line.find(":")+1:].strip() for line in meminfo.split("\n") }

def clusterId():
    return user_data()['clusterId']

def get_instance_type(host):
    return run_command_on_host(host,"curl -s http://169.254.169.254/latest/meta-data/instance-type")

def list_clusters():
    """Returns the AWS Dictionary"""
    res = check_output(['aws','emr','list-clusters','--output','json'],encoding='utf-8')
    return json.loads(res)['Clusters']

def describe_cluster(clusterId):
    res = check_output(['aws','emr','describe-cluster','--output','json','--cluster',clusterId], encoding='utf-8')
    return json.loads(res)['Cluster']    

def list_instances(clusterId):
    res = check_output(['aws','emr','list-instances','--output','json','--cluster-id',clusterId], encoding='utf-8')
    return json.loads(res)['Instances']    

def add_cluster_info(cluster):
    clusterId = cluster['Id']
    cluster['describe-cluster'] = describe_cluster(clusterId)
    cluster['instances']        = list_instances(clusterId)
    cluster['terminated']       = 'EndDateTime' in cluster['Status']['Timeline']
    # Get the id of the master
    try:
        masterPublicDnsName = cluster['describe-cluster']['MasterPublicDnsName']
        masterInstance = [i for i in cluster['instances'] if i['PrivateDnsName']==masterPublicDnsName][0]
        masterInstanceId = masterInstance['Ec2InstanceId']
        # Get the master tags
        cluster['MasterInstanceTags'] = {}
        for tag in ec2.describe_tags(resourceId=masterInstanceId):
            cluster['MasterInstanceTags'][tag['Key']] = tag['Value']
    except KeyError as e:
        pass
    return cluster


def complete_cluster_info(workers=DEFAULT_WORKERS,terminated=False):

    """Pull all of the information about a cluster efficiently using the EMR cluster API and multithreading.
    if terminated=True, get information about the terminated clusters as well.
    """
    clusters = list_clusters()
    for cluster in list(clusters):
        if terminated==False and cluster['Status']['State']=='TERMINATED':
            clusters.remove(cluster)
    with multiprocessing.Pool(workers) as p:
        clusters = p.map(add_cluster_info,clusters)

    return clusters

