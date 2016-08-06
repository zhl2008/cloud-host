#!/usr/bin/env python

from config import *
import redis

 

def check_redis(domain):
    tmp = ''
    result = redis_con.hgetall("domain:"+domain)
    if not result.has_key('count'):
	return ''
    count = int(result['count'])
    for i in range(count):
	if result['level_'+str(i)]=='2':
	    tmp += result['ip_'+str(i)]+' '+domain+'\n'
    return tmp
 


try:
    redis_con=redis.Redis(host=redis_ip,port=redis_port,password=redis_pass,db=0)
except Exception,e:
    print e
    exit()


hosts = ''
domains = open('resolv.list').readlines()
for domain in domains:
    tmp = check_redis(domain[:-1])
    if tmp=='':
	continue	
    print tmp,
    hosts += tmp

open('hosts','w').write(hosts)


