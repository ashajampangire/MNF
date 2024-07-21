from MNF.settings import IV,PASSWORD_SALT
import pbkdf2
import pyaes
def ipfsUriDecrypt(key,encryptedUri):
    password = key
    ciphertext = encryptedUri
    passwordSalt = PASSWORD_SALT
    key = pbkdf2.PBKDF2(password, passwordSalt).read(32)
    iv = IV
    aes = pyaes.AESModeOfOperationCTR(key, pyaes.Counter(iv))
    decrypted = aes.decrypt(ciphertext)
    y = str(decrypted).replace(" ","")
    a= len(y)
    p= y[2:a-1]
    decryptedUrl = 'https://ideamall.infura-ipfs.io/ipfs/'+ str(p)
    return decryptedUrl
