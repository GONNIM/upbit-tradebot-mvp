import bcrypt

password = "원하는 패쓰워드"
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

print("bcrypt 해시:", hashed.decode())
