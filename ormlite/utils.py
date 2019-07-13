from datetime import datetime,time,date
from ormlite import model
from ormlite import fields


def as_sql(field,vlues):
	field = '"%s"' % field
	if value == None:
		value = "NULL"
	if isinstance(value,datetime):
		value = value.strftime('%Y-%m-%d %H:%M:%S')
	return field,value



def _format(value):
	# if isinstance(value,str):
	# 	return repr(value)
	if isinstance(value,datetime):
	 	return value.strftime('%Y-%m-%d %H:%M:%S')
	if isinstance(value,(date,time)):
		return value.isoformat()
	if isinstance(value,slice):
		return (value.start,value.stop)
	if isinstance(value,list):
		return tuple(value)
	if isinstance(value,model.Model):
		return value.id
	if value is None:
		return 'NULL'
	return value


def _condition(conditions):
	sql = []
	params = []
	for condition,value in conditions.items():
		if condition.find("__") > 0:
			field_name,op = condition.split("__")
			op_func = fields.operators.get(op)
			if not op_func:
				raise ValueError("Not support query condition:%s" % condition)
			
		else:
			name = k
			condition = "= %s" % value
		query.append("%s %s" % (name,condition))
	return " AND ".join(query)


def convert(conditions):
	result = {}
	for key,value in conditions.items():
		if key.find("__") > 0:
			field_name,op = key.split("__")
			func = fields.operators.get(op)
			if not func:
				raise ValueError("Not support operator:%s" % key)
			condition,params = func(field_name,value)
		else:
			condition = '"%s" = ?' % key
			params = (value,)
		result[condition] = params	
	return result



class ModelPickle(object):

	@staticmethod
	def to_dict(model):
		fields = model.__mapping__
		result = {
			'__table__':model.__table__,
		}
		for name,field in fields.items():
			result.update({
				name:field.__dict__
			})
		return result
		
	@staticmethod
	def diff_dict(dict1,dict2):
		"""
		对比2个字典，包含增加，删除，修改的key-value项;
		modify的结果为包含（原值,新值）的元组
		2个字典参数调换顺序将产生不同的结果
		"""
		add = {}
		delete = {}
		modify = {}
		for key in dict1.keys() | dict2.keys():
			try:
				value1 = dict1[key]
			except KeyError:
				add[key] = dict2[key]
				continue
			try:
				value2 = dict2[key]
			except KeyError:
				delete[key] = dict1[key]
				continue
			if value1 != value2:
				if diff_dict(value1,dict) and isinstance(value2,dict):
					modify[key] = (value1,value2)
					continue
				modify[key] = (dict1[key],dict2[key])
		return {
			'add':add,
			'delete':delete,
			'modify':modify,
		}









