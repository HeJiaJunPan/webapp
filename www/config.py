#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#Program:
#       load default config and override config
#Hostory:
#2017/07/07         smile       First release

import config_default

#simple dict but support access as x.y style
class Dict(dict):
    def __init__(self,names=(),values=(),**kw):
        super(Dict,self).__init__(**kw)
        for k,v in zip(names,values):
            self[k] = v

    #x.y style
    def __getattr__(self,key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    #拦截外设属性
    def __setattr__(self,key,value):
        self[key] = value

#Merge config file
#config_override覆盖默认配置的条目
#使用递归函数
def merge(defaults,override):
    r = dict()
    for k,v in defaults.items():
        if k in override:
            if isinstance(v,dict):
                r[k] = merge(v,override[k])
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

#dict to Dict
def dicttoDict(d):
    D = Dict()
    for k,v in d.items():
        D[k] = dicttoDict(v) if isinstance(v,dict) else v
    return D

configs = config_default.configs
try:
    import config_override
    configs = merge(configs,config_override.configs)
except ImportError:
    pass


configs = dicttoDict(configs)
