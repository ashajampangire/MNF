import binascii
import pbkdf2
import pyaes
import calendar
import time
from Crypto.Hash import keccak
from web3 import Web3
from hexbytes import HexBytes
from django.utils.html import strip_tags
from MNF.email import mnfnsendemail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from datetime import date
from MNF.settings import COUNTRY_KEY, EMAIL_HOST_USER, BasePath,PRIVATE_KEY,ACCOUNT,IV,PASSWORD_SALT
from lpp.certificate.createCertificate import certificateGenrate
basepath = BasePath()


web3 = Web3(Web3.HTTPProvider("https://rpc-mumbai.maticvigil.com/"))
CAddress = '0x054CEcc939bFE3021e7493A29C2db6B701372594'
abi ='[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"previousOwner","type":"address"},{"indexed":true,"internalType":"address","name":"newOwner","type":"address"}],"name":"OwnershipTransferred","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"string","name":"uploaderName","type":"string"},{"indexed":true,"internalType":"string","name":"fileName","type":"string"},{"indexed":true,"internalType":"uint256","name":"timeOfUpload","type":"uint256"}],"name":"uploadDetails","type":"event"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"},{"internalType":"uint256","name":"","type":"uint256"}],"name":"bookConvert","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"characterIntroduction","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_bookCombine","type":"bytes32"},{"internalType":"bytes[2]","name":"_uri","type":"bytes[2]"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createBookConversion","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_combineCharacterIntro","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createCharacterIntro","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_combineFootage","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createFootage","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_combineFullNarration","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createFullNarration","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_combineFullScript","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createFullScript","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_onePagerCombine","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createOnePager","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_pptCombine","type":"bytes32"},{"internalType":"bytes[2]","name":"_uri","type":"bytes[2]"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createPPTconversion","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_combinePitchDeck","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createPitchDeck","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_pitchDeckCombine","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createPitchDeckConversion","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_previewChamberCombine","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createPreviewChamber","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_projectCenterCombine","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createProjectCenter","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_combineSampleNarration","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createSampleNarration","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_combineSampleScript","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createSampleScript","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_combineScriptAnalysis","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createScriptAnalysis","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_scriptCombine","type":"bytes32"},{"internalType":"bytes[2]","name":"_uri","type":"bytes[2]"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createScriptConversion","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_scriptPadCombine","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createScriptPad","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_storyCombine","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createStory","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_storyCombine","type":"bytes32"},{"internalType":"bytes[2]","name":"_uri","type":"bytes[2]"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createStoryConversion","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_subscriptionCombine","type":"bytes32"},{"internalType":"string","name":"startDate","type":"string"},{"internalType":"string","name":"endDate","type":"string"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createSubscription","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_viewerLoungeVideoCombine","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createViewerLoungeForVideo","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"_viewerLoungeLinkCombine","type":"bytes32"},{"internalType":"bytes","name":"_uri","type":"bytes"},{"internalType":"string","name":"_userName","type":"string"},{"internalType":"string","name":"_fileName","type":"string"},{"internalType":"uint256","name":"_timeOfUpload","type":"uint256"}],"name":"createviewerLoungeForLink","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"footage","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"fullNarration","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"fullScript","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"onePager","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"pitchDeck","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"pitchDeckConvert","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"},{"internalType":"uint256","name":"","type":"uint256"}],"name":"pptConvert","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"previewChamber","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"projectCenter","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"remove","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"renounceOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"sampleNarration","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"sampleScript","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"scriptAnalysis","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"},{"internalType":"uint256","name":"","type":"uint256"}],"name":"scriptConvert","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"scriptPad","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showBookConvert","outputs":[{"internalType":"bytes[2]","name":"","type":"bytes[2]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showCharacterIntro","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showFootage","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showFullNarration","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showFullScript","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showOnePager","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showPPTconvert","outputs":[{"internalType":"bytes[2]","name":"","type":"bytes[2]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showPitchDeck","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showPitchDeckConvert","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showPreviewChamber","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showSampleNarration","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showSampleScript","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showScriptAnalysis","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showScriptConvert","outputs":[{"internalType":"bytes[2]","name":"","type":"bytes[2]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showScriptPad","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showStory","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showStoryConvert","outputs":[{"internalType":"bytes[2]","name":"","type":"bytes[2]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showSubscription","outputs":[{"components":[{"internalType":"string","name":"subscriptionStartTime","type":"string"},{"internalType":"string","name":"subscriptionEndTime","type":"string"}],"internalType":"struct myNextFilm.subscription","name":"","type":"tuple"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showViewerLoungeLink","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showViewerLoungeVideo","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"string","name":"_email","type":"string"},{"internalType":"string","name":"_previewName","type":"string"},{"internalType":"uint256","name":"_timeStamp","type":"uint256"}],"name":"showprojectCenter","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"story","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"},{"internalType":"uint256","name":"","type":"uint256"}],"name":"storyConvert","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"subscribe","outputs":[{"internalType":"string","name":"subscriptionStartTime","type":"string"},{"internalType":"string","name":"subscriptionEndTime","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"newOwner","type":"address"}],"name":"transferOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"string","name":"","type":"string"},{"internalType":"string","name":"","type":"string"},{"internalType":"uint256","name":"","type":"uint256"}],"name":"uploadFileStatus","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"viewerLoungeLink","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"viewerLoungeVideo","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"view","type":"function"}]'
privatekey = PRIVATE_KEY
contractInst = web3.eth.contract(address=CAddress, abi=abi)
acc1 = ACCOUNT

