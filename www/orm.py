#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#Program:
#       This is a ORM for MySQL.
#History:
#2017/06/29       smile          First release

import logging
import asyncio
import aiomysql

def log(sql,args=()):
    logging.info('SQL: %s' % sql)

#Close pool
async def destory_pool():
    global __pool
    __pool.close()
    await __pool.wait_closed()

#Create connect pool
#Parameter: host,port,user,password,db,charset,autocommit
#           maxsize,minsize,loop
async def create_pool(loop,**kw):
    logging.info('Create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host = kw.get('host', 'localhost'),
        port = kw.get('port', 3306),
        user = kw['user'],
        password = kw['password'],
        db = kw['db'],
        charset = kw.get('charset', 'utf8'),
        autocommit = kw.get('autocommit', 'True'),
        maxsize = kw.get('maxsize', 10),
        minsize = kw.get('minsize', 1),
        loop = loop
    )

#Package SELECT function that can execute SELECT command.
#Setup 1:acquire connection from connection pool.
#Setup 2:create a cursor to execute MySQL command.
#Setup 3:execute MySQL command with cursor.
#Setup 4:return query result.
async def select(sql,args,size=None):
    log(sql,args)
    global __pool
    async with __pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql.replace('?','%s'),args or ())
            if size:
                rs = await cur.fetchmany(size)
            else:
                rs = await cur.fetchall()

        logging.info('rows returned: %s' % len(rs))
        return rs

#Package execute function that can execute INSERT,UPDATE and DELETE command
async def execute(sql,args,autocommit=True):
    global __pool
    #acquire connection from connection pool
    async with __pool.acquire() as conn:
        #如果MySQL禁止隐式提交，则标记事务开始
        if not autocommit:
            await conn.begin()
        try:
            #create cursor to execute MySQL command
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?','%s'),args or ())
                affectrow = cur.rowcount
                #如果MySQL禁止隐式提交，手动提交事务
                if not autocommit:
                    await cur.commit()
        #如果事务处理出现错误，则回退
        except BaseException as e:
            await conn.rollback()
            raise

        #return number of affected rows
        return affectrow

#Create placeholder with '?'
def create_args_string(num):
    L = []
    for i in range(num):
        L.append('?')
    return ', '.join(L)

