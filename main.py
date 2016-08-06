#!/usr/bin/env python
# --*-- coding: utf-8 --*--
import os
import time
import threading
import Queue
import httplib
import hashlib
import socket
import redis
import json
import random
from config import *



def log(type,msg):
    #output to the logfile:
    if write_log_allow:
        #should here be any lock?
        if type<>'error':
            with open(info_log,'a') as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())+":"+msg+'\n')
        else:
            with open(error_log,'a') as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())+":"+msg+'\n')
    #output to the terminal
    if type=='info':
        print("[*]\033[32m%s\033[0m: \033[32m%s\033[0m" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), msg))
    elif type=='warning':
        print("[*]\033[32m%s\033[0m: \033[33m%s\033[0m" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), msg))
    elif type=='error':
        print("[!]\033[32m%s\033[0m: \033[31m%s\033[0m" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), msg))
        exit('[!]engaged with fatal error,exit')
    

def connect_box():
    try:
        redis_con=redis.Redis(host=redis_ip,port=redis_port,password=redis_pass,db=0)
        http_con=httplib.HTTPConnection(http_ip,http_port,timeout=20)
        http_con.request("GET",'/check.php?token='+hashlib.md5(http_pass).hexdigest())
        if http_con.getresponse().read()<>'hello,haozigege':
            log('error','http connection password error')
    except Exception,e:
        log('error',str(e))
    log('info','connect to redis server ...')
    log('info','connect to web api ...')
    return redis_con,http_con
     


def read_config():
    try:
        with open(dns_list) as f:
            dns_servers=f.read().split('\n')[:-1]
        with open(resolv_list) as f:
            resolv_domains=f.read().split('\n')[:-1]
    except Exception,e:
        log('error',str(e))
    log('info','read the config file')
    return dns_servers,resolv_domains


def dump_the_result():
    dict_={}
    for domain in resolv_domains:
        tmp=redis_con.hgetall("domain:"+domain)
        #print tmp
        dict_[domain]=tmp
    open("/tmp/cloud-host/result_"+time.strftime("%Y_%m_%d", time.localtime())+'.json','w').write(json.dumps(dict_))
    log('info','writing the outcome')



class Cloud_Host(threading.Thread):
    """This mainly designed for cloud-host"""
    def __init__(self, queue,http_con,redis_con):
        threading.Thread.__init__(self)
        self.queue=queue
        self.http_con=http_con
        self.redis_con=redis_con
        
        
    def run(self):
            log('info',self.getName()+' starts')
            while True:
                    if self.queue.empty():
                            break
                    else:
                            [self.dns,self.domain]=self.queue.get().split('||')
                    self.dns_query()
                    for result in self.results:
                            self.ip=result
                            self.check_result()
                            self.push_result()
    
    def dns_query(self):
            global allow_ipv6
            #filter the domain and the dns before run this command
            payload_ipv4="dig +vc +short "+self.domain+" @"+self.dns+" A 2>/dev/null"
            payload_ipv6="dig +vc +short "+self.domain+" @"+self.dns+" AAAA 2>/dev/null"
            r1=os.popen(payload_ipv4).read().split('\n')[:-1]
            r2=os.popen(payload_ipv6).read().split('\n')[:-1]
            if not allow_ipv6:
                    r2=[]
            self.results=r1+r2
            

    def ip_validate_check(self,data):
        '''I am too lazy to use the re moudule, so I use ping instead
        you should change it by yourself'''
	ipv4 = ['.']
	ipv6 = [':','a','b','c','d','e','f']
	flag = '0'
	for char in data:
	    if char.isdigit():
		pass
	    elif char in ipv4 :
		if flag =='6':
		    return 0
		flag = '4'
	    elif char in ipv6:
		if flag=='4':
		    return 0
		flag = '6'
	    else:
		return 0
	    
	    
        r1=os.popen('ping '+data+' -c 1 -w  1 2>/dev/null').read()
        r2=os.popen('ping6 '+data+' -c 1 -w 1 2>/dev/null').read()
        if r1 or r2:
            return 1
        return 0
        
    def check_result(self):
            '''level 1 means the website open its ssl,however it may be not the ip address 
            of the website you want, level 2 means the ip address is exactly the one
            you want.  '''
            self.level=1
            if ':' in self.ip:
                    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    self.url='https://['+self.ip+']'
            else:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.url='https://'+self.ip
            sock.settimeout(3)
            try:
                    sock.connect((self.ip,443))
            except:
                    self.level=0
                    return 
            #you need to validate the url and domain before you use popen
            payload="curl '"+self.url+"' -k  -m 3 -H 'host: "+self.domain+"' -H \
            'accept-encoding: gzip, deflate, sdch' -H 'accept-language: zh-CN,\
            zh;q=0.8' -H 'upgrade-insecure-requests: 1' -H 'user-agent: Mozilla/5.0\
            (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/49.0.2623.110\
            Safari/537.36' -H 'accept: text/html,application/xhtml+xml,application/xml;q=0.9,\
            image/webp,*/*;q=0.8' -H 'cache-control: max-age=0'  --compressed 2>/dev/null | \
            grep "+self.domain+" |wc -l"
            if os.popen(payload).readlines() and os.popen(payload).readlines()[0][:-1]<>0:
                    self.level=2
            return

    def push_result(self):
            '''push the result to the redis server'''
            if not self.ip_validate_check(self.ip):
                return
            self.count=redis_con.hget("domain:"+self.domain,"count")
            if self.count:
                self.count=int(self.count)
            else:
                self.count=0
            #avoid the repeat ip
            if redis_con.get("ip:"+self.ip):
                return
            if self.level==2:
                log('warning','one possible result found')
		log('warning',str(self.queue.qsize())+" tasks remains") 
            redis_con.set("ip:"+self.ip,"1")
            redis_con.hset("domain:"+self.domain,"ip_"+str(self.count),self.ip)
            redis_con.hset("domain:"+self.domain,"dns_"+str(self.count),self.dns)
            redis_con.hset("domain:"+self.domain,"level_"+str(self.count),self.level)
            redis_con.hset("domain:"+self.domain,"count",self.count+1)
        

def thread_ctrl(thread_num):
    #init the queue
    queue=Queue.Queue(100000)
    #random order
    random.shuffle(dns_servers)
    random.shuffle(resolv_domains)
    for dns in dns_servers:
        for domain in resolv_domains:
            queue.put(dns+"||"+domain)
    #start the  threads
    threads=[]
    for i in range(thread_num):
        t=Cloud_Host(queue,http_con,redis_con)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
        pass




if __name__ == '__main__':
    redis_con,http_con=connect_box()
    dns_servers,resolv_domains=read_config()
    #print dns_servers
    #print resolv_domains

    log('info','start the cloud-host')
    while True:
        thread_ctrl(thread_num)
        dump_the_result()
        time.sleep(sleep_time)
