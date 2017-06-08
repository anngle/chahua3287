#coding=utf-8
"""filename:app/models.py
Created 2017-05-30
Author: by anaf
note:数据库模型函数
"""

from werkzeug.security import generate_password_hash,check_password_hash
from app import db
from flask.ext.login import UserMixin,AnonymousUserMixin
from .import login_manager
from datetime import datetime
import hashlib,random
from flask import request,current_app



#权限
class Permission:
	FOLLOW = 0x01   #关注
	COMMIT = 0x02	#在他人的文章中发表评论
	WRITE_ARTICLES = 0x03	#写文章
	MODERATE_COMMENTS = 0x04 #管理他人发表的评论
	ADMINISTER = 0x99	#管理员



"""角色表 一对多，一个角色对应多个用户
db.relationship('User',backref='role')
因为User 还没有定义 所以使用字符串形式指定
"""
class Role(db.Model):
	__tablename__ = 'roles'
	id = db.Column(db.Integer,primary_key=True)
	name = db.Column(db.String(64),unique=True)
	default = db.Column(db.Boolean,default=False,index=True)
	permissions = db.Column(db.Integer)
	users = db.relationship('User',backref='role',lazy='dynamic')

	def __repr__(self):
		return u'[角色： %s]' % self.name

	@staticmethod
	def insert_roles():
		#二进制处理的所以在数据库中显示的7、255、3
		roles = {
			'User':(Permission.FOLLOW|
					Permission.COMMIT|
					Permission.WRITE_ARTICLES,True),
			'Moderator':(Permission.FOLLOW|
					Permission.COMMIT|
					Permission.WRITE_ARTICLES|
					Permission.MODERATE_COMMENTS,False),
			'Administrator':(0xff,False)
		}
		for r in roles:
			role = Role.query.filter_by(name=r).first()
			if role is None:
				role = Role(name=r)
			role.permissions = roles[r][0]
			role.default = roles[r][1]
			db.session.add(role)
		db.session.commit()