#A base class about Field
#描述字段的字段名，数据类型，键信息，默认值
class Field(object):
    def __init__(self,name,column_type,primary_key,default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s,%s:%s>' % (self.__class__.__name__,self.column_type,self.name)

#String Field
class StringField(Field):
    def __init__(self,name=None,ddl='varchar(100)',default=None,primary_key=False):
        super(StringField,self).__init__(name,ddl,primary_key,default)

#Bool Fileed
class BooleanField(Field):
    def __init__(self,name=None,ddl='boolean',default=False,primary_key=False):
        super(BooleanField,self).__init__(name,ddl,primary_key,default)

#Integer Field
class IntegerField(Field):
    def __init__(self,name=None,ddl='bigint',default=None,primary_key=None):
        super(IntegerField,self).__init__(name,ddl,primary_key,default)

#Float Field
class FloatField(Field):
    def __init__(self,name=None,ddl='real',default=None,primary_key=None):
        super(FloatField,self).__init__(name,ddl,primary_key,default)

#Text Field
class TextField(Field):
    def __init__(self,name=None,ddl='text',default=None,primary_key=None):
        super(TextField,self).__init__(name,ddl,primary_key,default)

#Meatclass about ORM
#作用：
#首先，拦截类的创建
#然后，修改类
#最后，返回修改后的类
class ModelMetaclass(type):
    #采集应用元类的子类属性信息
    #将采集的信息作为参数传入__new__方法
    #应用__new__方法修改类
    def __new__(cls,name,bases,attrs):
        #不对Model类应用元类
        if name == 'Model':
            return type.__new__(cls,name,bases,attrs)

        #获取数据库表名。若__table__为None,则取用类名
        tablename = attrs.get('__table__',None) or name
        logging.info('Found model: %s (table: %s)' % (name,tablename))

        #存储映射表类的属性（键-值）
        mappings = dict()
        #存储映射表类的非主键属性(仅键）
        fields = []
        #主键对应字段
        primarykey = None
        for k,v in attrs.items():
            if isinstance(v,Field):
                logging.info('Found mapping: %s ==> %s' % (k,v))
                mappings[k] = v

                if v.primary_key:
                    logging.info('Found primary key')
                    if primarykey:
                        raise Exception('Duplicate primary key for field:%s' % k)
                    primarykey = k
                else:
                    fields.append(k)

        #如果没有主键抛出异常
        if not primarykey:
            raise Exception('Primary key not found')

        #删除映射表类的属性，以便应用新的属性
        for i in mappings.keys():
            attrs.pop(i)

        #使用反单引号" ` "区别MySQL保留字，提高兼容性
        escaped_fields = list(map(lambda f:'`%s`' % f,fields))

        #重写属性
        attrs['__mappings__'] = mappings
        attrs['__table__'] = tablename
        attrs['__primary_key__'] = primarykey
        attrs['__fields__'] = fields
        attrs['__select__'] = 'SELECT `%s`, %s FROM `%s`' % (primarykey,','.join(escaped_fields),tablename)
        attrs['__insert__'] = 'INSERT `%s` (%s,`%s`) VALUES (%s)' % (tablename,','.join(escaped_fields),primarykey,create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'UPDATE `%s` SET %s WHERE `%s` = ?' % (tablename,','.join(map(lambda f:'`%s` = ?' % (mappings.get(f).name or f),fields)),primarykey)
        attrs['__delete__'] = 'DELETE FROM `%s` WHERE `%s` = ?' % (tablename,primarykey)

        #返回修改后的类
        return type.__new__(cls,name,bases,attrs)

#A base class about Model
#继承dict类特性
#附加方法：
#       以属性形式获取值
#       拦截私设属性
class Model(dict,metaclass=ModelMetaclass):
    def __init__(self,**kw):
        super(Model,self).__init__(**kw)

    def __getattr__(self,key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self,key,value):
        self[key] = value

    def getValue(self,key):
        return getattr(self,key,None)

    def getValueorDefault(self,key):
        value = getattr(self,key,None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key,str(value)))
                setattr(self,key,value)

        return value

    #ORM框架下，每条记录作为对象返回
    #@classmethod定义类方法，类对象cls便可完成某些操作
    @classmethod
    async def findAll(cls,where=None,args=None,**kw):
        sql = [cls.__select__]
        #添加WHERE子句
        if where:
            sql.append('WHERE')
            sql.append(where)

        if args is None:
            args = []

        orderby = kw.get('orderby',None)
        #添加ORDER BY子句
        if orderby:
            sql.append('ORDER BY')
            sql.append(orderby)

        limit = kw.get('limit',None)
        #添加LIMIT子句
        if limit:
            sql.append('LIMIT')
            if isinstance(limit,int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit,tuple):
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))

        #execute SQL
        rs = await select(' '.join(sql),args)
        #将每条记录作为对象返回
        return [cls(**r) for r in rs]

    
    #过滤结果数量
    @classmethod
    async def findNumber(cls,selectField,where=None,args=None):
        sql = ['SELECT %s _num_ from `%s`' % (selectField,cls.__table__)]

        #添加WHERE子句
        if where:
            sql.append('WHERE')
            sql.append(where)

        rs = await select(' '.join(sql),args)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    #返回主键的一条记录
    @classmethod
    async def find(cls,pk):
        rs = await select('%s WHERE `%s` = ?' % (cls.__select__,cls.__primary_key__),[pk],1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    #INSERT command
    async def save(self):
        args = list(map(self.getValueorDefault,self.__fields__))
        args.append(self.getValueorDefault(self.__primary_key__))
        rows = await execute(self.__insert__,args)
        if rows != 1:
            logging.warn('Faield to insert record:affected rows: %s' % rows)

    #UPDATE command
    async def update(self):
        args = list(map(self.getValue,self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__,args)
        if rows != 1:
            logging.warn('Faield to update by primary_key:affectesd rows: %s' % rows)

    #DELETE command
    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__delete__,args)
        if rows != 1:
            logging.warn('Faield to remove by primary key:affected: %s' % rows)
