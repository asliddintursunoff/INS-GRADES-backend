from datetime import  timezone, datetime, timedelta

from passlib.context import CryptContext
from jose import jwt,JWTError

from app.config import jwt_settins


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated = "auto"
    )

def hash_password(password:str) ->str:
    return pwd_context.hash(password)

def verify_password(plain_password,hashed_password:str) ->bool:
    return pwd_context.verify(plain_password,hashed_password)




def create_access_token(data:dict,expires_delta:timedelta|None = None):

    if expires_delta:
        expire = datetime.now(timezone.utc)+expires_delta
    else:
        expire = datetime.now(timezone.utc)+timedelta(
            minutes=jwt_settins.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    data.update({
        "exp":expire
    })

    encoded_jwt = jwt.encode(data,jwt_settins.SECRET_KEY,algorithm=jwt_settins.ALGORITHM)
    return encoded_jwt

def decode_token(token:str):
    try:
        payload = jwt.decode(token,jwt_settins.SECRET_KEY,algorithms=jwt_settins.ALGORITHM)
        return payload
    except JWTError:
        return None
    

    
        