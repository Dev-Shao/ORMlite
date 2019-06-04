import sys
import os
import sqlite3
from ormlite.exception import *
from ormlite.fields import Field,PrimaryKey,RelatedMix,Mappings
from ormlite.utils import _format,_condition

__models__ = {}

def registered_model(name,model):
	global __models__
	model_name = "%s.%s" % (model.__module__,name)
	__models__[model_name] = model


Sum = lambda x:'SUM(%s)' % x
Count = lambda x:"COUNT(%s)" % x
Avg = lambda x:"AVG(%s)" % x
Max = lambda x:"MAX(%s)" % x
Min = lambda x:"MIN(%s)" % x


class Database(object):

	db = {}
	
	def __init__(self,db = None):
		if db:
			self.db = db
		self.connect = None
		self.cursor = None
		self.connector = sqlite3.connect

	def __enter__(self):
		self.connect = self.connector(**self.db)
		self.cursor = self.connect.cursor()
		return self.cursor

	def __exit__(self,exc_type,exc_instance,traceback):
		if not exc_instance:
			self.connect.commit()
		self.connect.close()

	def __str__(self):
		return "<Database:'%s'>" % self.db['database']

	@classmethod
	def config(cls,database,timeout = 5,**kw):
		cls.db['database'] = database
		cls.db['timeout'] = timeout
		cls.db.update(kw)


class Query(object):

	def __init__(self,model,fields=None,**kwargs):
		self.model = model
		self.table = model.__table__
		self.fields = fields or []
		self.where = kwargs.get('where',None)
		self.alias = kwargs.get('alias',{})
		self.distinct = kwargs.get('distinct',False)
		self.orderby = kwargs.get('orderby',[])
		self.groupby = kwargs.get('groupby',[])
		self.limit = kwargs.get('limit',None)
		self.sql = ''
		self.function = None
		self.cache = None
		self.result = []

	def as_sql(self):
		sql = ['SELECT']
		if self.distinct:
			sql.append("DISTINCT")
		fields = self.fields[:]
		if self.alias:
			self.fields.extend(self.alias.keys())
			alias = ("%s AS %s " % (v,k) for k,v in self.alias.items())
			fields.extend(alias)
		sql.append(', '.join(fields))
		sql.append('FROM')
		sql.append(self.table)
		if self.where:
			sql.append("WHERE %s" % self.where)
		if self.groupby:
			sql.append("GROUP BY %s" % ','.join(self.groupby))
		if self.orderby:
			sql.append("ORDER BY %s" % ', '.join(self.orderby))
		if self.limit is not None:
			if isinstance(self.limit,slice):
				start = self.limit.start or 0
				length = self.limit.stop
				sql.append("LIMIT %s OFFSET %s" % (length,start))
			elif isinstance(self.limit,int):
				sql.append("LIMIT 1 OFFSET %s" % self.limit)
		self.sql = ' '.join(sql) + ';'
		return self.sql

	def eval(self,sql,function=None):
		with Database() as db:
			db.execute(sql)
			result = db.fetchall()
		return function(result) if function else result

	def execute(self):
		sql = self.as_sql()
		print(sql)
		with Database() as db:
			db.execute(sql)
			self.cache = db.fetchall()
		if self.function:
			#根据需要原始处理数据
			self.result = self.function(self.cache)
		else:
			self.result = self.__get_objects()
		return self.result

	def __get_objects(self):
		result = []
		for col in self.cache:
			attrs = {}
			for attr,value in zip(self.fields,col):
				attrs[attr] = value
			result.append(self.model(**attrs))
		return result

	def copy(self):
		#克隆并返回一个新的对象
		new = self.__class__(self.model,self.fields)
		new.where = self.where
		new.alias = self.alias.copy()
		new.distinct = self.distinct
		new.groupby = self.groupby[:]
		new.orderby = self.orderby[:]
		new.limit = self.limit
		return new

	def __getitem__(self,value):
		if not isinstance(value,(slice,int)):
			raise TypeError("Query object must be integers or slices")
		if self.cache:
			return list(self.result)[value]
		new = self.copy()
		new.limit = value
		new.execute()
		if isinstance(value,int):
			return new.result[0] if new.result else []
		return new.result[value]

	def __bool__(self):
		if self.cache is None:	
			self.execute()
		return bool(self.cache)

	def __iter__(self):
		if self.cache is None:
			self.execute()
		return iter(self.result)

	def __len__(self):
		if self.cache is None:
			self.execute()
		return len(self.result)

	def __or__(self,other):
		new = self.copy()
		if new.where:
			new.where = new.where + " OR " + other.where
		else:
			new.where = other.where
		return new

	def __and__(self,other):
		new = self.copy()
		if self.where:
			self.where = self.where + " AND " + other.where
		else:
			self.where = other.where
		return self

	def __str__(self):
		if self.cache is None:
			self.execute()
		return "<Query %r>" % self.result

	def get(self,**kwargs):
		query = self.copy().query(**kwargs)
		query.execute()
		if not query.result:
			raise RecordNotExistsError('Not query %s object record:%s' % (self.model,query.where))
		elif len(query.result) > 1:
			raise MultiRecordError('Query multiple %s object records:%s' % (self.model.__name__,query.where))
		return query.result[0]


	def count(self):
		if self.result:
			return len(self.result)
		new = self.copy()
		new.fields = []
		new.alias = {"__count":Count('id')}
		new.function = lambda x:x[0][0]
		new.execute()
		return new.result

	def sort(self,*fields):
		new = self.copy()
		new.orderby.extend(fields)
		return new

	def values(self,*fields,flat=False):
		new = self.copy()
		if fields:
			new.fields = list(fields)
		if flat:
			new.function = lambda x:[s[0] for s in x]
		else:
			new.function = lambda x:x
		return new

	def items(self,*fields):
		new = self.copy()
		if fields:
			new.fields = list(fields)
		fields = new.fields
		def to_dict(data):
			result = []
			for row in data:
				d = {}
				for field,value in zip(fields,row):
					d[field] = value
				result.append(d)
			return result
		new.function = to_dict
		new.execute()
		return new.result

	def query(self,**kwargs):
		where = _condition(**kwargs)
		new = self.copy()
		if new.where:
			new.where += (" AND " + where)
		else:
			new.where = where
		return new

	def group(self,**kwargs):#rename
		new = self.copy()
		alias = {k:v for k,v in kwargs.items()}
		new.alias = alias
		new.groupby = self.fields[:]
		fields = new.fields
		def to_dict(data):
			result = []
			for row in data:
				d = {}
				for field,value in zip(fields,row):
					d[field] = value
				result.append(d)
			return result
		new.function = to_dict
		new.execute()
		return new.result

	def extra(self,**kwargs):
		pass

	def exists(self):
		pass