def upload_to_blockchain(ciphertext, file_from, key, email, ts):
    key = str(key)
    nonce = web3.eth.getTransactionCount(acc1)
    projectTitle = '0x' + \
        binascii.hexlify(Web3.solidityKeccak(['string'], [key])).decode()
    Email = '0x' + \
        binascii.hexlify(Web3.solidityKeccak(['string'], [email])).decode()
    combineEncrypt = '0x'+binascii.hexlify(Web3.solidityKeccak(
        ['bytes32', 'bytes32', 'uint256'], [Email, projectTitle, ts])).decode()
    spliting = "@" 
    temp = email.find(spliting)
    userName = email[0:temp]
    if file_from == "UploadOnePager":
        file_from ="Ideamall:One Pager"
        upload_one_pager = contractInst.functions.createOnePager(combineEncrypt,ciphertext,userName,file_from,ts).buildTransaction({
          'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_one_pager, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "storyuploaded":
        file_from = "Ideamall:Story"
        upload_story = contractInst.functions.createStory(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
           'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_story, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "samplescriptuploaded":
        file_from = "Ideamall:Sample Script"
        upload_sample_script = contractInst.functions.createSampleScript(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
           'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_sample_script, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "fullscriptuploaded":
        file_from = "Ideamall:Full Script"
        upload_fullscript = contractInst.functions.createFullScript(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
           'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_fullscript, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "samplefootageuploaded":
        file_from = "Ideamall:Sample Footage"
        upload_footage = contractInst.functions.createFootage(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
          'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_footage, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "pitchdeckuploaded":
        file_from = "Ideamall:Pitchdeck"
        upload_pitchDeck = contractInst.functions.createPitchDeck(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
           'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_pitchDeck, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "samplenarrationuploaded":
        file_from = "Ideamall:Sample Narration"
        upload_sample_narration = contractInst.functions.createSampleNarration(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
           'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_sample_narration, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "scriptanalysisuploaded":
        file_from = "Ideamall:Script Analysis"
        upload_script_analysis = contractInst.functions.createScriptAnalysis(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
          'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_script_analysis, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "narratefulluploaded":
        file_from = "Ideamall:Full Narration"
        upload_full_narration = contractInst.functions.createFullNarration(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
           'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_full_narration, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "characterintrouploaded":
        file_from = "Ideamall:Character Introduction"
        upload_character_intro = contractInst.functions.createCharacterIntro(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
           'gasPrice': web3.eth.gas_price,
            'chainId': 80001,
            'from': acc1,
            'nonce': nonce
        })
        signed_transaction = web3.eth.account.sign_transaction(
            upload_character_intro, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        web3.eth.wait_for_transaction_receipt(transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "convertPPT":
        file_from = "Conversion Studio:Converted PPT"
        uploadConvertedPPT = contractInst.functions.createPPTconversion(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadConvertedPPT, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex()
      
    elif file_from == "convertStory":
        file_from = "Conversion Studio:Converted Story"
        uploadConvertedStory = contractInst.functions.createStoryConversion(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadConvertedStory, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex()
        
    elif file_from == "convertBook":
        file_from = "Conversion Studio:Converted Book"
        uploadConvertedBook = contractInst.functions.createBookConversion(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadConvertedBook, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "convertScript":
        file_from = "Conversion Studio:Converted Script"
        uploadConvertedScript = contractInst.functions.createScriptConversion(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadConvertedScript, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "pitchdeck":
        file_from = "Narration: Narration Bundle"
        uploadConvertedPitchdeck = contractInst.functions.createPitchDeckConversion(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadConvertedPitchdeck, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex()

    elif file_from == "viewerLoungevideo":
        file_from = "Viewer's Lounge: video"
        uploadviewerloungevideo = contractInst.functions.createViewerLoungeForVideo(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadviewerloungevideo, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash) 
        tx_id = transaction_hash.hex()
       
    elif file_from == "viewerLoungelink":
        file_from = "Viewer's Lounge: Link"
        uploadviewerloungelink = contractInst.functions.createviewerLoungeForLink(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadviewerloungelink, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex()
        
    elif file_from == "scriptpad":
        file_from = "Script Builder:Scriptpad"
        uploadscriptpad = contractInst.functions.createScriptPad(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadscriptpad, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex() 
        
    elif file_from == "Preview Chamber":
        uploadpreviewchamber = contractInst.functions.createPreviewChamber(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadpreviewchamber, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex()  
        
    elif file_from == "projectCenter":
        uploadprojectcenter = contractInst.functions.createProjectCenter(combineEncrypt, ciphertext,userName,file_from,ts).buildTransaction({
            'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
        signed_transaction = web3.eth.account.sign_transaction(
            uploadprojectcenter, private_key=privatekey)
        transaction_hash = web3.eth.send_raw_transaction(
            signed_transaction.rawTransaction)
        transaction_receipt = web3.eth.wait_for_transaction_receipt(
            transaction_hash)
        tx_id = transaction_hash.hex()  
            
    certificate_send(email,userName,file_from,tx_id,ts,key) 
        
def upload_subscription_to_blockchain(key, email,start_date,exp_date): 
    key = str(key)
    gmt = time.gmtime()
    ts = calendar.timegm(gmt)
    file_from ="Claim your Privileges"
    spliting = "@" 
    temp = email.find(spliting)
    userName = email[0:temp]
    nonce = web3.eth.getTransactionCount(acc1)
    projectTitle = '0x' + binascii.hexlify(Web3.solidityKeccak(['string'], [key])).decode()
    Email = '0x' +binascii.hexlify(Web3.solidityKeccak(['string'], [email])).decode()
    combineEncrypt = '0x'+binascii.hexlify(Web3.solidityKeccak(['bytes32', 'bytes32', 'uint256'], [Email, projectTitle, ts])).decode()
    uploadsubscription = contractInst.functions.createSubscription(combineEncrypt, str(start_date),str(exp_date),userName,file_from,ts).buildTransaction({
    'gasPrice': web3.eth.gas_price, 'chainId': 80001, 'from': acc1, 'nonce': nonce})
    signed_transaction = web3.eth.account.sign_transaction(uploadsubscription, private_key=privatekey)
    transaction_hash = web3.eth.send_raw_transaction(signed_transaction.rawTransaction)
    transaction_receipt = web3.eth.wait_for_transaction_receipt(transaction_hash)
    tx_id = transaction_hash.hex()  
    certificate_send(email,userName,file_from,tx_id,ts,key)   
     
    # FOR SENDING DETAILS AND CERTIFICATE TO FILE OWNER ciphertext, file_from, key, email, ts
def certificate_send(email,userName,file_from,tx_id,ts,key):
    certificate = certificateGenrate(email,file_from,tx_id)
    subject = "Congratulations your data is secure on blockchain!"
    from_email = EMAIL_HOST_USER
    to = email
    context = {
        "Date": date.today(),
        "Name": email,
        "emailcode": "B100",
        "heading1": "Uploaded to blockchain",
        "heading2": f"To view from blockchain use following details: Timestamp - {ts}, Key - {key}, FileName - {file_from},UserName -{userName}",
    }
    html_content = render_to_string(
        rf"{basepath}/lpp/templates/lpp/email_templete.html",
        context,  # /home/user/mnf/project/MNF/ideamall/templates/ideamall/email_templete.html
    )  # render with dynamic value
    # Strip the html tag. So people can see the pure text at least.
    text_content = strip_tags(html_content)
    # create the email, and attach the HTML version as well.
    msg = EmailMultiAlternatives(
        subject, text_content, from_email, [to])
    msg.attach_alternative(html_content, "text/html")
    msg.attach_file(certificate)
    msg.send()
    print("Message send successfully")

def ipfsUriDecrypt(key, encryptedUri):
    password = key
    hb = HexBytes(encryptedUri)
    ciphertext = bytes(hb)
    print("ciphertext", ciphertext)
    passwordSalt = PASSWORD_SALT 
    key = pbkdf2.PBKDF2(password, passwordSalt).read(32)
    iv = IV
    aes = pyaes.AESModeOfOperationCTR(key, pyaes.Counter(iv))
    decrypted = aes.decrypt(ciphertext)
    y = str(decrypted)
    a = len(y)
    p = y[2:a-1]
    decryptedUrl = 'https://ideamall.infura-ipfs.io/ipfs/' + str(p)
    return decryptedUrl

def ipfsUriDecryptConversion(key, encryptedUri):
    password = key
    passwordSalt = PASSWORD_SALT
    key = pbkdf2.PBKDF2(password, passwordSalt).read(32)
    iv = IV
    aes = pyaes.AESModeOfOperationCTR(key, pyaes.Counter(iv))
    decrypted = aes.decrypt(encryptedUri)
    y = str(decrypted)
    a = len(y)
    p = y[2:a-1]
    decryptedUrl = 'https://ideamall.infura-ipfs.io/ipfs/' + str(p)
    print("decryptedUrl", decryptedUrl)
    return decryptedUrl

def decryptUrifromBlockchain(key, encryptedUri):
    password = key
    passwordSalt = PASSWORD_SALT
    key = pbkdf2.PBKDF2(password, passwordSalt).read(32)
    iv = IV
    aes = pyaes.AESModeOfOperationCTR(key, pyaes.Counter(iv))
    decrypted = aes.decrypt(encryptedUri)
    y = str(decrypted)
    a = len(y)
    p = y[2:a-1]
    decryptedUrl =str(p)
    print("decryptedUrl", decryptedUrl)
    return decryptedUrl

def fetchFromBlockchain(file_from, email, key, ts):
    decryptUrl = []
    ts = int(ts)
    if file_from == 'onepager':
        showOnePager1 = contractInst.functions.showOnePager(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showOnePager1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'story':
        showStory1 = contractInst.functions.showStory(email, key, ts).call()
        url = ipfsUriDecrypt(key, showStory1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'samplescript':
        showSampleScript1 = contractInst.functions.showSampleScript(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showSampleScript1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'fullscript':
        showFullScript1 = contractInst.functions.showFullScript(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showFullScript1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'footage':
        showFootage1 = contractInst.functions.showFootage(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showFootage1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'pitchdeck':
        showPitchDeck1 = contractInst.functions.showPitchDeck(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showPitchDeck1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'samplenarration':
        showSampleNarration1 = contractInst.functions.showSampleNarration(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showSampleNarration1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'scriptanalysis':
        showScriptAnalysis1 = contractInst.functions.showScriptAnalysis(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showScriptAnalysis1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'fullnarration':
        showFullNarration1 = contractInst.functions.showFullNarration(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showFullNarration1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == 'characterintro':
        showCharacterIntroduction1 = contractInst.functions.showCharacterIntro(
            email, key, ts).call()
        url = ipfsUriDecrypt(key, showCharacterIntroduction1)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == "convertPPT":
        showPpt = contractInst.functions.showPPTconvert(email, key, ts).call()
        print("Showencrypted files", showPpt)
        for i in range(0, len(showPpt)):
            url = ipfsUriDecryptConversion(key, showPpt[i])
            decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == "convertStory":
        showstoryconvert = contractInst.functions.showStoryConvert(
            email, key, ts).call()
        print("Showencrypted files", showstoryconvert)
        for i in range(0, len(showstoryconvert)):
            url = ipfsUriDecryptConversion(key, showstoryconvert[i])
            decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == "convertBook":
        showbookconvert = contractInst.functions.showBookConvert(
            email, key, ts).call()
        print("Showencrypted files", showbookconvert)
        for i in range(0, len(showbookconvert)):
            url = ipfsUriDecryptConversion(key, showbookconvert[i])
            decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == "convertScript":
        showscriptconvert = contractInst.functions.showScriptConvert(
            email, key, ts).call()
        print("Showencrypted files", showscriptconvert)
        for i in range(0, len(showscriptconvert)):
            url = ipfsUriDecryptConversion(key, showscriptconvert[i])
            decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl
   
    elif file_from == "pitchdeckNarration":
        showpitchdeckconvert = contractInst.functions.showPitchDeckConvert(
            email, key, ts).call()
        print("pitchdeck fetch from blockchain",showpitchdeckconvert)
        url = ipfsUriDecryptConversion(key, showpitchdeckconvert)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl

    elif file_from == "viewerLoungevideo":
        showviwerloungevideo = contractInst.functions.showViewerLoungeVideo(email, key, ts).call()
        print("Showencrypted files",  showviwerloungevideo )
        url = ipfsUriDecryptConversion(key,  showviwerloungevideo )
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl
    
    elif file_from == "viewerLoungelink":
        showviwerloungelink = contractInst.functions.showViewerLoungeLink(email, key, ts).call()
        print("Showencrypted files",  showviwerloungelink )
        url = decryptUrifromBlockchain(key,  showviwerloungelink )
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl
    
    elif file_from == "scriptpad":
        showscriptpad = contractInst.functions.showScriptPad(email, key, ts).call()
        print("Showencrypted files",  showscriptpad)
        url = ipfsUriDecryptConversion(key,  showscriptpad)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl
    
    elif file_from == "previewchamber":
        showpreviewchamber = contractInst.functions.showPreviewChamber(email, key, ts).call()
        print("Showencrypted files",  showpreviewchamber)
        url = ipfsUriDecryptConversion(key,  showpreviewchamber)
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl
    
    
    elif file_from == 'projectCenter':
        showprojectcenter = contractInst.functions.showprojectCenter(email, key, ts).call()
        url = ipfsUriDecrypt(key, showprojectcenter )
        decryptUrl.append(url)
        print("Decrypt URL", decryptUrl)
        return decryptUrl
    
    elif file_from == "subscription":
        showsubscription = contractInst.functions.showSubscription(email, key, ts).call()
        print("urlsubscription", showsubscription)
        for i in range(0, len(showsubscription)):
          decryptUrl.append(showsubscription[i])
        print("Decrypt URL", decryptUrl)
        return decryptUrl
    
def verifyFromBlockchain(userName,file,ts):
    ts = int(ts)
    result = contractInst.functions.uploadFileStatus(userName, file, ts).call()
    print("verify data from blockchain", result)

    return result