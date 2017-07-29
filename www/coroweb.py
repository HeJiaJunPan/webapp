#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#Program:
#       This a async web frame depending on aiohttp
#History:
#2017/07/06         smile       First release

__author__ = 'smile'

import os
import asyncio
import inspect
import functools
import logging
from urllib import parse
from aiohttp import web
from apis import APIError

#编写装饰器，装饰URL处理函数
#理由：如果只看一个URL处理函数，其和路径关系弱，要在后面特别指出。
#      另外，aiohttp要求其返回web.respond对象。我们则希望其返回值多样

#GET method
def get(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator

#POST method
def post(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator

#编写几个检测函数参数的函数
#获取必须传入参数的命名关键字参数
def get_required_kw_args(func):
    args = []
    params = inspect.signature(func).parameters
    for name,param in params.items():
        #若参数类型为命名关键字而又无默认值，则必须传入此参数
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default ==inspect.Parameter.empty:
            args.append(name)
    return tuple(args)

#获取所有命名关键字，在参数列表中
def get_named_kw_args(func):
    args = []
    params = inspect.signature(func).parameters
    for name ,param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)

#判断是否有命名关键字参数
def has_named_kw_args(func):
    params = inspect.signature(func).parameters
    for name,param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True

#判断是否有关键字参数
def has_var_kw_args(func):
    params = inspect.signature(func).parameters
    for name,param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True

#判断是否含有“request”参数，且该参数为位置参数时，只能是最后一个位置参数
def has_request_arg(func):
    sig = inspect.signature(func)
    params = sig.parameters
    found = False
    for name,param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError('request parameter must be the last named parameter in function:%s %s' % (func.__name__,str(sig)))
    return found

#Request handler class
#由于我们的框架基于aiohttp,通过这个类包装URL处理函数，满足aiohttp的入口条件
#同时，从request对象中获取相应的参数信息
class RequestHandler(object):
    def __init__(self,app,func):
        self._app = app
        self._func = func
        self._has_request_arg = has_request_arg(func)
        self._has_var_kw_args = has_var_kw_args(func)
        self._has_named_kw_args = has_named_kw_args(func)
        self._named_kw_args = get_named_kw_args(func)
        self._required_kw_args = get_required_kw_args(func)

    #aiohttp的入口条件：一个仅含request位置参数的可调用对象
    async def __call__(self,request):
        kw = None
        if self._has_var_kw_args or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                #if method is post,read request body
                #how read request body depend on content type
                if not request.content_type:
                    return web.HTTPBadRequest(text='Missing content-Type')
                ct = request.content_type.lower()
                #read request body decode as json
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params,dict):
                        return web.HTTPBadRequest(text='json body must be dict object')
                    kw = params
                #read POST parameters from request body
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest(text='unsupported content-Type %s' % request.content_type)

            if request.method == 'GET':
                #The query string in the URL
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k,v in parse.parse_qs(qs,True).items():
                        kw[k] = v[0]

        if kw is None:
            kw = dict(**request.match_info)
        else:
            #对于关键字参数，任何参数都是有效的；
            #但是，若没有关键字参数，必须保证命名关键字参数传入
            if not self._has_var_kw_args and self._named_kw_args:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy

            #可能存在除request外的位置参数或未获取到的命名关键字参数
            #例如，'/manage/blog/{id}'这样链接中的id参数
            for k,v in request.match_info.items():
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v

        if self._has_request_arg:
            kw['request'] = request

        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest(text='Missing argument: %s' % name)

        logging.info('call with args: %s' % str(kw))
        try:
            r = await self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error,data=e.data,message=e.message)

#重构app.router.add_route method
def add_route(app, func):
    method = getattr(func, '__method__', None)
    path = getattr(func, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(func))
    #如果URL处理函数既不是协程又不是生成器对象，则封装为协程对象
    if not asyncio.iscoroutinefunction(func) and not inspect.isgeneratorfunction(func):
        func = asyncio.coroutine(func)
    logging.info('add route %s %s => %s(%s)' % (method,path,func.__name__,', '.join(inspect.signature(func).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app, func))
#从模块添加所有URL处理函数
def add_routes(app,module_name):
    n = module_name.rfind('.')
    if n == (-1):
        mod = __import__(module_name,globals(),locals())
    else:
        name = module_name[n+1: ]
        mod = getattr(__import__(module_name[:n],globals(),locals(),[name]),name)
    for attr in dir(mod):
        if attr.startswith('_'):
            continue
        func = getattr(mod,attr)
        if callable(func):
            method = getattr(func,'__method__',None)
            path = getattr(func,'__route__',None)
            if method and path:
                add_route(app,func)

#添加静态文件
def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'static')
    app.router.add_static('/static/',path)
    logging.info('add static %s => %s' % ('/static/',path))