class Insert():

	def __init__(self,table,fields,value):
		self.table = table
		self.fields = fields
		self.value = value
		self.sql = ''

	def as_sql(self):
		fields = ', '.join(self.fields)
		value = ', '.join('?' * len(self.value))
		sql = "INSERT OR REPLACE INTO %s (%s) VALUES (%s);" % (self.table,fields,value)
		self.sql = sql 
		return self.sql

	def execute(self):
		sql = self.as_sql()
		print(sql,self.value)
		with Actuator() as db:
			db.execute(sql,self.value)
			result = db.rowcount
		return result

	def __str__(self):
		return self.sql or self.as_sql()


class Update():

	def __init__(self,table,fields,value,where):
		self.table = table
		self.fields = fields
		self.value = value
		self.where = where
		self.sql = ''

	def as_sql(self):
		sql = "UPDATE %s SET %s WHERE %s;"
		fields = ["%s = ?" % f for f in self.fields]
		sql = sql % (self.table,', '.join(fields),self.where)
		self.sql = sql
		return self.sql

	def __str__(self):
		return self.sql or self.as_sql()

class Delete():

	def __init__(self,table,where):
		self.table = table
		self.where = where
		self.sql = ''

	def as_sql(self):
		self.sql = "DELETE FROM %s WHERE %s" % (self.table,self.where)
		return self.sql

	def __str__(self):
		return self.sql or self.as_sql()



