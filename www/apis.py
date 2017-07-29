#!/usr/bin/env python3
# -*- coding:utf-8 -*-
#Program:
#       JSON API Error Definition
#Hostory:
#2017/07/10         smile       First release

class APIError(Exception):
    def __init__(self,error,data='',message=''):
        super(APIError,self).__init__(message)
        self.error = error
        self.data = data
        self.message = message

class APIValueError(APIError):
    def __init__(self,field,message=''):
        super(APIValueError,self).__init__('value:invalid',field,message)

class APIResourceNotFoundError(APIError):
    def __init__(self,field,message=''):
        super(APIResourceNotFound,self).__init__('value:not found',field,message)

class APIPermissionError(APIError):
    def __init__(self,message=''):
        super(APIPermissionError,self).__init__('permission:forbidden','permission',message)

class Page(object):
    def __init__(self,item_count,page_index=1,page_size=10):
        #项目总数
        self.item_count = item_count
        #每页项目数量
        self.page_size = page_size
        #页数
        self.page_count = item_count // page_size + (1 if item_count % page_size > 0 else 0)

        #当项目数为0或者页码超过总页数，显示第一页
        if item_count == 0 or page_index > self.page_count:
            self.offset = 0
            self.limit = 0
            self.page_index = 1
        else:
            self.page_index = page_index
            #下一页的起点，从数据库中检索的行号
            self.offset = self.page_size * (page_index -1)
            #每页最多显示的项目量
            self.limit = self.page_size

        self.has_next = self.page_index < self.page_count
        self.has_previous = self.page_index > 1

    def __str__(self):
        return 'item_count:%s,page_count:%s,page_index:%s,page_size:%s,offset:%s,limit:%s' % (self.item_count,self.page_count,self.page_index,self.page_size,self.offset,self.limit)

    __repr__ = __str__
