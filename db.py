import json
import os

class Database:
    def insert(self, name, email, password):
        with open('user.json', 'r') as rf:
            user = json.load(rf)

            if email in user:
                return 0
            else:
                user[email] = [name, password]

        with open('user.json', 'w') as wf:
            json.dump(user, wf, indent=4)
            return 1

    def validate(self, email, password):
        with open('user.json', 'r') as rf:
            user = json.load(rf)

            if email in user and user[email][1] == password:
                return user[email][0]

        return None