class Converter(object):

	def __init__(self,model,instance = None):
		self.model = model
		self.table = model.__table__
		self._instance = instance
		self.fields = list(model.__mapping__.keys())

	def get(self,**kwargs):
		return Query(self.model,fields=self.fields).get(**kwargs)

	def save(self):
		# insert or update
		if self._instance is None:
			raise AttributeError('Missing %s object instance' % self.model.__name__)
		values = []
		for field in self.fields:
			if field in self._instance.__relation__.keys():
				value = getattr(self._instance,field)
				value = value.id
			else:
				value = getattr(self._instance,field)
			values.append(value)
		return Insert(self.table,self.fields,values).execute()

	def all(self):
		query = Query(self.model,fields=self.fields)
		return query

	def query(self,**kwargs):
		return Query(self.model,fields=self.fields).query(**kwargs)

	def update(self,*fields,**kwargs):
		"""
		:param fields: field name
		:param kwargs: field name and value
		:return: None
		"""
		if not fields and not kwargs:
			return self.save()
		if not self._instance:
			raise AttributeError('Missing %s object instance' % self.model)
		updates = {}
		for field in fields:
			updates[field] = getattr(self._instance,field)
		updates.update(kwargs)
		if 'id' in updates:
			raise ORMException("Can not update primary key")
		print(updates)
		data = []
		for k,v in updates.items():
			data.append("%s = %s" % (k,_format(v)))
		data = ",".join(data)
		condition = "id = %s" % self._instance.id
		sql = "UPDATE %s SET %s WHERE %s" % (self.table,data,condition)
		print(sql)
		with Database() as db:
			db.execute(sql)
			data = db.rowcount
		return data

	def delete(self):
		if not self._instance:
			raise DoseNotExist("%s object dose not exist" % self.model.__name__)
		condition = "id = %s" % self._instance.id
		sql = "DELETE FROM %s WHERE %s" % (self.table,condition)
		print(sql)
		with self.actuator as db:
			db.execute(sql)
		


class RelatedDescriptor(object):

	def __init__(self,name,reference):
		self.name = name
		self.related_name = name + "_id"
		self._reference = None
		self.reference = reference

	def __get__(self,instance,onwer):
		if instance:
			obj = instance.__dict__.get(self.name)
			if obj:
				return obj
			fk = getattr(instance,self.related_name)
			obj = self.reference.object.get(id=fk)
			instance.__dict__[self.name] = obj
			return obj
		return self.reference

	def __set__(self,instance,value):
		if isinstance(value,Model):
			#应该检查一下value是不是reference的实例？
			instance.__dict__[self.name] = value
			setattr(instance,self.related_name,value.id)
		elif isinstance(value,(int,str)):
			setattr(instance,self.related_name,value)
		else:
			raise ValueError("%s" % value)

	@property
	def reference(self):
		if isinstance(self._reference,str):
			model = __models__.get(self._reference)
			if not model:
				raise ValueError("Not found object:%s" % self._reference)
			return model
		return self._reference

	@reference.setter
	def reference(self,value):
		if isinstance(value,Model):
			self._reference = value
		elif isinstance(value,str):
			model = __models__.get(value,value)
			self._reference = model
		else:
			raise ValueError('Reference value must be str or model')




class ConverterDescriptor(object):

	def __init__(self,model):
		self.converter = Converter(model)

	def __get__(self,instance,onwer):
		if instance is not None:
			return Converter(onwer,instance)
		return self.converter


class ModelMetaClass(type):

	def __new__(cls,name,bases,attrs):
		if name == 'Model':
			return type.__new__(cls,name,bases,attrs)
		mapping = {}
		for attr,value in attrs.items():
			if isinstance(value,Field):
				mapping[attr] = value
				value.name = attr #
		has_pk = False
		relation = {}
		for attr,field in mapping.items():
			if isinstance(field,PrimaryKey):
				has_pk = True
			elif isinstance(field,RelatedMix):
				relation[attr] = field
				related_model = field.related_model
				if isinstance(related_model,str):
					if related_model == "self":
						related_model = "%s.%s" % (attrs['__module__'] + "." + name)
					else:
						related_model = "%s.%s" % (attrs['__module__'],related_model)
				attrs[attr] = RelatedDescriptor(attr,related_model)
				continue
			attrs[attr] = field.default #是否应该初始化?
		if not has_pk:
			mapping['id'] = PrimaryKey()
			attrs['id'] = None
		attrs['__mapping__'] = mapping
		attrs['__table__'] = name
		attrs["__relation__"] = relation
		instance = type.__new__(cls,name,bases,attrs)
		instance.object = ConverterDescriptor(instance)
		registered_model(name,instance)
		return instance


class Model(object,metaclass=ModelMetaClass):

	def __init__(self,**kwargs):
		for k,v in kwargs.items():
			setattr(self,k,v)

	def __repr__(self):
		attrs = []
		for k,v in self.__dict__.items():
			attrs.append('%s:%r' % (k,v))
		if len(attrs) > 8:
			attrs = attrs[:8]
			attrs[-1] = '...'
		return "<%s: %s>" % (self.__class__.__name__,','.join(attrs))

	def __str__(self):
		return "<%s object>" % self.__class__.__name__

	def save(self):
		self.object.save()

	def delete(self):
		pass

	def update(self):
		pass

	def clear(self):
		pass










		





