import os
from orm import model


db = os.path.join(os.getcwd(),'db.sqlite3')
model.db_config['name'] = db

DATADABE = {
	"name":db
}


class User(model.Model):
	id = model.PrimaryKey('id')
	name = model.CharField('name',max_length=50)
	sex = model.CharField('sex',max_length=20)
	age = model.IntegerField('age')


 


class Studen(model.Model):
	name = model.CharField('name',max_length=50,unique=True)
	sex = model.CharField('sex',max_length=20)
	age = model.IntegerField('age',default='M',null=False)


a = User.object.all().order_by('age')
for x in a:
	print(x)
print(a)