#多对多关系
#自引用关系
class Follow(db.Model):
	__tablename__ = 'follows'
	follower_id = db.Column(db.Integer, db.ForeignKey('users.id'),primary_key=True)
	followed_id = db.Column(db.Integer, db.ForeignKey('users.id'),primary_key=True)
	timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin,db.Model):
	__tablename__ = 'users'
	id = db.Column(db.Integer,primary_key = True)
	username = db.Column(db.String(64),unique=True,index=True)
	password_hash = db.Column(db.String(128))
	role_id = db.Column(db.Integer,db.ForeignKey('roles.id'))
	name = db.Column(db.String(64))
	location = db.Column(db.String(64))
	about_me = db.Column(db.Text())
	#创建时间
	member_since = db.Column(db.DateTime(),default=datetime.utcnow)
	#最后访问时间
	last_seen = db.Column(db.DateTime(),default=datetime.utcnow)
	avatar_hash = db.Column(db.String(32))
	article_id = db.relationship('Article',backref='author',lazy='dynamic')
	#多对多关系
	followed = db.relationship('Follow',
								foreign_keys=[Follow.follower_id],
								backref=db.backref('follower', lazy='joined'),
								lazy='dynamic',
								cascade='all, delete-orphan')
	followers = db.relationship('Follow',
								foreign_keys=[Follow.followed_id],
								backref=db.backref('followed', lazy='joined'),
								lazy='dynamic',
								cascade='all, delete-orphan')
	comments = db.relationship('Comment', backref='author', lazy='dynamic')

	def __init__(self,**kwargs):
		super(User,self).__init__(**kwargs)
		#初始化时候添加自己为关注者
		#self.follow(self)
		#赋予角色信息
		if self.role is None:
			if self.username ==current_app.config['SUPERADMIN_NAME']:
				self.role = Role.query.filter_by(permissions=0xff).first()
			if self.role is None:
				self.role = Role.query.filter_by(default=True).first()

		#头像
		if self.avatar_hash is None:
			#使用flask-admin这里得到的self为空
			if self.username:
				self.avatar_hash = hashlib.md5(self.username.encode('utf-8')).hexdigest()
			# db.session.add(self)
			# db.session.commit()

	def __repr__(self):
		return '<User %r>' % self.username

	@property
	def password(self):
		raise AttributeError('password is not a readable attribute')

	@password.setter
	def password(self,password):
		self.password_hash = generate_password_hash(password)

	def verify_password(self,password):
		return check_password_hash(self.password_hash,password)

	#验证角色
	def can(self,permissions):
		return self.role is not None and \
			(self.role.permissions & permissions) ==permissions

	#验证角色
	def is_administrator(self):
		return self.can(Permission.ADMINISTER)

	#刷新用户最后访问时间
	def ping(self):
		self.last_seen = datetime.utcnow()
		db.session.add(self)

	#头像
	def gravatar(self,size=100,default='identicon',rating='g'):
		if request.is_secure:
			url = 'https://secure.gravatar.com/avatar'
		else:
			url = 'http://www.gravatar.com/avatar'
		hash = self.avatar_hash or hashlib.md5(self.username.encode('utf-8')).hexdigest()
		return '{url}/{hash}?s={size}&d={default}&r={rating}'.format(
				url=url,hash=hash,size=size,default=default,rating=rating)

	#生成虚拟数据
	@staticmethod
	def generate_fake(count=100):
		from sqlalchemy.exc import IntegrityError
		from random import seed
		import forgery_py
		seed()
		for i in range(count):
			 u = User(username=forgery_py.internet.user_name(True),
			 		password = forgery_py.lorem_ipsum.word(),
			 		# confirmed=True,
			 		name = forgery_py.name.full_name(),
			 		location = forgery_py.address.city(),
			 		about_me = forgery_py.lorem_ipsum.sentence(),
			 		member_since = forgery_py.date.date(True)
			 		)
			 db.session.add(u)
			 try:
			 	db.session.commit()
			 except Exception, e:
			 	db.session.rollback()

	#多对多关注关系辅助方法
	def follow(self, user):
		if not self.is_following(user):
			f = Follow(follower=self,followed=user)
			db.session.add(f)
			db.session.commit()

	def unfollow(self, user):
		f = self.followed.filter_by(followed_id=user.id).first()
		if f:
			db.session.delete(f)
			db.session.commit()

	def is_following(self, user):
		return self.followed.filter_by(followed_id=user.id).first() is not None
		return fo is not None

	def is_followed_by(self, user):
		return self.followers.filter_by(follower_id=user.id).first() is not None



#验证角色
class AnonymousUser(AnonymousUserMixin):
	def can(self,permissions):
		return False

	def is_administrator(self):
		return False
#验证角色
login_manager.anonymous_user = AnonymousUser


@login_manager.user_loader
def load_user(user_id):
	return User.query.get(int(user_id))


class Article(db.Model):
	__tablename__ = 'articles'
	id = db.Column(db.Integer,primary_key=True)
	#标题
	title = db.Column(db.String(64))
	#是否显示
	show = db.Column(db.Boolean,default=True)
	#点击次数
	click = db.Column(db.Integer,default=random.randint(100,200)) 
	#缩略图
	thumbnail = db.Column(db.Text)
	#关键字
	seokey = db.Column(db.String(128))
	#描述
	seoDescription = db.Column(db.String(200))
	#栏目内容
	body = db.Column(db.Text)
	#创建时间
	timestamp = db.Column(db.DateTime,index=True,default=datetime.utcnow)
	#用户角色 多对一   此表为多
	author_id = db.Column(db.Integer,db.ForeignKey('users.id'))
	#评论 一对多 对应多条评论
	comments = db.relationship('Comment', backref='articles', lazy='dynamic')
	#栏目列表 多对一 此表为多
	author_id = db.Column(db.Integer,db.ForeignKey('users.id'))

	# category_id = db.relationship('Category', backref=db.backref('article_set', lazy='dynamic'))

	def __repr__(self):
		return u"<文章:{}>".format(self.title)

	#生成虚拟数据
	@staticmethod
	def generate_fake(count=100):
		from random import seed,randint
		import forgery_py
		seed()
		user_count = User.query.count()
		for i in range(count):
			u = User.query.offset(randint(0,user_count-1)).first()
			p = Article(title=forgery_py.name.full_name(),
					body = forgery_py.lorem_ipsum.sentences(randint(1,3)),
					timestamp=forgery_py.date.date(True),
					author = u
					)
			db.session.add(p)
			db.session.commit()

	"""平板上花了挺长的时间  很多错误，
	都是打错或者没导入，都解决了
	python manage.py shell
	from app.models import User,Post
	User.generate_fake(100)
	Post.generate_fake(100)
	"""


