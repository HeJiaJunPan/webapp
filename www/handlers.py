#!/usr/bin/env python3
# -*- coding:utf-8 -*-
import re
import time
import json
import hashlib
import asyncio
import markdown2
import logging
from models import Blog, User,Comment,next_id
from coroweb import get,post
from apis import APIError, APIValueError,APIPermissionError,APIResourceNotFoundError,Page
from aiohttp import web
from config import configs

#cookie name
COOKIE_NAME = 'awesession'
#cookie密钥
_COOKIE_KEY = configs.session.secret

#Email格式
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')

#SHA1格式
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p

def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&','&amp;').replace('>','&gt;'),filter(lambda s: s.strip() != '',text.split('\n')))
    return ''.join(lines)

#--------------用户浏览页-------------------
@get('/')
async def index(request,*,page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    page = Page(num,page_index)
    if num == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(orderBy='created_at desc',limit=(page.offset,page.limit))
    return {
        '__template__':'blogs.html',
        'page':page,
        'blogs':blogs,
        '__user__':request.__user__
    }

#获取注册页面
@get('/register')
def get_register():
    return {
        '__template__':'register.html'
    }

#获取登录页面
@get('/signin')
def get_signin():
    return {
        '__template__':'signin.html'
    }

#user sign out
@get('/signout')
def signout(request):
    #获取重定向链接
    referer = request.headers.get('Referer',None)
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME,'-deleted-',max_age=0,httponly=True)
    logging.info('user signed out.')
    return r

@get('/blog/{id}')
async def get_blog(id,request):
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id = ?',[id],orderBy='created_at desc')
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__':'blog.html',
        'blog':blog,
        'comments':comments,
        '__user__':request.__user__
    }

#cookie生成
#方案：
#cookie = "userid" + "expires time" + SHA1("userid"+"userpassword"+
#         "expires" + "cookiekey")
def user2cookie(user,max_age):
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id,user.password,expires,_COOKIE_KEY)
    L = [user.id,expires,hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

#cookie验证
async def cookie2user(cookie_str):
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid,expires,sha1 = L
        if int(expires) < time.time():
            return None
        user = await User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (user.id,user.password,expires,_COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.password = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None

#-----------------后端API-----------------------
#user register
@post('/api/users')
async def api_user_register(*,name,email,passwd):
    #check name of user
    if not name or not name.strip():
        raise APIValueError('name')
    #check form of email
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    #check user password
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('password')
    #check exist user
    users = await User.findAll('email = ?',[email])
    if len(users) > 0:
        raise APIError('register:failed','email','Email is already in use.')
    #save user
    uid = next_id()
    sha1_password = '%s:%s' % (uid,passwd)
    user = User(id=uid,name=name.strip(),email=email,password=hashlib.sha1(sha1_password.encode('utf-8')).hexdigest(),image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    r = web.Response()
    r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
    user.password = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r

#user sign in
@post('/api/authenticate')
async def authenticate(*,email,passwd):
    if not email:
        raise APIValueError('email')
    if not passwd:
        raise APIValueError('password')
    users = await User.findAll('email = ?',[email])
    if len(users) == 0:
        raise APIValueError('email','Email not exist')
    user = users[0]
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.password != sha1.hexdigest():
        raise APIValue('password','Invalid password')
    r = web.Response()
    r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
    user.password = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r

def check_admin(request):
    if not request.__user__ or not request.__user__.admin:
        raise APIPermissionError()
#获取日志
@get('/api/blogs/{id}')
async def api_get_blog(*,id):
    blog = await Blog.find(id)
    return blog

@post('/api/blogs')
async def api_create_blog(request,*,name,summary,content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name','name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary','summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content','content cannot be empty.')

    blog = Blog(user_id=request.__user__.id,user_name=request.__user__.name,user_image=request.__user__.image,name=name.strip(),summary=summary.strip(),content=content.strip())
    await blog.save()
    return blog

@get('/api/blogs')
async def api_blogs(*,page='1'):
    #将request object中的字符串量转换为数字量
    page_index = get_page_index(page)
    #获取博客总数
    num = await Blog.findNumber('count(id)')
    #获取指定页码页信息
    p = Page(num,page_index)
    if num == 0:
        return dict(page=p,blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc',limit=(p.offset,p.limit))
    return dict(page=p,blogs=blogs)

#更新日志
@post('/api/blogs/{id}')
async def api_update_blog(id,request,*,name,summary,content):
    check_admin(request)
    blog = await Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name','name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary','summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content','content cannot be empty.')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    return blog

#删除日志
@post('/api/blogs/{id}/delete')
async def api_delete_blog(request,*,id):
    check_admin(request)
    blog = await Blog.find(id)
    await blog.remove()
    return dict(id=id)

#获取用户
@get('/api/users')
async def api_get_users(*,page='1'):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(num,page_index)
    if num == 0:
        return dict(page=p,users=())
    users = await User.findAll(orderBy='created_at desc',limit=(p.offset,p.limit))
    for u in users:
        u.password = '******'
    return dict(page=p,users=users)

#获取评论
@get('/api/comments')
async def api_comments(*,page='1'):
    page_index = get_page_index(page)
    num = await Comment.findNumber('count(id)')
    p = Page(num,page_index)
    if num == 0:
        return dict(page=p,comments=())
    comments = await Comment.findAll(orderBy='created_at desc',limit=(p.offset,p.limit))
    return dict(page=p,comments=comments)

#创建评论
@post('/api/blogs/{id}/comments')
async def api_create_comment(id,request,*,content):
    user = request.__user__
    #禁止游客评论
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = await Blog.find(id)
    if not blog:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id = blog.id,user_id = user.id,user_name=user.name,user_image=user.image,content=content.strip())
    await comment.save()
    return comment

#删除评论
@post('/api/comments/{id}/delete')
async def api_delete_comments(id,request):
    check_admin(request)
    c = await Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    await c.remove()
    return dict(id=id)
#------------------后台管理------------------
@get('/manage/')
def manage():
    return 'redirect:/manage/comments'

@get('/manage/comments')
def manage_comments(request,*,page='1'):
    return {
        '__template__':'manage_comments.html',
        'page_index':get_page_index(page),
        '__user__':request.__user__
    }

@get('/manage/blogs')
def manage_blogs(request,*,page='1'):
    return {
        '__template__':'manage_blogs.html',
        'page_index':get_page_index(page),
        '__user__':request.__user__
    }

@get('/manage/blogs/create')
def manage_create_blog(request):
    return {
        '__template__':'manage_blog_edit.html',
        'id':'',
        'action':'/api/blogs',
        '__user__':request.__user__
    }

@get('/manage/blogs/edit')
def manage_edit_blog(request,*,id):
    return {
        '__template__':'manage_blog_edit.html',
        'id':id,
        'action':'/api/blogs/%s' % id,
        '__user__':request.__user__
    }

@get('/manage/users')
def manage_users(request,*,page='1'):
    return {
        '__template__':'manage_users.html',
        'page_index':get_page_index(page),
        '__user__':request.__user__
    }
