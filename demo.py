#!/usr/bin/env python
import database

db = database.Connection(host='localhost',database='postgres',user='postgres')
for item in db.query("SELECT * FROM person"):
    print item