#评论
class Comment(db.Model):
	__tablename__ = 'comments'
	id = db.Column(db.Integer,primary_key=True)
	body = db.Column(db.Text)
	body_html = db.Column(db.Text)
	timestamp = db.Column(db.DateTime,index=True,default=datetime.utcnow)
	disabled = db.Column(db.Boolean)
	author_id =db.Column(db.Integer,db.ForeignKey('users.id'))
	article_id = db.Column(db.Integer,db.ForeignKey('articles.id'))

	@staticmethod
	def on_changed_body(target,value,oldvalue,initiator):
		allowed_tags = ['a','abbr','acronym','b','code','em','i','strong']
		target.body_html 



category_attribute_reg = db.Table('category_attribute_register',
							db.Column('category_id',db.Integer,db.ForeignKey('categorys.id')),
							db.Column('category_attribute_id',db.Integer,db.ForeignKey('category_attribute.id'))
							)


#多对多关系
#自引用关系
#栏目pid
class CategoryPid(db.Model):
	__tablename__ = 'category_pid'
	category_id = db.Column(db.Integer, db.ForeignKey('categorys.id'),primary_key=True)
	category_pid = db.Column(db.Integer, db.ForeignKey('categorys.id'),primary_key=True)



#栏目导航分类
class Category(db.Model):
	__tablename__ = 'categorys'
	id = db.Column(db.Integer,primary_key=True)
	title = db.Column(db.String(64))
	show = db.Column(db.Boolean,default=True)
	sort = db.Column(db.Integer,default=100)
	pubd =  db.Column(db.DateTime(),default = datetime.utcnow)
	nlink = db.Column(db.Text)
	template  = db.Column(db.String(64))
	body = db.Column(db.Text)
	#外键属性表
	category_attribute_id = db.relationship('Category_attribute',
								secondary=category_attribute_reg,
								backref=db.backref('category',lazy='dynamic'),
								lazy='dynamic')
	seoKey = db.Column(db.String(200))
	seoDescription = db.Column(db.String(200))
	#多对多关系
	# pid = db.Column(db.Integer, db.ForeignKey('category.id'))
	# pcategory = db.relationship('Category', remote_side=[id])
	categoryed = db.relationship('CategoryPid',
								foreign_keys=[CategoryPid.category_id],
								backref=db.backref('categoryer', lazy='joined'),
								lazy='dynamic',
								cascade='all, delete-orphan')
	categoryers = db.relationship('CategoryPid',
								foreign_keys=[CategoryPid.category_pid],
								backref=db.backref('categoryed', lazy='joined'),
								lazy='dynamic',
								cascade='all, delete-orphan')

	def __repr__(self):
		return "<category:{}>".format(self.title)

	def __init__(self, name, pcategory=None):
		self.pcategory = pcategory





class Category_attribute(db.Model):
	__tablename__ = 'category_attribute'
	id = db.Column(db.Integer,primary_key=True)
	name = db.Column(db.String(64))


#留言表
class User_msg(db.Model):
	__tablename__ = 'user_msgs'
	id = db.Column(db.Integer,primary_key=True)
	name = db.Column(db.String(64))
	phone = db.Column(db.String(11))
	body = db.Column(db.Text)
	timestamp = db.Column(db.DateTime(),default=datetime.utcnow)







