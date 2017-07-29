#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#Program:
#       Monitor the current directory recursively to detect changes.
#       If files are changed,kill process and restart process.
#History:
#2017/07/27             smile           First release
import os
import sys
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

command = ['echo','ok']
process = None

def log(s):
    print('[Monitor] %s' % s)

class MyFileSystemEventHandler(FileSystemEventHandler):
    def __init__(self,func):
        super(MyFileSystemEventHandler,self).__init__()
        self.restart = func

    #重写on_any_event方法
    #监测目录发生任何改变，触发此事件
    def on_any_event(self,event):
        if event.src_path.endswith('.py'):
            log('Python source file changed: %s' % event.src_path)
            self.restart()

def kill_process():
    global process
    if process:
        log('Kill process [%s]...' % process.pid)
        process.kill()
        process.wait()
        log('Process ended with code %s.' % process.returncode)
        process = None

def start_process():
    global process
    log('Start process %s...' % ' '.join(command))
    process = subprocess.Popen(command,stdin=sys.stdin,stdout=sys.stdout,stderr=sys.stderr)

def restart_process():
    kill_process()
    start_process()

def start_watch(path,callback):
    #Create Observer instance
    observer = Observer()
    #传入EventHandler实例，recursive=True监测子目录
    observer.schedule(MyFileSystemEventHandler(restart_process),path,recursive=True)
    #监听开始
    observer.start()
    log('Watching directory %s...' % path)
    start_process()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
            observer.stop()
    observer.join()

if __name__ == '__main__':
    #获取命令行参数
    #'python3 currentScript.py workScript.py'
    #sys.argv[0]='currentScript.py'
    #sys.argv[1]='workScript.py'
    argv = sys.argv[1:]
    if not argv:
        print('Usage:./pymonitor your-script.py')
        exit(0)

    if argv[0] != 'python3':
        argv.insert(0,'python3')
    command = argv
    path = os.path.abspath('.')
    start_watch(path,None)
