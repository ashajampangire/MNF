import binascii
import os
import secrets

import pbkdf2
import pyaes
from io import StringIO
import requests
import calendar
import time
from pptx import Presentation

from .contractInteraction import upload_to_blockchain
import zipfile
from MNF.settings import COUNTRY_KEY, EMAIL_HOST_USER, BasePath,PROJECT_ID,PROJECT_SECRET,IV,PASSWORD_SALT
import codecs
import threading
from threading import Thread
from django.utils.html import strip_tags
from MNF.email import mnfnsendemail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from datetime import date
basepath = BasePath()


def upload_string(url_string, key, file_from, email):
    gmt = time.gmtime()
    ts = calendar.timegm(gmt)
    key= key+str(ts)
    password = str(key)
    iv = IV
    passwordSalt = PASSWORD_SALT
    keyutf = pbkdf2.PBKDF2(password, passwordSalt).read(32)
    # ciphertext = encrypted url string
    aes = pyaes.AESModeOfOperationCTR(keyutf, pyaes.Counter(iv))
    ciphertext = aes.encrypt(str(url_string))
    upload_to_blockchain(ciphertext, file_from, key, email, ts)

    return ts, ciphertext

def upload_to_ipfs(contex, key, file_from, email, ts):
    projectId = PROJECT_ID
    projectSecret = PROJECT_SECRET
    endpoint = "https://ipfs.infura.io:5001"
    print("files",contex)
    files = {
        "files": contex
    }
    
    response1 = requests.post(endpoint + "/api/v0/add",
                              files=files, auth=(projectId, projectSecret))
    hash1 = response1.text.split(",")[1].split(":")[1].replace('"', "")
    password = key
    iv = IV
    passwordSalt = PASSWORD_SALT
    keyutf = pbkdf2.PBKDF2(password, passwordSalt).read(32)
    CID = hash1
    aes = pyaes.AESModeOfOperationCTR(keyutf, pyaes.Counter(iv))
    ciphertext = aes.encrypt(CID)
    print('Encrypted:', binascii.hexlify(ciphertext))
    upload_to_blockchain(ciphertext, file_from, key, email, ts)
    return ciphertext


def upload_multiFile_to_ipfs(contex, key, file_from, email):
    gmt = time.gmtime()
    ts = calendar.timegm(gmt)
    print("timestamp:-", ts)
    data = []
    projectId = PROJECT_ID
    projectSecret = PROJECT_SECRET
    endpoint = "https://ipfs.infura.io:5001"
    iv = IV
    passwordSalt = PASSWORD_SALT
    for i in range(0, len(contex)):
        print(i, contex[i], " :open codec file")
        z = codecs.open(contex[i], mode="rb")
        print("files data from database", z)
        files = {"files": z}
        response1 = requests.post(
            endpoint + "/api/v0/add", files=files, auth=(projectId, projectSecret))
        hash1 = response1.text.split(",")[1].split(":")[
            1].replace('"', "")
        password = key
        keyutf = pbkdf2.PBKDF2(password, passwordSalt).read(32)
        CID = hash1
        aes = pyaes.AESModeOfOperationCTR(keyutf, pyaes.Counter(iv))
        ciphertext = aes.encrypt(CID)
        data.append(ciphertext)
    print("ipfs data from encrypt", data)
    upload_to_blockchain(data, file_from, key, email, ts)
    return data, ts


def upload_zipfile_to_ipfs(contex, key, file_from, email):
    gmt = time.gmtime()
    ts = calendar.timegm(gmt)
    print("\n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n timestamp pitchdeck :- \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n \n  ", ts)
    print("contex files path ", contex)
    projectId = PROJECT_ID
    projectSecret = PROJECT_SECRET
    endpoint = "https://ipfs.infura.io:5001"
    iv = IV
    passwordSalt = PASSWORD_SALT
    zip_file = zipfile.ZipFile(
        f'{basepath}/blockchain/temp.zip', 'w')
    print("length..upload_pitchdeck_to_ipfs.", len(contex))
    for i in range(0, len(contex)):
        print("filename=", contex[i])
        zip_file.write(contex[i], compress_type=zipfile.ZIP_DEFLATED)
    zip_file.close()
    print("......//", zip_file.filename)
    zfile = codecs.open(zip_file.filename, mode="rb")
    print("files data from pitchdeck", zfile)
    files = {
        "files": zfile
    }
    response1 = requests.post(
        endpoint + "/api/v0/add", files=files, auth=(projectId, projectSecret))
    hash1 = response1.text.split(",")[1].split(":")[1].replace('"', "")
    password = key
    keyutf = pbkdf2.PBKDF2(password, passwordSalt).read(32)
    CID = hash1
    aes = pyaes.AESModeOfOperationCTR(keyutf, pyaes.Counter(iv))
    ciphertext = aes.encrypt(CID)
    print("ipfs data from encrypt", CID)
    upload_to_blockchain(ciphertext, file_from, key, email, ts)

    return ciphertext, ts
